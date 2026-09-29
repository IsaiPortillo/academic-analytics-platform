"""Extracción de las entidades operacionales — SCRUM-34.

Dos decisiones atraviesan todo el módulo:

1. Columnas explícitas, nunca SELECT *. Qué sale del OLTP es una decisión
   consciente columna por columna: si mañana alguien agrega una columna
   `nombre` a estudiantes, el ETL no la arrastra al Data Warehouse sin que
   nadie lo note. (La validación de anonimización lo vuelve a comprobar al
   final, pero la primera barrera es no pedirla.)

2. Las calificaciones y asistencias se extraen ya agregadas por inscripción,
   haciendo el GROUP BY en PostgreSQL. El grano del modelo dimensional es la
   inscripción (un estudiante cursando una sección), y traer ~130k notas y
   ~120k sesiones a Python para agregarlas aquí sería mover datos para nada —
   el mismo criterio que ya sigue el reporte de SCRUM-10. La nota final usa
   literalmente la misma expresión SQL que ese reporte (backend/app/calculos.py).
"""

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .conexiones import calculos_oltp, modelos_oltp


def _leer(sesion: Session, consulta) -> pd.DataFrame:
    # coerce_float convierte los NUMERIC (Decimal) a float: el análisis
    # posterior es estadístico, no contable.
    return pd.read_sql(consulta, sesion.connection(), coerce_float=True)


def extraer_estudiantes(sesion: Session) -> pd.DataFrame:
    m = modelos_oltp()
    return _leer(sesion, select(
        m.Estudiante.estudiante_id,
        m.Estudiante.carnet_hash,
        m.Estudiante.anio_ingreso,
        m.Estudiante.carrera_id,
        m.Estudiante.trabaja,
        m.Estudiante.condicion_academica,
        m.Estudiante.activo,
    ))


def extraer_materias(sesion: Session) -> pd.DataFrame:
    m = modelos_oltp()
    return _leer(sesion, select(
        m.Materia.materia_id,
        m.Materia.codigo_materia,
        m.Materia.nombre,
        m.Materia.unidades_valorativas,
        m.Materia.ciclo_plan,
        m.Materia.carrera_id,
        m.Materia.activo,
    ))


def extraer_periodos(sesion: Session) -> pd.DataFrame:
    m = modelos_oltp()
    return _leer(sesion, select(
        m.PeriodoAcademico.periodo_id,
        m.PeriodoAcademico.codigo_periodo,
        m.PeriodoAcademico.anio,
        m.PeriodoAcademico.ciclo_romano,
        m.PeriodoAcademico.fecha_inicio,
        m.PeriodoAcademico.fecha_fin,
    ))


def extraer_secciones(sesion: Session) -> pd.DataFrame:
    # Sin `aula`: no es insumo de ningún análisis. docente_id es una llave
    # sustituta interna, no un dato personal; codigo_docente no se extrae.
    m = modelos_oltp()
    return _leer(sesion, select(
        m.Seccion.seccion_id,
        m.Seccion.materia_id,
        m.Seccion.docente_id,
        m.Seccion.periodo_id,
        m.Seccion.numero_seccion,
        m.Seccion.turno,
        m.Seccion.cupo_maximo,
    ))


def extraer_inscripciones(sesion: Session) -> pd.DataFrame:
    m = modelos_oltp()
    return _leer(sesion, select(
        m.Inscripcion.inscripcion_id,
        m.Inscripcion.estudiante_id,
        m.Inscripcion.seccion_id,
        m.Inscripcion.fecha_inscripcion,
        m.Inscripcion.numero_intento,
        m.Inscripcion.estado_inscripcion,
    ))


def extraer_notas_por_inscripcion(sesion: Session) -> pd.DataFrame:
    """Nota final ponderada por inscripción, para todas las inscripciones.

    A diferencia del reporte de SCRUM-10, aquí no se filtran los RETIRADO ni se
    limita a un periodo: el ETL extrae todo y las reglas de limpieza deciden
    qué hacer con cada caso (ver transformacion.py). Agrega además cuántas
    evaluaciones de la sección quedaron sin nota, que el reporte no necesita.
    """
    m = modelos_oltp()
    nf = calculos_oltp().expresiones_nota_final()
    consulta = calculos_oltp().unir_evaluaciones_y_calificaciones(
        select(
            m.Inscripcion.inscripcion_id,
            func.count(m.Evaluacion.evaluacion_id).label("evaluaciones"),
            func.count(m.Calificacion.calificacion_id).label("evaluaciones_calificadas"),
            nf.ponderacion_evaluada.label("ponderacion_evaluada"),
            nf.ponderacion_calificada.label("ponderacion_calificada"),
            nf.nota_final.label("nota_final"),
        )
        .select_from(m.Inscripcion)
        .join(m.Seccion, m.Inscripcion.seccion_id == m.Seccion.seccion_id)
    ).group_by(m.Inscripcion.inscripcion_id)
    return _leer(sesion, consulta)


def extraer_asistencia_por_inscripcion(sesion: Session) -> pd.DataFrame:
    """Sesiones de asistencia agregadas por inscripción.

    INNER sobre asistencias a propósito: solo devuelve inscripciones con al
    menos una sesión registrada. Las que no tienen ninguna se distinguen en la
    transformación (porcentaje de asistencia desconocido, no 0 %).
    """
    m = modelos_oltp()
    conteo = calculos_oltp().conteo_asistencia
    return _leer(sesion, select(
        m.Asistencia.inscripcion_id,
        func.count(m.Asistencia.asistencia_id).label("sesiones"),
        conteo("PRESENTE").label("presentes"),
        conteo("AUSENTE").label("ausentes"),
        conteo("JUSTIFICADO").label("justificados"),
    ).group_by(m.Asistencia.inscripcion_id))


EXTRACTORES = {
    "estudiantes": extraer_estudiantes,
    "materias": extraer_materias,
    "periodos": extraer_periodos,
    "secciones": extraer_secciones,
    "inscripciones": extraer_inscripciones,
    "notas": extraer_notas_por_inscripcion,
    "asistencia": extraer_asistencia_por_inscripcion,
}


def extraer_oltp(sesion: Session) -> dict[str, pd.DataFrame]:
    """Ejecuta todos los extractores en una misma transacción REPEATABLE READ.

    Con el aislamiento por defecto (READ COMMITTED) cada SELECT vería su propia
    foto de la base: si un docente registra una nota entre la extracción de
    inscripciones y la de notas, los dos DataFrames no cuadrarían. En REPEATABLE
    READ todas las consultas leen el mismo instante, sin bloquear al OLTP.
    """
    sesion.connection(execution_options={"isolation_level": "REPEATABLE READ"})
    return {nombre: extractor(sesion) for nombre, extractor in EXTRACTORES.items()}
