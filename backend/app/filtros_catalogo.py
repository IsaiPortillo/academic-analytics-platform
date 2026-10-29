"""Filtros, orden y paginación de las listas de Catálogos (Administración).

Cada catálogo declara qué se puede filtrar (departamento, carrera, ciclo del plan, turno,
condición…). De ahí salen los selectores de la pantalla, la lectura segura de la URL y la
consulta: un valor que no corresponde a ninguna opción se ignora (no rompe nada ni se
interpola en el SQL: siempre va como parámetro).

Filtros en cascada: las opciones de cada selector son solo las que existen en los registros
que dejan los DEMÁS filtros (y la búsqueda), con cuántos hay de cada una. Elegir un
departamento deja en «Carrera» solo las carreras de ese departamento; elegir una carrera
deja en «Departamento» el suyo; elegir un turno deja en «Docente» a quienes dan clases en ese
turno. Si cambiar un filtro deja sin sentido a otro ya elegido (la carrera de otro
departamento), ese se quita y se avisa.

Cada filtro es una expresión SQL por registro: una columna, o una subconsulta cuando el dato
vive en otra tabla (el departamento de una materia viene de su carrera).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional
from urllib.parse import urlencode

from sqlalchemy import collate, func, literal_column, select, text
from sqlalchemy.orm import Session

from .catalogos import CARRERAS, DEPARTAMENTOS, DOCENTES, PERIODOS, Catalogo
from .models import Carrera, Docente, Estudiante, Materia, PeriodoAcademico, Seccion

POR_PAGINA_OPCIONES = (25, 50, 100, 200)
POR_PAGINA = 50
SI_NO = (("1", "Sí"), ("0", "No"))
MAX_PASADAS = 4


@dataclass(frozen=True)
class Filtro:
    nombre: str                                   # parámetro de la URL
    etiqueta: str
    tipo: str                                     # fk | valores | opcion | bool
    expresion: Any = None                         # columna o subconsulta escalar por registro
    valores: tuple = ()                           # tipo opcion: los permitidos
    cargar: Optional[Callable[[Session], list]] = None   # tipo fk: [(id, texto)]


def _departamento_de(columna_carrera):
    return select(Carrera.departamento_id).where(Carrera.carrera_id == columna_carrera).scalar_subquery()


def _depto_de_la_materia(columna_materia):
    return (select(Carrera.departamento_id).join(Materia, Materia.carrera_id == Carrera.carrera_id)
            .where(Materia.materia_id == columna_materia).scalar_subquery())


def _carrera_de_la_materia(columna_materia):
    return select(Materia.carrera_id).where(Materia.materia_id == columna_materia).scalar_subquery()


def _depto(expresion):
    return Filtro("departamento_id", "Departamento", "fk", expresion, cargar=DEPARTAMENTOS)


def _activo(columna, etiqueta="Activo"):
    return Filtro("activo", etiqueta, "bool", columna)


FILTROS: dict[str, tuple[Filtro, ...]] = {
    "periodos": (
        Filtro("anio", "Año", "valores", PeriodoAcademico.anio),
        Filtro("ciclo_romano", "Ciclo", "opcion", PeriodoAcademico.ciclo_romano, valores=("I", "II", "EXTRA")),
        _activo(PeriodoAcademico.activo, "Vigente"),
    ),
    "secciones": (
        Filtro("periodo_id", "Período", "fk", Seccion.periodo_id, cargar=PERIODOS),
        _depto(_depto_de_la_materia(Seccion.materia_id)),
        Filtro("carrera_id", "Carrera", "fk", _carrera_de_la_materia(Seccion.materia_id), cargar=CARRERAS),
        Filtro("docente_id", "Docente", "fk", Seccion.docente_id, cargar=DOCENTES),
        Filtro("turno", "Turno", "opcion", Seccion.turno, valores=("MATUTINO", "VESPERTINO", "NOCTURNO")),
    ),
    "materias": (
        _depto(_departamento_de(Materia.carrera_id)),
        Filtro("carrera_id", "Carrera", "fk", Materia.carrera_id, cargar=CARRERAS),
        Filtro("ciclo_plan", "Ciclo del plan", "valores", Materia.ciclo_plan),
        _activo(Materia.activo),
    ),
    "docentes": (
        _depto(Docente.departamento_id),
        Filtro("escalafon", "Escalafón", "opcion", Docente.escalafon,
               valores=("HORA CLASE", "AUXILIAR", "ADJUNTO", "TITULAR")),
        _activo(Docente.activo),
    ),
    "estudiantes": (
        _depto(_departamento_de(Estudiante.carrera_id)),
        Filtro("carrera_id", "Carrera", "fk", Estudiante.carrera_id, cargar=CARRERAS),
        Filtro("anio_ingreso", "Año de ingreso", "valores", Estudiante.anio_ingreso),
        Filtro("condicion_academica", "Condición", "opcion", Estudiante.condicion_academica,
               valores=("REGULAR", "CONDICIONAL", "EGRESADO", "RETIRADO")),
        Filtro("trabaja", "Trabaja", "bool", Estudiante.trabaja),
        _activo(Estudiante.activo),
    ),
    "carreras": (
        _depto(Carrera.departamento_id),
        _activo(Carrera.activo),
    ),
    "departamentos": (),
}


def filtros_de(catalogo: Catalogo) -> tuple[Filtro, ...]:
    return FILTROS.get(catalogo.slug, ())


def _etiquetas(db: Session, filtro: Filtro) -> dict[str, str]:
    """valor de la URL -> texto, de TODAS las opciones posibles (sin mirar los demás filtros)."""
    if filtro.tipo == "fk":
        return {str(i): texto for i, texto in filtro.cargar(db)}
    if filtro.tipo == "bool":
        return dict(SI_NO)
    if filtro.tipo == "opcion":
        return {v: v.capitalize() for v in filtro.valores}
    return {}


def condicion(filtro: Filtro, crudo: str):
    """La condición SQL de un valor de la URL, o None si el valor no vale."""
    crudo = (crudo or "").strip()
    if not crudo:
        return None
    if filtro.tipo in ("fk", "valores"):
        return filtro.expresion == int(crudo) if crudo.lstrip("-").isdigit() else None
    if filtro.tipo == "bool":
        return filtro.expresion.is_(True) if crudo == "1" else filtro.expresion.is_(False) if crudo == "0" else None
    return filtro.expresion == crudo if crudo in filtro.valores else None


@dataclass
class Seleccion:
    """Lo que la persona pidió en la URL, ya depurado."""
    buscar: str = ""
    filtros: dict[str, str] = None            # nombre -> valor válido
    orden: Optional[str] = None
    descendente: bool = False
    por_pagina: int = POR_PAGINA
    pagina: int = 1

    def __post_init__(self):
        self.filtros = self.filtros or {}


def leer(catalogo: Catalogo, parametros: Mapping[str, str], por_defecto: Optional[Mapping[str, str]] = None) -> Seleccion:
    """Depura los parámetros de la URL. `por_defecto` aplica a un filtro que no vino en la URL
    (que venga vacío es una elección: «todos»)."""
    por_defecto = por_defecto or {}
    seleccion = Seleccion(buscar=(parametros.get("buscar") or "").strip()[:80])
    for filtro in filtros_de(catalogo):
        crudo = parametros.get(filtro.nombre, por_defecto.get(filtro.nombre))
        if crudo is not None and condicion(filtro, crudo) is not None:
            seleccion.filtros[filtro.nombre] = crudo.strip()
    ordenables = {c.nombre for c in catalogo.campos if not c.virtual} | {"id"}
    orden = (parametros.get("orden") or "").strip()
    if orden in ordenables:
        seleccion.orden = orden
        seleccion.descendente = parametros.get("dir") == "desc"
    try:
        por_pagina = int(parametros.get("por_pagina", POR_PAGINA))
    except ValueError:
        por_pagina = POR_PAGINA
    seleccion.por_pagina = por_pagina if por_pagina in POR_PAGINA_OPCIONES else POR_PAGINA
    pagina = (parametros.get("pagina") or "1").strip()
    seleccion.pagina = int(pagina) if pagina.isdigit() and int(pagina) > 0 else 1
    return seleccion


def aplicar(consulta, catalogo: Catalogo, seleccion: Seleccion):
    """Agrega los filtros a la consulta. (La búsqueda por texto la arma el router: depende del catálogo.)"""
    for filtro in filtros_de(catalogo):
        crudo = seleccion.filtros.get(filtro.nombre)
        if crudo is not None:
            consulta = consulta.where(condicion(filtro, crudo))
    return consulta


def contar_por_valor(db: Session, catalogo: Catalogo, filtro: Filtro, seleccion: "Seleccion", busqueda) -> dict[str, int]:
    """Cuántos registros hay de cada valor de `filtro` entre los que cumplen la búsqueda y todos los
    DEMÁS filtros (el propio no cuenta: así se ven las alternativas, no solo lo ya elegido)."""
    valor = filtro.expresion.label("valor")
    consulta = select(valor, func.count().label("n")).select_from(catalogo.modelo)
    if busqueda is not None:
        consulta = consulta.where(busqueda)
    for otro in filtros_de(catalogo):
        crudo = seleccion.filtros.get(otro.nombre)
        if otro.nombre != filtro.nombre and crudo is not None:
            consulta = consulta.where(condicion(otro, crudo))
    return {(str(v) if not isinstance(v, bool) else ("1" if v else "0")): n
            for v, n in db.execute(consulta.group_by(literal_column("valor"))).all() if v is not None}


def reconciliar(db: Session, catalogo: Catalogo, seleccion: "Seleccion", busqueda=None, *,
                contar=contar_por_valor) -> list[str]:
    """Quita de la selección los filtros que ya no tienen ningún registro con los demás (la carrera de otro
    departamento, tras cambiar el departamento). Devuelve las etiquetas de los que quitó.

    Si dos filtros chocan se quita el más específico: se revisan de atrás hacia adelante, y en cada catálogo
    el orden va de lo general (departamento) a lo particular (carrera, docente, turno)."""
    quitados: list[str] = []
    for _ in range(MAX_PASADAS):
        cambio = False
        for filtro in reversed(filtros_de(catalogo)):
            valor = seleccion.filtros.get(filtro.nombre)
            if valor is not None and not contar(db, catalogo, filtro, seleccion, busqueda).get(valor):
                del seleccion.filtros[filtro.nombre]
                quitados.append(filtro.etiqueta)
                cambio = True
        if not cambio:
            break
    return quitados


def facetas(db: Session, catalogo: Catalogo, seleccion: "Seleccion", busqueda=None, *,
            contar=contar_por_valor) -> list[dict]:
    """Los selectores de la pantalla: cada uno con sus opciones disponibles y cuántos registros trae cada una."""
    resultado = []
    for filtro in filtros_de(catalogo):
        cuentas = contar(db, catalogo, filtro, seleccion, busqueda)
        etiquetas = _etiquetas(db, filtro)
        if filtro.tipo in ("fk", "bool", "opcion"):
            orden = list(etiquetas)
        else:
            orden = sorted(cuentas, key=lambda v: int(v))
        opciones = [(v, f"{etiquetas.get(v, v)} ({cuentas[v]:,})") for v in orden if cuentas.get(v)]
        resultado.append({"nombre": filtro.nombre, "etiqueta": filtro.etiqueta, "opciones": opciones,
                          "valor": seleccion.filtros.get(filtro.nombre, ""), "total": sum(cuentas.values())})
    return resultado


COLACION_ES = "es-x-icu"
_colacion_disponible: Optional[bool] = None


def colacion(db: Session) -> Optional[str]:
    """La colación en español de ICU, si la base la tiene. La base de datos ordena por bytes
    (la imagen de PostgreSQL no trae la configuración regional): sin esto «Álgebra» queda después de
    «Zoología». Se consulta una vez; si no existe, se ordena como siempre en vez de fallar."""
    global _colacion_disponible
    if _colacion_disponible is None:
        _colacion_disponible = bool(db.scalar(
            text("SELECT EXISTS (SELECT 1 FROM pg_collation WHERE collname = :c)"), {"c": COLACION_ES}))
    return COLACION_ES if _colacion_disponible else None


def clausulas_de_orden(catalogo: Catalogo, seleccion: Seleccion, colacion_texto: Optional[str] = None):
    if not seleccion.orden:
        return list(catalogo.orden)
    modelo = catalogo.modelo
    columna = modelo.__mapper__.primary_key[0] if seleccion.orden == "id" else getattr(modelo, seleccion.orden)
    if colacion_texto and getattr(columna.type, "python_type", None) is str:
        columna = collate(columna, colacion_texto)
    principal = columna.desc() if seleccion.descendente else columna.asc()
    return [principal, modelo.__mapper__.primary_key[0].asc()]


def consulta_url(seleccion: Seleccion, *, quitar: tuple = (), **cambios) -> str:
    """Los parámetros de la selección como query string; `quitar` los omite y `cambios` los reemplaza."""
    datos: dict[str, Any] = {}
    if seleccion.buscar:
        datos["buscar"] = seleccion.buscar
    datos.update(seleccion.filtros)
    if seleccion.orden:
        datos["orden"] = seleccion.orden
        if seleccion.descendente:
            datos["dir"] = "desc"
    if seleccion.por_pagina != POR_PAGINA:
        datos["por_pagina"] = seleccion.por_pagina
    for nombre in quitar:
        datos.pop(nombre, None)
    for nombre, valor in cambios.items():
        if valor in (None, ""):
            datos.pop(nombre, None)
        else:
            datos[nombre] = valor
    return urlencode(datos)


def chips(db: Session, catalogo: Catalogo, seleccion: Seleccion, base: str, con_defecto: tuple = ()) -> list[dict]:
    """Un chip por cada filtro o búsqueda activa, con el enlace que lo quita.

    `con_defecto`: filtros que la pantalla rellena sola cuando no vienen en la URL (el período de
    las secciones). Quitarlos no basta con omitirlos —volverían a su valor por defecto—: el
    enlace los manda vacíos, que significa «todos»."""
    resultado = []
    if seleccion.buscar:
        resultado.append({"etiqueta": "Búsqueda", "texto": seleccion.buscar,
                          "quitar": f"{base}?{consulta_url(seleccion, quitar=('buscar',))}"})
    for filtro in filtros_de(catalogo):
        valor = seleccion.filtros.get(filtro.nombre)
        if valor is None:
            continue
        texto = _etiquetas(db, filtro).get(valor, valor)
        consulta = consulta_url(seleccion, quitar=(filtro.nombre,))
        if filtro.nombre in con_defecto:
            consulta = (consulta + "&" if consulta else "") + f"{filtro.nombre}="
        resultado.append({"etiqueta": filtro.etiqueta, "texto": texto, "quitar": f"{base}?{consulta}"})
    return resultado
