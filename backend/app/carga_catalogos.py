"""Carga masiva de los catálogos (períodos, secciones, materias, docentes, estudiantes,
carreras y departamentos) desde la plantilla Excel o un CSV.

Mismo recorrido que las demás importaciones (app/importar.py): se descarga la
plantilla de ese catálogo, se llena, se sube y se ve una VISTA PREVIA con lo que va
a crear o actualizar; nada se escribe hasta confirmar y, si hay un solo error, no se
puede confirmar. Al confirmar todo se aplica o nada se aplica.

Cada fila se valida con las mismas reglas que el formulario de alta
(catalogos.leer_formulario), así que un valor que el formulario rechaza también lo
rechaza la carga. En el archivo las referencias se escriben con el CÓDIGO legible
(el de la materia, la carrera…), no con el número interno; la hoja «Referencia» de la
plantilla los lista. La parte pura (analizar, leer_carga) no toca la base: recibe las
referencias y los registros existentes ya consultados, para probarla sin base.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .catalogos import Campo, Catalogo, aplicar, hash_carnet, leer_formulario
from .importar import ErrorArchivo, como_entero, como_fecha, normalizar, ubicar_cabecera
from .models import Carrera, Departamento, Docente, Estudiante, Materia, PeriodoAcademico

FILAS_MAXIMAS = 1000   # el resultado de la vista previa viaja en el formulario de confirmación

# Campo de clave foránea -> (modelo, atributo con el código legible).
REFERENCIAS = {
    "periodo_id": (PeriodoAcademico, "codigo_periodo"),
    "materia_id": (Materia, "codigo_materia"),
    "docente_id": (Docente, "codigo_docente"),
    "carrera_id": (Carrera, "codigo_carrera"),
    "departamento_id": (Departamento, "codigo_departamento"),
}

# Con qué se decide si una fila crea un registro o actualiza uno existente.
CLAVE_NATURAL = {
    "periodos": ("codigo_periodo",),
    "secciones": ("periodo_id", "materia_id", "numero_seccion"),
    "materias": ("codigo_materia",),
    "docentes": ("codigo_docente",),
    "estudiantes": ("carnet",),
    "carreras": ("codigo_carrera",),
    "departamentos": ("codigo_departamento",),
}

AFIRMATIVOS = {"si", "s", "x", "1", "true", "verdadero", "yes", "y"}
NEGATIVOS = {"", "no", "n", "0", "false", "falso"}
HASH_VALIDO = re.compile(r"^[0-9a-f]{64}$")


class ErrorCarga(ValueError):
    """La confirmación no coincide con lo que se revisó, o la base rechazó una fila."""


@dataclass
class Cambio:
    tipo: str                       # nueva | cambio | igual
    fila: int
    formulario: dict[str, str]      # valores como texto, listos para leer_formulario
    valores: dict[str, Any]         # valores ya tipados
    registro_id: Optional[int] = None
    carnet_hash: Optional[str] = None
    diferencias: list[str] = field(default_factory=list)


def codigo_de_referencia(texto: str) -> str:
    """«ABC101 · Álgebra» (como se ve en la hoja Referencia) -> «ABC101»."""
    return texto.split(" · ")[0].strip().upper()


def cabeceras(catalogo: Catalogo) -> list[str]:
    return [c.etiqueta for c in catalogo.campos]


def _texto_de_celda(campo: Campo, valor: Any, refs: dict) -> tuple[str, Optional[str]]:
    """(texto para el formulario, error). Texto vacío = celda vacía."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        # «Activo» vacío cuenta como Sí (así nace en el formulario); los demás Sí/No, como No.
        return ("on" if campo.tipo == "bool" and campo.por_defecto else "", None)
    if campo.tipo == "bool":
        marca = normalizar(valor)
        if marca in AFIRMATIVOS:
            return ("on", None)
        if marca in NEGATIVOS:
            return ("", None)
        return ("", f"«{campo.etiqueta}»: escribe Sí o No.")
    if campo.tipo == "fecha":
        fecha = como_fecha(valor)
        return (fecha.isoformat(), None) if fecha else ("", f"«{campo.etiqueta}» no es una fecha válida (usa AAAA-MM-DD).")
    if campo.tipo == "fk":
        codigo = codigo_de_referencia(str(valor))
        encontrado = refs.get(campo.nombre, {}).get(codigo)
        if encontrado is None:
            return ("", f"«{campo.etiqueta}»: «{str(valor).strip()}» no existe. Usa un código de la hoja Referencia.")
        return (str(encontrado), None)
    if campo.tipo == "entero":
        numero = como_entero(valor)
        return (str(numero), None) if numero is not None else ("", f"«{campo.etiqueta}» debe ser un número entero.")
    if campo.tipo == "opcion":
        elegido = normalizar(valor).upper()
        if elegido not in campo.opciones:
            return ("", f"«{campo.etiqueta}»: «{str(valor).strip()}» no es válido. Usa: {', '.join(campo.opciones)}.")
        return (elegido, None)
    if isinstance(valor, float) and valor.is_integer():
        return (str(int(valor)), None)   # un carnet o código numérico que Excel guardó como número
    return (str(valor).strip(), None)


