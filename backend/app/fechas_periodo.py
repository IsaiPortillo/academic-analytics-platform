"""Las fechas de asistencia y evaluaciones deben caer dentro del ciclo de su sección.

Sin esta regla, una clase de 2022-I podía quedar fechada en 2026 y los reportes
por mes, semana o día la contaban en el mes equivocado. La asistencia, además,
no puede ser futura: registra algo que ya ocurrió. Una evaluación sí puede
programarse con anticipación.
"""

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from .models import PeriodoAcademico, Seccion


def periodo_de(db: Session, seccion: Seccion) -> PeriodoAcademico:
    return db.get(PeriodoAcademico, seccion.periodo_id)


def problema_fecha(periodo: PeriodoAcademico, fecha: date, *, permitir_futura: bool) -> Optional[str]:
    """None si la fecha es válida; si no, el motivo en una frase."""
    if not permitir_futura and fecha > date.today():
        return f"La fecha {fecha:%d/%m/%Y} es futura."
    if not (periodo.fecha_inicio <= fecha <= periodo.fecha_fin):
        return (f"La fecha {fecha:%d/%m/%Y} está fuera del ciclo {periodo.codigo_periodo} "
                f"({periodo.fecha_inicio:%d/%m/%Y} a {periodo.fecha_fin:%d/%m/%Y}).")
    return None
