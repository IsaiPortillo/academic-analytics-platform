"""Verificación de anonimización antes de que algo salga hacia el DW — SCRUM-34.

El carnet ya llega hasheado con SHA-256 desde el generador (Fase 1.2), así que
el ETL no anonimiza: *verifica* que la anonimización se cumple. Tres barreras,
de la más estructural a la más empírica:

1. Lista blanca de columnas por conjunto de salida. Solo pueden salir las
   columnas enumeradas aquí; cualquier otra hace fallar el pipeline. Es lista
   blanca y no lista negra a propósito: una lista negra ("nombre", "email",
   ...) solo atrapa lo que alguien pensó de antemano. Con lista blanca, agregar
   una columna al DW exige editar este archivo, y ese diff es el que se revisa.

2. Validación de contenido: carnet_hash debe tener forma de SHA-256 (64
   caracteres hexadecimales) y ser único, y ninguna columna de texto puede
   contener algo con forma de carnet sin hashear, correo o DUI. Esto atrapa
   el caso en que la columna es legítima pero el dato no lo es — p. ej. un
   generador o una migración que dejara el carnet en claro dentro de
   carnet_hash.

3. Aislamiento de credenciales: rol_etl no puede leer academico_oltp.usuarios
   (nombres completos, hashes de contraseña). Se comprueba en vivo contra
   PostgreSQL, igual que verificar_conexiones.py comprueba el solo-lectura.

Si cualquiera falla, el pipeline se detiene antes de escribir nada.
"""

import re

import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from .conexiones import sesion_oltp

COLUMNAS_PERMITIDAS: dict[str, set[str]] = {
    "hechos_inscripcion": {
        "inscripcion_id", "estudiante_id", "seccion_id", "materia_id", "periodo_id",
        "docente_id", "fecha_inscripcion", "numero_intento", "estado_inscripcion",
        "resultado", "nota_final", "aprobado", "nota_completa",
        "ponderacion_evaluada", "ponderacion_calificada", "evaluaciones_sin_nota",
        "sesiones", "presentes", "ausentes", "justificados", "porcentaje_asistencia",
        "es_repeticion", "costo_inscripcion", "costo_reprobacion", "costo_repeticion",
        "turno", "patron_riesgo",
    },
    "estudiante_periodo": {
        "estudiante_id", "periodo_id", "materias_inscritas", "materias_retiradas",
        "materias_aprobadas", "materias_reprobadas", "uv_inscritas", "uv_aprobadas",
        "con_actividad", "promedio_periodo", "porcentaje_asistencia",
    },
    # Única dimensión sobre personas. Sin nombre, sin carnet en claro, sin
    # fecha de nacimiento ni datos de contacto: el OLTP tampoco los tiene.
    "estudiantes": {
        "estudiante_id", "carnet_hash", "anio_ingreso", "carrera_id", "trabaja",
        "condicion_academica", "activo", "periodos_inscritos",
        "periodos_con_actividad", "ultimo_periodo_activo", "sin_actividad",
    },
    "materias": {
        "materia_id", "codigo_materia", "nombre", "unidades_valorativas", "ciclo_plan",
        "carrera_id", "activo", "en_grafo", "area", "dependientes_directos",
        "dependientes_indirectos", "dependientes_totales", "prerrequisitos_directos",
        "longitud_cascada", "profundidad_prerrequisitos", "indice_bloqueo",
        "es_cuello_botella", "inscripciones", "retiros", "inscripciones_cerradas",
        "reprobados", "nota_promedio", "tasa_reprobacion", "tasa_retiro", "indice_impacto",
    },
    "periodos": {
        "periodo_id", "codigo_periodo", "anio", "ciclo_romano", "fecha_inicio", "fecha_fin",
        "orden", "costo_por_uv", "moneda", "fuente_costo",
    },
    "carreras": {
        "carrera_id", "codigo_carrera", "nombre_carrera", "departamento_id",
        "codigo_departamento", "nombre_departamento",
    },
    "secciones": {
        "seccion_id", "materia_id", "docente_id", "periodo_id", "numero_seccion",
        "turno", "cupo_maximo",
    },
    # Sin codigo_docente ni nombre: el OLTP no guarda nombres y el código es un
    # identificador institucional que ningún análisis necesita.
    "docentes": {
        "docente_id", "escalafon", "departamento_id", "codigo_departamento",
        "nombre_departamento", "activo",
    },
}