def _clave(catalogo: Catalogo, formulario: dict, valores: dict) -> tuple:
    if catalogo.slug == "estudiantes":
        return (hash_carnet(formulario["carnet"]),)
    return tuple(valores[nombre] for nombre in CLAVE_NATURAL[catalogo.slug])


def _legible(catalogo: Catalogo, formulario: dict) -> str:
    nombres = CLAVE_NATURAL[catalogo.slug]
    return " / ".join("(carnet)" if n == "carnet" else str(formulario.get(n, "")) for n in nombres)


def _diferencias(catalogo: Catalogo, valores: dict, actual: dict) -> list[str]:
    cambios = []
    for campo in catalogo.campos:
        if campo.virtual or campo.solo_alta or campo.nombre not in valores:
            continue
        if valores[campo.nombre] != actual.get(campo.nombre):
            cambios.append(campo.etiqueta)
    return cambios


def analizar(catalogo: Catalogo, filas: list[list[Any]], refs: dict, existentes: dict) -> tuple[list[Cambio], list[str]]:
    """Convierte las filas del archivo en cambios y errores.

    refs: {campo_fk: {CÓDIGO: id}}. existentes: {clave natural: {campo: valor, "_id": id}}.
    """
    errores: list[str] = []
    etiquetas = cabeceras(catalogo)
    inicio = ubicar_cabecera(filas, etiquetas[0])
    encontradas = [normalizar(c) for c in (list(filas[inicio]) + [None] * len(etiquetas))[:len(etiquetas)]]
    if encontradas != [normalizar(e) for e in etiquetas]:
        raise ErrorArchivo(f"Las columnas no coinciden con la plantilla de «{catalogo.titulo}». "
                           "Descarga la plantilla de este catálogo y úsala sin cambiar la cabecera.")
    datos = filas[inicio + 1:]
    if len(datos) > FILAS_MAXIMAS:
        raise ErrorArchivo(f"Cada carga admite hasta {FILAS_MAXIMAS:,} filas; el archivo tiene {len(datos):,}. "
                           "Divídelo en varios archivos.")
    cambios: list[Cambio] = []
    vistos: dict[tuple, int] = {}
    vigentes = []
    for numero, fila in enumerate(datos, start=inicio + 2):
        fila = list(fila) + [None] * len(catalogo.campos)
        formulario, fallas = {}, []
        for campo, valor in zip(catalogo.campos, fila):
            texto, error = _texto_de_celda(campo, valor, refs)
            formulario[campo.nombre] = texto
            if error:
                fallas.append(error)
        if not fallas:
            valores, fallas = leer_formulario(catalogo, formulario, creando=True)
        if fallas:
            errores.extend(f"Fila {numero}: {f}" for f in fallas)
            continue
        clave = _clave(catalogo, formulario, valores)
        if clave in vistos:
            errores.append(f"Fila {numero}: {_legible(catalogo, formulario)} ya aparece en la fila {vistos[clave]}.")
            continue
        vistos[clave] = numero
        actual = existentes.get(clave)
        cambio = Cambio("nueva", numero, formulario, valores)
        if actual is not None:
            cambio.registro_id = actual["_id"]
            cambio.diferencias = _diferencias(catalogo, valores, actual)
            cambio.tipo = "cambio" if cambio.diferencias else "igual"
        if catalogo.slug == "estudiantes":
            cambio.carnet_hash = clave[0]
        if catalogo.slug == "periodos" and valores.get("activo"):
            vigentes.append(numero)
        cambios.append(cambio)
    if len(vigentes) > 1:
        errores.append("Solo un período puede quedar vigente; hay varios marcados en las filas "
                       + ", ".join(map(str, vigentes)) + ".")
    return cambios, errores


