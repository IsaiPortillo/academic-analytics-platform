"""Cálculos académicos compartidos por los reportes (SCRUM-10) y el ETL (SCRUM-34).

La nota final ponderada es una regla de negocio, no un detalle de un reporte:
si el reporte del coordinador y el Data Warehouse la calcularan cada uno a su
manera, tarde o temprano el dashboard mostraría una nota distinta a la que el
coordinador ve en pantalla para el mismo estudiante. Por eso vive aquí una sola
vez y ambos la importan.

Este módulo no depende de FastAPI a propósito: el ETL lo importa sin levantar
la aplicación web.
"""

from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import Select, case, func
from sqlalchemy.sql.elements import ColumnElement

from .models import Asistencia, Calificacion, Evaluacion, Inscripcion, Seccion

ESTADO_RETIRADO = "RETIRADO"

# Nota mínima para aprobar un curso (escala 0-10), la misma que usa el
# generador de datos sintéticos (scripts/generator/02_generador_datos_sinteticos.py)
# como media de aprobación.
UMBRAL_NOTA_APROBACION = Decimal("6.00")


class ExpresionesNotaFinal(NamedTuple):
    """Agregados de la nota final; se usan dentro de un GROUP BY por inscripción."""

    # Suma de porcentajes de las evaluaciones creadas en la sección.
    ponderacion_evaluada: ColumnElement
    # Suma de porcentajes de las evaluaciones que el estudiante ya tiene calificadas.
    ponderacion_calificada: ColumnElement
    # SUM(nota * porcentaje / 100). Una evaluación sin nota no suma: cuenta como 0.
    nota_final: ColumnElement


def expresiones_nota_final() -> ExpresionesNotaFinal:
    """Misma idea que "Sentencia SQL de Prueba 1" de
    scripts/benchmark/04_explain_analyze_benchmarks.sql, pensada para usarse
    junto con `unir_evaluaciones_y_calificaciones`.
    """
    return ExpresionesNotaFinal(
        ponderacion_evaluada=func.coalesce(func.sum(Evaluacion.porcentaje), 0),
        ponderacion_calificada=func.coalesce(
            func.sum(case((Calificacion.nota.isnot(None), Evaluacion.porcentaje), else_=0)),
            0,
        ),
        nota_final=func.round(
            func.coalesce(func.sum(Calificacion.nota * Evaluacion.porcentaje / 100), 0), 2
        ),
    )


def unir_evaluaciones_y_calificaciones(consulta: Select) -> Select:
    """Agrega los JOIN que necesitan las `expresiones_nota_final`.

    La consulta ya debe tener Inscripcion y Seccion en su FROM. Son LEFT JOIN y
    no INNER JOIN: una sección sin evaluaciones creadas, o un estudiante con
    evaluaciones aún sin calificar, también debe aparecer — con INNER JOIN esas
    inscripciones desaparecerían en silencio.
    """
    return consulta.outerjoin(
        Evaluacion, Evaluacion.seccion_id == Seccion.seccion_id
    ).outerjoin(
        Calificacion,
        (Calificacion.evaluacion_id == Evaluacion.evaluacion_id)
        & (Calificacion.inscripcion_id == Inscripcion.inscripcion_id),
    )


def conteo_asistencia(estado: str) -> ColumnElement:
    """COUNT condicional de sesiones de asistencia en un estado dado."""
    return func.count(case((Asistencia.estado_asistencia == estado, 1)))