PATRON_SHA256 = re.compile(r"^[0-9a-f]{64}$")

# Formas de datos identificables que nunca deberían aparecer en un valor de
# texto. El carnet sigue el formato del generador (p. ej. US2300042); se busca
# como palabra completa para no confundirlo con un fragmento de un hash.
PATRONES_IDENTIFICABLES = {
    "carnet sin hashear": re.compile(r"\b[A-Z]{2}\d{5,7}\b"),
    "correo electrónico": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    "DUI": re.compile(r"\b\d{8}-\d\b"),
}


class ErrorAnonimizacion(Exception):
    """Algún dato identificable saldría del OLTP. No se debe cargar nada."""


def validar_columnas(datasets: dict[str, pd.DataFrame]) -> list[str]:
    errores = []
    for nombre, df in datasets.items():
        permitidas = COLUMNAS_PERMITIDAS.get(nombre)
        if permitidas is None:
            errores.append(f"'{nombre}': conjunto sin lista blanca declarada")
            continue
        sobrantes = sorted(set(df.columns) - permitidas)
        if sobrantes:
            errores.append(f"'{nombre}': columnas no autorizadas {sobrantes}")
    return errores


def validar_carnet_hash(estudiantes: pd.DataFrame) -> list[str]:
    errores = []
    hashes = estudiantes["carnet_hash"].astype("string")
    invalidos = ~hashes.str.fullmatch(PATRON_SHA256).fillna(False)
    if invalidos.any():
        errores.append(
            f"'estudiantes': {int(invalidos.sum())} carnet_hash sin forma de SHA-256 "
            "(¿carnet en claro?)"
        )
    if hashes.duplicated().any():
        errores.append("'estudiantes': carnet_hash duplicado")
    return errores


def escanear_contenido(datasets: dict[str, pd.DataFrame]) -> list[str]:
    errores = []
    for nombre, df in datasets.items():
        for columna in df.select_dtypes(include=["object", "string"]).columns:
            valores = df[columna].dropna().astype("string").drop_duplicates()
            for descripcion, patron in PATRONES_IDENTIFICABLES.items():
                coincidencias = valores[valores.str.contains(patron, regex=True)]
                if not coincidencias.empty:
                    errores.append(
                        f"'{nombre}.{columna}': {len(coincidencias)} valor(es) con forma "
                        f"de {descripcion}"
                    )
    return errores


def verificar_aislamiento_credenciales() -> list[str]:
    """Lo correcto es que PostgreSQL rechace la lectura de usuarios. Solo un
    rechazo por permisos (SQLSTATE 42501) cuenta: cualquier otro error, como
    una base apagada, no demuestra nada y se propaga."""
    with sesion_oltp() as sesion:
        try:
            sesion.execute(text("SELECT 1 FROM academico_oltp.usuarios LIMIT 1"))
        except DBAPIError as exc:
            if getattr(exc.orig, "pgcode", None) != "42501":
                raise
            return []
    return ["rol_etl puede leer academico_oltp.usuarios: revisa sus GRANT"]


def verificar_anonimizacion(datasets: dict[str, pd.DataFrame],
                            comprobar_permisos: bool = True) -> None:
    errores = validar_columnas(datasets)
    errores += validar_carnet_hash(datasets["estudiantes"])
    errores += escanear_contenido(datasets)
    if comprobar_permisos:
        errores += verificar_aislamiento_credenciales()
    if errores:
        raise ErrorAnonimizacion(
            "La salida del ETL contiene datos potencialmente identificables:\n  - "
            + "\n  - ".join(errores)
        )