# ---------------------------------------------------------------------------
# Confirmación: lo revisado viaja en un campo oculto y se vuelve a validar entero.
# ---------------------------------------------------------------------------

def empaquetar(catalogo: Catalogo, cambios: list[Cambio]) -> str:
    """Lo que hay que aplicar (nuevas y cambios), sin el carnet: solo su hash."""
    pendientes = []
    for c in cambios:
        if c.tipo == "igual":
            continue
        formulario = {k: v for k, v in c.formulario.items() if k != "carnet"}
        pendientes.append({"t": c.tipo, "n": c.fila, "i": c.registro_id, "h": c.carnet_hash, "f": formulario})
    return json.dumps(pendientes, ensure_ascii=False, separators=(",", ":"))


def leer_carga(catalogo: Catalogo, texto: str) -> list[Cambio]:
    """Reconstruye y vuelve a validar los cambios de la vista previa. ErrorCarga si algo
    no cuadra: la persona que confirma vuelve a subir el archivo."""
    cambiada = ErrorCarga("La carga cambió desde la vista previa: vuelve a subir el archivo.")
    try:
        paquete = json.loads(texto)
    except ValueError:
        raise cambiada from None
    if not isinstance(paquete, list) or not paquete or len(paquete) > FILAS_MAXIMAS:
        raise cambiada
    cambios = []
    for item in paquete:
        if not isinstance(item, dict) or item.get("t") not in ("nueva", "cambio") or not isinstance(item.get("f"), dict):
            raise cambiada
        formulario = {str(k): str(v) for k, v in item["f"].items()}
        nueva = item["t"] == "nueva"
        registro_id, hash_ = item.get("i"), item.get("h")
        if not nueva and not isinstance(registro_id, int):
            raise cambiada
        if catalogo.slug == "estudiantes":
            if not isinstance(hash_, str) or not HASH_VALIDO.match(hash_):
                raise cambiada
            formulario["carnet"] = "-"   # ya validado en la vista previa; el carnet real no viaja
        valores, errores = leer_formulario(catalogo, formulario, creando=nueva)
        if errores:
            raise cambiada
        cambios.append(Cambio(item["t"], int(item.get("n") or 0), formulario, valores, registro_id, hash_))
    return cambios


def aplicar_carga(db: Session, catalogo: Catalogo, cambios: list[Cambio]) -> int:
    """Escribe todo en un solo punto de guardado: si una fila falla, no queda nada a medias.
    `mensaje` convierte el error de la base en texto para la persona (lo da el router)."""
    from sqlalchemy import update  # noqa: PLC0415 - solo para el período vigente
    from sqlalchemy.exc import DBAPIError  # noqa: PLC0415
    vigente = None
    with db.begin_nested():
        for c in cambios:
            registro = catalogo.modelo() if c.tipo == "nueva" else db.get(catalogo.modelo, c.registro_id)
            if registro is None:
                raise ErrorCarga(f"Fila {c.fila}: el registro ya no existe. Vuelve a subir el archivo.")
            valores = dict(c.valores)
            if catalogo.slug == "estudiantes":
                valores.pop("carnet", None)
                if c.tipo == "nueva":
                    registro.carnet_hash = c.carnet_hash
            aplicar(catalogo, registro, valores)
            if c.tipo == "nueva":
                db.add(registro)
            try:
                db.flush()
            except DBAPIError as exc:
                exc.fila = c.fila  # type: ignore[attr-defined]
                raise
            if catalogo.slug == "periodos" and valores.get("activo"):
                vigente = registro
        if vigente is not None:
            db.execute(update(PeriodoAcademico).where(PeriodoAcademico.periodo_id != vigente.periodo_id)
                       .values(activo=False))
    return len(cambios)


