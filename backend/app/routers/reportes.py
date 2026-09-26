"""Módulo de reportes operacionales — SCRUM-10.

Subtareas: SCRUM-24 (notas finales por sección) · SCRUM-25 (asistencia acumulada)
· SCRUM-26 (exportación CSV).

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

import csv
from datetime import date
from decimal import Decimal
from typing import Iterable, Optional, Sequence

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import UsuarioSesion, requiere_rol
from ..models import (
    Asistencia,
    Calificacion,
    Estudiante,
    Evaluacion,
    Inscripcion,
    Materia,
    PeriodoAcademico,
    Seccion,
)
from ..templating import templates

router = APIRouter(prefix="/reportes", tags=["reportes"])

ESTADO_RETIRADO = "RETIRADO"

# Umbral de faltas a partir del cual se marca al estudiante en riesgo. Coincide
# con el HAVING del benchmark de la Fase 1.4 y con el badge rojo que ya usa el
# resumen por sección de asistencia.html, para que el equipo no vea dos criterios
# distintos de "muchas faltas" en la misma aplicación.
UMBRAL_FALTAS_RIESGO = 3

# Nota mínima para aprobar un curso (escala 0-10), la misma que usa el
# generador de datos sintéticos (scripts/generator/02_generador_datos_sinteticos.py)
# como media de aprobación.
UMBRAL_NOTA_APROBACION = Decimal("6.00")

# El reporte se ordena por faltas descendentes, así que el corte deja fuera los
# casos menos relevantes, no una porción arbitraria.
LIMITE_FILAS = 500

# Excel en Windows asume la codificación local si el archivo no lleva BOM, y los
# nombres de materia tienen acentos ("Álgebra Vectorial", "Matemática"). Sin esto
# el coordinador abre el CSV y ve "Ãlgebra".
BOM_UTF8 = "﻿"


def _periodos(db: Session):
    return db.scalars(
        select(PeriodoAcademico).order_by(
            PeriodoAcademico.anio.desc(), PeriodoAcademico.ciclo_romano.desc()
        )
    ).all()


class _LineaCSV:
    """Destino de csv.writer que devuelve la línea en vez de escribirla.

    csv.writer espera un objeto con write(); al devolver el texto podemos ir
    entregando el archivo línea por línea en lugar de armarlo completo en memoria.
    """

    def write(self, valor: str) -> str:
        return valor


def _generar_csv(cabeceras: Sequence[str], filas: Iterable[Sequence]):
    escritor = csv.writer(_LineaCSV())
    yield BOM_UTF8 + escritor.writerow(cabeceras)
    for fila in filas:
        yield escritor.writerow(fila)


def _respuesta_csv(nombre: str, periodo, cabeceras: Sequence[str], filas: Iterable[Sequence]):
    codigo = periodo.codigo_periodo if periodo else "sin-periodo"
    archivo = f"{nombre}_{codigo}_{date.today().isoformat()}.csv"
    return StreamingResponse(
        _generar_csv(cabeceras, filas),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{archivo}"'},
    )


def _periodo_por_id(db: Session, periodo_id: Optional[int]):
    return db.get(PeriodoAcademico, periodo_id) if periodo_id else None


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


def consulta_notas_finales(
    periodo_id: int,
    materia_id: Optional[int] = None,
    solo_reprobados: bool = False,
    limite: Optional[int] = LIMITE_FILAS,
):
    """Arma el SELECT de nota final ponderada por inscripción (estudiante + sección).

    Misma idea que "Sentencia SQL de Prueba 1" de
    scripts/benchmark/04_explain_analyze_benchmarks.sql (SUM(nota * porcentaje/100)
    agrupado por inscripción), pero con LEFT JOIN a evaluaciones/calificaciones
    en vez de INNER JOIN: una sección sin evaluaciones creadas, o un estudiante
    con evaluaciones aún sin calificar, también debe aparecer en el reporte del
    coordinador — con INNER JOIN esas inscripciones desaparecerían en silencio.
    """
    ponderacion_evaluada = func.coalesce(func.sum(Evaluacion.porcentaje), 0)
    ponderacion_calificada = func.coalesce(
        func.sum(case((Calificacion.nota.isnot(None), Evaluacion.porcentaje), else_=0)),
        0,
    )
    nota_final = func.round(
        func.coalesce(func.sum(Calificacion.nota * Evaluacion.porcentaje / 100), 0), 2
    )

    consulta = (
        select(
            Estudiante.estudiante_id,
            Materia.codigo_materia,
            Materia.nombre.label("materia"),
            Seccion.numero_seccion,
            Inscripcion.estado_inscripcion,
            ponderacion_evaluada.label("ponderacion_evaluada"),
            ponderacion_calificada.label("ponderacion_calificada"),
            nota_final.label("nota_final"),
        )
        .select_from(Inscripcion)
        .join(Seccion, Inscripcion.seccion_id == Seccion.seccion_id)
        .join(Materia, Seccion.materia_id == Materia.materia_id)
        .join(Estudiante, Inscripcion.estudiante_id == Estudiante.estudiante_id)
        .outerjoin(Evaluacion, Evaluacion.seccion_id == Seccion.seccion_id)
        .outerjoin(
            Calificacion,
            (Calificacion.evaluacion_id == Evaluacion.evaluacion_id)
            & (Calificacion.inscripcion_id == Inscripcion.inscripcion_id),
        )
        .where(
            Seccion.periodo_id == periodo_id,
            # Mismo criterio que asistencia: un retiro ya no es un resultado
            # académico que reportar.
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
        .order_by(nota_final, Materia.codigo_materia, Estudiante.estudiante_id)
    )

    if materia_id:
        consulta = consulta.where(Materia.materia_id == materia_id)
    if solo_reprobados:
        # HAVING sobre el agregado: se excluyen las secciones sin evaluaciones
        # creadas todavía (ponderacion_evaluada = 0), que de otro modo
        # aparecerían con nota_final = 0 y contaminarían el filtro.
        consulta = consulta.having(
            ponderacion_evaluada > 0, nota_final < UMBRAL_NOTA_APROBACION
        )
    if limite:
        consulta = consulta.limit(limite)

    return consulta


def consultar_notas_finales(
    db: Session,
    periodo_id: int,
    materia_id: Optional[int] = None,
    solo_reprobados: bool = False,
    limite: Optional[int] = LIMITE_FILAS,
):
    """Ejecuta el reporte de notas finales y devuelve las filas ya agregadas.

    Función pública por la misma razón que consultar_asistencia_acumulada:
    SCRUM-26 debe reutilizarla para exportar CSV en vez de reescribir la
    consulta. Para exportar el periodo completo, limite=None.
    """
    return db.execute(
        consulta_notas_finales(periodo_id, materia_id, solo_reprobados, limite)
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


@router.get("/notas-finales")
def reporte_notas_finales(
    request: Request,
    periodo_id: Optional[int] = Query(None),
    materia_id: Optional[int] = Query(None),
    solo_reprobados: bool = Query(False),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    periodos = _periodos(db)
    if periodo_id is None and periodos:
        periodo_id = periodos[0].periodo_id

    materias = _materias_del_periodo(db, periodo_id) if periodo_id else []
    filas = (
        consultar_notas_finales(db, periodo_id, materia_id, solo_reprobados)
        if periodo_id
        else []
    )

    return templates.TemplateResponse(
        request,
        "modulos/reporte_notas_finales.html",
        {
            "usuario": usuario,
            "periodos": periodos,
            "periodo_id": periodo_id,
            "materias": materias,
            "materia_id": materia_id,
            "solo_reprobados": solo_reprobados,
            "filas": filas,
            "umbral_aprobacion": UMBRAL_NOTA_APROBACION,
            "limite_filas": LIMITE_FILAS,
            "truncado": len(filas) == LIMITE_FILAS,
        },
    )


# ---------------------------------------------------------------------------
# SCRUM-26 — Exportación a CSV
#
# Ambas descargas reutilizan las mismas funciones de consulta que alimentan la
# pantalla, con limite=None: el CSV entrega el periodo completo (la pantalla se
# corta en LIMITE_FILAS por legibilidad) y respeta los filtros activos, de modo
# que el archivo nunca puede discrepar de lo que el coordinador está viendo.
#
# Las filas se obtienen antes de empezar a transmitir, a propósito: así el envío
# del cuerpo no depende de que la sesión de base de datos siga abierta. Son
# tuplas pequeñas y acotadas a un periodo, mientras que la parte que sí crece
# —el texto del CSV— se genera línea por línea.
# ---------------------------------------------------------------------------


@router.get("/asistencia/csv")
def exportar_asistencia_csv(
    periodo_id: Optional[int] = Query(None),
    materia_id: Optional[int] = Query(None),
    solo_riesgo: bool = Query(False),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    periodos = _periodos(db)
    if periodo_id is None and periodos:
        periodo_id = periodos[0].periodo_id

    filas = (
        consultar_asistencia_acumulada(db, periodo_id, materia_id, solo_riesgo, limite=None)
        if periodo_id
        else []
    )

    def _porcentaje(presentes: int, sesiones: int) -> str:
        return f"{presentes / sesiones * 100:.0f}" if sesiones else ""

    return _respuesta_csv(
        "asistencia_acumulada",
        _periodo_por_id(db, periodo_id),
        [
            "estudiante_id",
            "codigo_materia",
            "materia",
            "seccion",
            "estado_inscripcion",
            "sesiones",
            "presentes",
            "ausentes",
            "justificados",
            "porcentaje_asistencia",
        ],
        [
            (
                f.estudiante_id,
                f.codigo_materia,
                f.materia,
                f.numero_seccion,
                f.estado_inscripcion,
                f.sesiones,
                f.presentes,
                f.ausentes,
                f.justificados,
                _porcentaje(f.presentes, f.sesiones),
            )
            for f in filas
        ],
    )


@router.get("/notas-finales/csv")
def exportar_notas_finales_csv(
    periodo_id: Optional[int] = Query(None),
    materia_id: Optional[int] = Query(None),
    solo_reprobados: bool = Query(False),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    periodos = _periodos(db)
    if periodo_id is None and periodos:
        periodo_id = periodos[0].periodo_id

    filas = (
        consultar_notas_finales(db, periodo_id, materia_id, solo_reprobados, limite=None)
        if periodo_id
        else []
    )

    return _respuesta_csv(
        "notas_finales",
        _periodo_por_id(db, periodo_id),
        [
            "estudiante_id",
            "codigo_materia",
            "materia",
            "seccion",
            "estado_inscripcion",
            "ponderacion_evaluada",
            "ponderacion_calificada",
            "nota_final",
        ],
        [
            (
                f.estudiante_id,
                f.codigo_materia,
                f.materia,
                f.numero_seccion,
                f.estado_inscripcion,
                f.ponderacion_evaluada,
                f.ponderacion_calificada,
                f.nota_final,
            )
            for f in filas
        ],
    )
