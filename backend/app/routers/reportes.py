"""Módulo de reportes operacionales — SCRUM-10.

Subtareas: SCRUM-24 (notas finales, pendiente) · SCRUM-25 (asistencia acumulada)
· SCRUM-26 (exportación CSV, pendiente).

A diferencia del resumen de faltas que vive dentro de asistencia.py —que es por
sección y lo usa el docente sobre su propio roster— este reporte es la vista del
coordinador: cruza todas las secciones de un periodo para detectar estudiantes en
riesgo por inasistencia.

La agregación se hace en PostgreSQL (GROUP BY + COUNT condicional), no trayendo
filas a Python: un periodo tiene decenas de miles de registros de asistencia y
materializarlos en memoria no escala. Es la misma forma de consulta que la
"Sentencia SQL de Prueba 2" de scripts/benchmark/04_explain_analyze_benchmarks.sql,
que ya tiene índices dedicados de la Fase 1.4 (idx_asistencias_inscripcion_estado
e idx_secciones_periodo).
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import UsuarioSesion, requiere_rol
from ..models import Asistencia, Estudiante, Inscripcion, Materia, PeriodoAcademico, Seccion
from ..templating import templates

router = APIRouter(prefix="/reportes", tags=["reportes"])

ESTADO_RETIRADO = "RETIRADO"

# Umbral de faltas a partir del cual se marca al estudiante en riesgo. Coincide
# con el HAVING del benchmark de la Fase 1.4 y con el badge rojo que ya usa el
# resumen por sección de asistencia.html, para que el equipo no vea dos criterios
# distintos de "muchas faltas" en la misma aplicación.
UMBRAL_FALTAS_RIESGO = 3

# El reporte se ordena por faltas descendentes, así que el corte deja fuera los
# casos menos relevantes, no una porción arbitraria.
LIMITE_FILAS = 500


def _periodos(db: Session):
    return db.scalars(
        select(PeriodoAcademico).order_by(
            PeriodoAcademico.anio.desc(), PeriodoAcademico.ciclo_romano.desc()
        )
    ).all()


def _materias_del_periodo(db: Session, periodo_id: int):
    return db.scalars(
        select(Materia)
        .join(Seccion, Seccion.materia_id == Materia.materia_id)
        .where(Seccion.periodo_id == periodo_id)
        .distinct()
        .order_by(Materia.codigo_materia)
    ).all()


def _conteo_por_estado(estado: str):
    return func.count(case((Asistencia.estado_asistencia == estado, 1)))


def consulta_asistencia_acumulada(
    periodo_id: int,
    materia_id: Optional[int] = None,
    solo_riesgo: bool = False,
    limite: Optional[int] = LIMITE_FILAS,
):
    """Arma el SELECT de asistencia acumulada por inscripción (estudiante + sección).

    Construir la consulta aparte de ejecutarla permite inspeccionar el SQL
    generado sin necesidad de una conexión abierta.
    """
    presentes = _conteo_por_estado("PRESENTE")
    ausentes = _conteo_por_estado("AUSENTE")
    justificados = _conteo_por_estado("JUSTIFICADO")

    consulta = (
        select(
            Estudiante.estudiante_id,
            Materia.codigo_materia,
            Materia.nombre.label("materia"),
            Seccion.numero_seccion,
            Inscripcion.estado_inscripcion,
            func.count(Asistencia.asistencia_id).label("sesiones"),
            presentes.label("presentes"),
            ausentes.label("ausentes"),
            justificados.label("justificados"),
        )
        .select_from(Inscripcion)
        .join(Seccion, Inscripcion.seccion_id == Seccion.seccion_id)
        .join(Materia, Seccion.materia_id == Materia.materia_id)
        .join(Estudiante, Inscripcion.estudiante_id == Estudiante.estudiante_id)
        # OUTER JOIN a propósito: una inscripción sin ninguna sesión registrada
        # también es información para el coordinador (el docente no ha pasado
        # lista), y con INNER JOIN esas filas desaparecerían del reporte.
        .outerjoin(Asistencia, Asistencia.inscripcion_id == Inscripcion.inscripcion_id)
        .where(
            Seccion.periodo_id == periodo_id,
            # Un estudiante retirado ya no está en riesgo de reprobar por
            # inasistencia: se excluye para que el reporte hable del presente.
            Inscripcion.estado_inscripcion != ESTADO_RETIRADO,
        )
        .group_by(
            Inscripcion.inscripcion_id,
            Estudiante.estudiante_id,
            Materia.codigo_materia,
            Materia.nombre,
            Seccion.numero_seccion,
            Inscripcion.estado_inscripcion,
        )
        .order_by(desc(ausentes), Materia.codigo_materia, Estudiante.estudiante_id)
    )

    if materia_id:
        consulta = consulta.where(Materia.materia_id == materia_id)
    if solo_riesgo:
        # HAVING y no WHERE: el filtro se aplica sobre el agregado, no sobre las
        # filas individuales de asistencia.
        consulta = consulta.having(ausentes >= UMBRAL_FALTAS_RIESGO)
    if limite:
        consulta = consulta.limit(limite)

    return consulta


def consultar_asistencia_acumulada(
    db: Session,
    periodo_id: int,
    materia_id: Optional[int] = None,
    solo_riesgo: bool = False,
    limite: Optional[int] = LIMITE_FILAS,
):
    """Ejecuta el reporte y devuelve las filas ya agregadas por la base.

    Es una función pública a propósito: SCRUM-26 (exportación CSV) debe
    reutilizarla en vez de reescribir la consulta, de modo que el CSV y la
    pantalla nunca discrepen. Para exportar el periodo completo, limite=None.
    """
    return db.execute(
        consulta_asistencia_acumulada(periodo_id, materia_id, solo_riesgo, limite)
    ).all()


@router.get("")
def inicio_reportes(
    request: Request,
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    return templates.TemplateResponse(request, "modulos/reportes.html", {"usuario": usuario})


@router.get("/asistencia")
def reporte_asistencia(
    request: Request,
    periodo_id: Optional[int] = Query(None),
    materia_id: Optional[int] = Query(None),
    solo_riesgo: bool = Query(False),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    periodos = _periodos(db)
    if periodo_id is None and periodos:
        periodo_id = periodos[0].periodo_id

    materias = _materias_del_periodo(db, periodo_id) if periodo_id else []
    filas = (
        consultar_asistencia_acumulada(db, periodo_id, materia_id, solo_riesgo)
        if periodo_id
        else []
    )

    return templates.TemplateResponse(
        request,
        "modulos/reporte_asistencia.html",
        {
            "usuario": usuario,
            "periodos": periodos,
            "periodo_id": periodo_id,
            "materias": materias,
            "materia_id": materia_id,
            "solo_riesgo": solo_riesgo,
            "filas": filas,
            "umbral_riesgo": UMBRAL_FALTAS_RIESGO,
            "limite_filas": LIMITE_FILAS,
            "truncado": len(filas) == LIMITE_FILAS,
        },
    )