# ---------------------------------------------------------------------------
# Lecturas de la base
# ---------------------------------------------------------------------------

def cargar_refs(db: Session, catalogo: Catalogo) -> dict:
    refs = {}
    for campo in catalogo.campos:
        if campo.tipo == "fk":
            modelo, atributo = REFERENCIAS[campo.nombre]
            clave = modelo.__mapper__.primary_key[0]
            refs[campo.nombre] = {str(getattr(o, atributo)).upper(): getattr(o, clave.name)
                                  for o in db.scalars(select(modelo)).all()}
    return refs


def cargar_existentes(db: Session, catalogo: Catalogo, filas_carnets: Optional[set] = None) -> dict:
    """{clave natural: valores actuales}. Estudiantes: solo los carnets que vienen en el archivo."""
    clave_pk = catalogo.modelo.__mapper__.primary_key[0].name
    consulta = select(catalogo.modelo)
    if catalogo.slug == "estudiantes":
        consulta = consulta.where(Estudiante.carnet_hash.in_(filas_carnets or {""}))
    existentes = {}
    for registro in db.scalars(consulta).all():
        actual = {c.nombre: getattr(registro, c.nombre) for c in catalogo.campos if not c.virtual}
        actual["_id"] = getattr(registro, clave_pk)
        if catalogo.slug == "estudiantes":
            clave = (registro.carnet_hash,)
        else:
            clave = tuple(actual[n] for n in CLAVE_NATURAL[catalogo.slug])
        existentes[clave] = actual
    return existentes


def carnets_del_archivo(filas: list[list[Any]]) -> set:
    """Hashes de la primera columna, para consultar solo esos estudiantes."""
    try:
        inicio = ubicar_cabecera(filas, "Carnet")
    except ErrorArchivo:
        return set()
    return {hash_carnet(_texto_de_celda(Campo("carnet", "Carnet"), (list(f) + [None])[0], {})[0])
            for f in filas[inicio + 1:] if f and f[0] not in (None, "")}


# ---------------------------------------------------------------------------
# Plantilla descargable
# ---------------------------------------------------------------------------

def _como_se_llena(campo: Campo) -> str:
    if campo.tipo == "entero":
        rango = f" de {campo.minimo} a {campo.maximo}" if campo.minimo is not None and campo.maximo is not None else ""
        texto = f"Número entero{rango}."
    elif campo.tipo == "fk":
        texto = "El código que aparece en la hoja Referencia (por ejemplo «ABC101»)."
    elif campo.tipo == "fecha":
        texto = "Fecha en formato AAAA-MM-DD (por ejemplo 2026-03-01)."
    elif campo.tipo == "bool":
        texto = "Sí o No." + (" Vacío cuenta como Sí." if campo.por_defecto else " Vacío cuenta como No.")
    elif campo.tipo == "opcion":
        texto = "Uno de: " + ", ".join(campo.opciones) + "."
    else:
        largo = f" de hasta {campo.maximo_largo} caracteres" if campo.maximo_largo else ""
        texto = f"Texto{largo}." + (" Se guarda en mayúsculas." if campo.mayusculas else "")
    return f"{texto} {campo.ayuda}".strip()


# Los ejemplos no deben coincidir con datos reales (la sección usa el número 99): copiados debajo de la
# cabecera tal cual, crean un registro nuevo en vez de actualizar uno existente.
# Fila de ejemplo de cada plantilla. Las referencias (período, materia, carrera…) no se fijan
# aquí: se toma la primera de las que existen en la base, para que el ejemplo sea válido.
EJEMPLOS = {
    "periodos": {"codigo_periodo": "2027-I", "anio": 2027, "ciclo_romano": "I", "fecha_inicio": "2027-02-01",
                 "fecha_fin": "2027-06-30", "activo": "No"},
    "secciones": {"numero_seccion": 99, "turno": "MATUTINO", "aula": "A-12", "cupo_maximo": 40},
    "materias": {"codigo_materia": "MAT101", "nombre": "Matemática I", "unidades_valorativas": 4, "ciclo_plan": 1,
                 "activo": "Sí"},
    "docentes": {"codigo_docente": "DOC-021", "escalafon": "HORA CLASE", "activo": "Sí"},
    "estudiantes": {"carnet": "AB26001", "anio_ingreso": 2026, "trabaja": "No", "condicion_academica": "REGULAR",
                    "activo": "Sí"},
    "carreras": {"codigo_carrera": "ISI", "nombre": "Ingeniería en Sistemas Informáticos", "plan_anio": 2024,
                 "total_uv_carrera": 190, "activo": "Sí"},
    "departamentos": {"codigo_departamento": "DCC", "nombre": "Departamento de Ciencias de la Computación"},
}


def _fila_ejemplo(catalogo: Catalogo, referencias: dict) -> list:
    """Valores de ejemplo en el orden de las columnas. referencias: {campo_fk: [«CÓD · nombre», …]}."""
    base = EJEMPLOS[catalogo.slug]
    fila = []
    for campo in catalogo.campos:
        if campo.tipo == "fk":
            opciones = referencias.get(campo.nombre) or []
            fila.append(codigo_de_referencia(opciones[0]) if opciones else "CÓDIGO")
        else:
            fila.append(base.get(campo.nombre, ""))
    return fila


def construir_plantilla(db: Session, catalogo: Catalogo) -> bytes:
    """Excel con la cabecera del catálogo, validaciones de lista y las hojas Guía y Referencia."""
    from .importar import plantilla_xlsx  # noqa: PLC0415

    validaciones: dict[int, tuple] = {}
    for indice, campo in enumerate(catalogo.campos):
        if campo.tipo == "opcion":
            validaciones[indice] = ("lista", list(campo.opciones))
        elif campo.tipo == "bool":
            validaciones[indice] = ("lista", ["Sí", "No"])
        elif campo.tipo == "entero" and campo.minimo is not None and campo.maximo is not None:
            validaciones[indice] = ("decimal", campo.minimo, campo.maximo)

    columnas_fk = [(c.etiqueta, [etiqueta for _, etiqueta in c.fk(db)]) for c in catalogo.campos if c.tipo == "fk"]
    referencias = {c.nombre: valores for c, (_, valores) in
                   zip([c for c in catalogo.campos if c.tipo == "fk"], columnas_fk)}
    ejemplo = _fila_ejemplo(catalogo, referencias)
    guia = [["Campo", "Obligatorio", "Qué escribir", "Ejemplo"]] + [
        [c.etiqueta, "Sí" if c.requerido and c.tipo != "bool" else "No", _como_se_llena(c), valor]
        for c, valor in zip(catalogo.campos, ejemplo)]
    hojas = {"Guía": guia}
    if columnas_fk:
        alto = max(len(valores) for _, valores in columnas_fk)
        hojas["Referencia"] = [[nombre for nombre, _ in columnas_fk]] + [
            [valores[i] if i < len(valores) else None for _, valores in columnas_fk] for i in range(alto)]

    clave = " + ".join(c.etiqueta for c in catalogo.campos if c.nombre in CLAVE_NATURAL[catalogo.slug]) or "Carnet"
    return plantilla_xlsx(
        f"Carga masiva · {catalogo.titulo}",
        f"Una fila por {catalogo.singular}, debajo de la cabecera (la fila amarilla es solo un ejemplo). Si ya existe "
        f"un registro con el mismo {clave}, la fila lo actualiza; si no, crea uno nuevo. No cambies la cabecera. "
        "Dudas: hojas «Guía»" + (" y «Referencia»." if columnas_fk else "."),
        cabeceras(catalogo), [], validaciones=validaciones, hojas_extra=hojas, ejemplo=ejemplo,
        anchos=[max(len(c.etiqueta) + 6, 16) for c in catalogo.campos])
