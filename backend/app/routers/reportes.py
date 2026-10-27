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

from dataclasses import dataclass
from typing import Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import Session

from ..calculos import (
    ESTADO_RETIRADO,
    UMBRAL_FALTAS_RIESGO,
    UMBRAL_NOTA_APROBACION,
    conteo_asistencia,
    expresiones_nota_final,
    unir_evaluaciones_y_calificaciones,
)
from ..database import get_db
from ..exportar import Columna, Reporte, formatear, responder
from ..dependencies import UsuarioSesion, requiere_rol
from ..models import (
    Asistencia,
    Calificacion,
    Docente,
    Estudiante,
    Evaluacion,
    Inscripcion,
    Materia,
    PeriodoAcademico,
    Seccion,
)
from ..templating import templates

router = APIRouter(prefix="/reportes", tags=["reportes"])

# El reporte se ordena por faltas descendentes, así que el corte deja fuera los
# casos menos relevantes, no una porción arbitraria.
LIMITE_FILAS = 500

def _periodos(db: Session):
    return db.scalars(
        select(PeriodoAcademico).order_by(
            PeriodoAcademico.anio.desc(), PeriodoAcademico.ciclo_romano.desc()
        )
    ).all()


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
    presentes = conteo_asistencia("PRESENTE")
    ausentes = conteo_asistencia("AUSENTE")
    justificados = conteo_asistencia("JUSTIFICADO")

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

    El cálculo en sí vive en app/calculos.py, compartido con el ETL (SCRUM-34):
    el reporte y el Data Warehouse no pueden discrepar en la nota de nadie.
    """
    ponderacion_evaluada, ponderacion_calificada, nota_final = expresiones_nota_final()

    consulta = unir_evaluaciones_y_calificaciones(
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
    )
    consulta = (
        consulta.where(
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
    return templates.TemplateResponse(
        request, "modulos/reportes.html",
        {"usuario": usuario, "adicionales": REPORTES_ADICIONALES},
    )


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
# Exportación: CSV (SCRUM-26), Excel y PDF
#
# Cada reporte se arma una sola vez como un exportar.Reporte, y de ahí salen la
# pantalla y los tres archivos. Las descargas usan limite=None: entregan el
# periodo completo (la pantalla se corta en LIMITE_FILAS) respetando los filtros
# activos, así que el archivo no puede discrepar de lo que se está viendo.
# ---------------------------------------------------------------------------

FORMATO = Query("csv", pattern="^(csv|xlsx|pdf)$")


def _periodo_vigente(db: Session, periodo_id: Optional[int]) -> Optional[int]:
    if periodo_id is None:
        periodos = _periodos(db)
        return periodos[0].periodo_id if periodos else None
    return periodo_id


def _filtro_periodo(db: Session, periodo_id: Optional[int]) -> tuple[str, str]:
    periodo = _periodo_por_id(db, periodo_id)
    return ("Período", periodo.codigo_periodo if periodo else "—")


def _filtro_materia(db: Session, materia_id: Optional[int]) -> tuple[str, str]:
    materia = db.get(Materia, materia_id) if materia_id else None
    return ("Materia", f"{materia.codigo_materia} — {materia.nombre}" if materia else "Todas")


def _fraccion(numerador, denominador) -> Optional[float]:
    return numerador / denominador if denominador else None


COLUMNAS_ASISTENCIA = [
    Columna("estudiante_id", "ID estudiante", "id", 0.9),
    Columna("codigo_materia", "Código", "texto", 0.8),
    Columna("materia", "Materia", "texto", 2.6),
    Columna("seccion", "Secc.", "id", 0.5),
    Columna("estado_inscripcion", "Estado", "texto", 1.1),
    Columna("sesiones", "Sesiones", "entero", 0.8),
    Columna("presentes", "Presentes", "entero", 0.8),
    Columna("ausentes", "Ausentes", "entero", 0.8),
    Columna("justificados", "Justificados", "entero", 0.9),
    Columna("porcentaje_asistencia", "Asistencia", "porcentaje", 0.9),
]

COLUMNAS_NOTAS = [
    Columna("estudiante_id", "ID estudiante", "id", 0.9),
    Columna("codigo_materia", "Código", "texto", 0.8),
    Columna("materia", "Materia", "texto", 2.6),
    Columna("seccion", "Secc.", "id", 0.5),
    Columna("estado_inscripcion", "Estado", "texto", 1.1),
    Columna("ponderacion_evaluada", "% evaluado", "decimal", 0.9),
    Columna("ponderacion_calificada", "% calificado", "decimal", 0.9),
    Columna("nota_final", "Nota final", "decimal", 0.8),
]


def reporte_asistencia(db: Session, periodo_id, materia_id=None, solo_riesgo=False) -> Reporte:
    filas = (consultar_asistencia_acumulada(db, periodo_id, materia_id, solo_riesgo, limite=None)
             if periodo_id else [])
    filtros = [_filtro_periodo(db, periodo_id), _filtro_materia(db, materia_id)]
    if solo_riesgo:
        filtros.append(("Filtro", f"{UMBRAL_FALTAS_RIESGO} o más faltas"))
    return Reporte(
        "Asistencia acumulada", "asistencia_acumulada", COLUMNAS_ASISTENCIA,
        [(f.estudiante_id, f.codigo_materia, f.materia, f.numero_seccion, f.estado_inscripcion,
          f.sesiones, f.presentes, f.ausentes, f.justificados, _fraccion(f.presentes, f.sesiones))
         for f in filas],
        filtros,
    )


def reporte_notas_finales(db: Session, periodo_id, materia_id=None, solo_reprobados=False) -> Reporte:
    filas = (consultar_notas_finales(db, periodo_id, materia_id, solo_reprobados, limite=None)
             if periodo_id else [])
    filtros = [_filtro_periodo(db, periodo_id), _filtro_materia(db, materia_id)]
    if solo_reprobados:
        filtros.append(("Filtro", f"Nota final menor a {UMBRAL_NOTA_APROBACION}"))
    return Reporte(
        "Notas finales por sección", "notas_finales", COLUMNAS_NOTAS,
        [(f.estudiante_id, f.codigo_materia, f.materia, f.numero_seccion, f.estado_inscripcion,
          f.ponderacion_evaluada, f.ponderacion_calificada, f.nota_final) for f in filas],
        filtros,
    )


@router.get("/asistencia/exportar")
def exportar_asistencia(
    formato: str = FORMATO,
    periodo_id: Optional[int] = Query(None),
    materia_id: Optional[int] = Query(None),
    solo_riesgo: bool = Query(False),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    periodo_id = _periodo_vigente(db, periodo_id)
    return responder(reporte_asistencia(db, periodo_id, materia_id, solo_riesgo), formato)


@router.get("/asistencia/csv")
def exportar_asistencia_csv(
    periodo_id: Optional[int] = Query(None),
    materia_id: Optional[int] = Query(None),
    solo_riesgo: bool = Query(False),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    """Se conserva la URL de SCRUM-26 para los enlaces que ya existían."""
    periodo_id = _periodo_vigente(db, periodo_id)
    return responder(reporte_asistencia(db, periodo_id, materia_id, solo_riesgo), "csv")


@router.get("/notas-finales/exportar")
def exportar_notas_finales(
    formato: str = FORMATO,
    periodo_id: Optional[int] = Query(None),
    materia_id: Optional[int] = Query(None),
    solo_reprobados: bool = Query(False),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    periodo_id = _periodo_vigente(db, periodo_id)
    return responder(reporte_notas_finales(db, periodo_id, materia_id, solo_reprobados), formato)


@router.get("/notas-finales/csv")
def exportar_notas_finales_csv(
    periodo_id: Optional[int] = Query(None),
    materia_id: Optional[int] = Query(None),
    solo_reprobados: bool = Query(False),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    """Se conserva la URL de SCRUM-26 para los enlaces que ya existían."""
    periodo_id = _periodo_vigente(db, periodo_id)
    return responder(reporte_notas_finales(db, periodo_id, materia_id, solo_reprobados), "csv")


# ---------------------------------------------------------------------------
# Reportes adicionales por período
#
# Rendimiento por materia y por docente usan la misma nota final ponderada que
# el reporte de notas (app/calculos.py) y el mismo criterio de "con nota final":
# inscripción FINALIZADO con todas sus evaluaciones calificadas.
# ---------------------------------------------------------------------------

def _notas_por_inscripcion(periodo_id: int):
    nf = expresiones_nota_final()
    return unir_evaluaciones_y_calificaciones(
        select(
            Inscripcion.inscripcion_id,
            Inscripcion.estado_inscripcion.label("estado"),
            Seccion.seccion_id,
            Seccion.materia_id,
            Seccion.docente_id,
            nf.ponderacion_evaluada.label("pe"),
            nf.ponderacion_calificada.label("pc"),
            nf.nota_final.label("nota"),
        )
        .select_from(Inscripcion)
        .join(Seccion, Inscripcion.seccion_id == Seccion.seccion_id)
        .where(Seccion.periodo_id == periodo_id)
    ).group_by(
        Inscripcion.inscripcion_id, Inscripcion.estado_inscripcion,
        Seccion.seccion_id, Seccion.materia_id, Seccion.docente_id,
    ).subquery()


def _medidas_rendimiento(n):
    cerrada = and_(n.c.estado == "FINALIZADO", n.c.pe > 0, n.c.pc >= n.c.pe)
    return [
        func.count(func.distinct(n.c.seccion_id)).label("secciones"),
        func.count().label("inscritos"),
        func.count().filter(n.c.estado == ESTADO_RETIRADO).label("retirados"),
        func.count().filter(cerrada).label("con_nota"),
        func.count().filter(and_(cerrada, n.c.nota >= UMBRAL_NOTA_APROBACION)).label("aprobados"),
        func.count().filter(and_(cerrada, n.c.nota < UMBRAL_NOTA_APROBACION)).label("reprobados"),
        func.round(func.avg(n.c.nota).filter(cerrada), 2).label("nota_promedio"),
    ]


COLUMNAS_RENDIMIENTO = [
    Columna("secciones", "Secciones", "entero", 0.8),
    Columna("inscritos", "Inscritos", "entero", 0.8),
    Columna("retirados", "Retirados", "entero", 0.8),
    Columna("con_nota_final", "Con nota final", "entero", 0.9),
    Columna("aprobados", "Aprobados", "entero", 0.8),
    Columna("reprobados", "Reprobados", "entero", 0.8),
    Columna("tasa_reprobacion", "Tasa de reprobación", "porcentaje", 1.0),
    Columna("nota_promedio", "Nota promedio", "decimal", 0.9),
]


def _filas_rendimiento(registros, claves):
    filas = [tuple(getattr(r, c) for c in claves) + (
        r.secciones, r.inscritos, r.retirados, r.con_nota, r.aprobados, r.reprobados,
        _fraccion(r.reprobados, r.con_nota), r.nota_promedio,
    ) for r in registros]
    # Mayor tasa de reprobación primero.
    return sorted(filas, key=lambda f: (-(f[-2] or 0), f[0]))


def reporte_rendimiento_materias(db: Session, periodo_id: int) -> Reporte:
    n = _notas_por_inscripcion(periodo_id)
    registros = db.execute(
        select(Materia.codigo_materia, Materia.nombre, *_medidas_rendimiento(n))
        .select_from(n).join(Materia, Materia.materia_id == n.c.materia_id)
        .group_by(Materia.materia_id, Materia.codigo_materia, Materia.nombre)
    ).all()
    return Reporte(
        "Rendimiento por materia", "rendimiento_por_materia",
        [Columna("codigo_materia", "Código", "texto", 0.8),
         Columna("materia", "Materia", "texto", 2.4)] + COLUMNAS_RENDIMIENTO,
        _filas_rendimiento(registros, ("codigo_materia", "nombre")),
        [_filtro_periodo(db, periodo_id)],
    )


def reporte_rendimiento_docentes(db: Session, periodo_id: int) -> Reporte:
    n = _notas_por_inscripcion(periodo_id)
    registros = db.execute(
        select(Docente.codigo_docente, Docente.escalafon, *_medidas_rendimiento(n))
        .select_from(n).join(Docente, Docente.docente_id == n.c.docente_id)
        .group_by(Docente.docente_id, Docente.codigo_docente, Docente.escalafon)
    ).all()
    return Reporte(
        "Desempeño por docente", "desempeno_por_docente",
        [Columna("codigo_docente", "Docente", "texto", 0.9),
         Columna("escalafon", "Escalafón", "texto", 1.1)] + COLUMNAS_RENDIMIENTO,
        _filas_rendimiento(registros, ("codigo_docente", "escalafon")),
        [_filtro_periodo(db, periodo_id)],
    )


def reporte_ocupacion_secciones(db: Session, periodo_id: int) -> Reporte:
    activos = func.count(Inscripcion.inscripcion_id).filter(
        Inscripcion.estado_inscripcion != ESTADO_RETIRADO)
    retirados = func.count(Inscripcion.inscripcion_id).filter(
        Inscripcion.estado_inscripcion == ESTADO_RETIRADO)
    registros = db.execute(
        select(Materia.codigo_materia, Materia.nombre, Seccion.numero_seccion, Seccion.turno,
               Docente.codigo_docente, Seccion.cupo_maximo,
               activos.label("activos"), retirados.label("retirados"))
        .select_from(Seccion)
        .join(Materia, Materia.materia_id == Seccion.materia_id)
        .join(Docente, Docente.docente_id == Seccion.docente_id)
        .outerjoin(Inscripcion, Inscripcion.seccion_id == Seccion.seccion_id)
        .where(Seccion.periodo_id == periodo_id)
        .group_by(Seccion.seccion_id, Materia.materia_id, Docente.docente_id)
    ).all()
    filas = sorted(
        ((r.codigo_materia, r.nombre, r.numero_seccion, r.turno.capitalize(), r.codigo_docente,
          r.cupo_maximo, r.activos, r.retirados, _fraccion(r.activos, r.cupo_maximo))
         for r in registros),
        key=lambda f: (-(f[-1] or 0), f[0], f[2]),
    )
    return Reporte(
        "Ocupación de secciones", "ocupacion_de_secciones",
        [
            Columna("codigo_materia", "Código", "texto", 0.8),
            Columna("materia", "Materia", "texto", 2.4),
            Columna("seccion", "Secc.", "id", 0.5),
            Columna("turno", "Turno", "texto", 0.9),
            Columna("codigo_docente", "Docente", "texto", 0.9),
            Columna("cupo_maximo", "Cupo", "entero", 0.6),
            Columna("inscritos_activos", "Inscritos activos", "entero", 1.0),
            Columna("retirados", "Retirados", "entero", 0.8),
            Columna("ocupacion", "Ocupación", "porcentaje", 0.9),
        ],
        filas,
        [_filtro_periodo(db, periodo_id)],
    )


def reporte_notas_pendientes(db: Session, periodo_id: int) -> Reporte:
    no_retirada = Inscripcion.estado_inscripcion != ESTADO_RETIRADO
    evaluaciones = (select(Evaluacion.seccion_id, func.count().label("n"))
                    .group_by(Evaluacion.seccion_id).subquery())
    activos = (select(Inscripcion.seccion_id, func.count().label("n"))
               .where(no_retirada).group_by(Inscripcion.seccion_id).subquery())
    registradas = (select(Inscripcion.seccion_id, func.count(Calificacion.calificacion_id).label("n"))
                   .join(Calificacion, Calificacion.inscripcion_id == Inscripcion.inscripcion_id)
                   .where(no_retirada).group_by(Inscripcion.seccion_id).subquery())
    registros = db.execute(
        select(Materia.codigo_materia, Materia.nombre, Seccion.numero_seccion, Docente.codigo_docente,
               func.coalesce(evaluaciones.c.n, 0).label("evaluaciones"),
               func.coalesce(activos.c.n, 0).label("activos"),
               func.coalesce(registradas.c.n, 0).label("registradas"))
        .select_from(Seccion)
        .join(Materia, Materia.materia_id == Seccion.materia_id)
        .join(Docente, Docente.docente_id == Seccion.docente_id)
        .outerjoin(evaluaciones, evaluaciones.c.seccion_id == Seccion.seccion_id)
        .outerjoin(activos, activos.c.seccion_id == Seccion.seccion_id)
        .outerjoin(registradas, registradas.c.seccion_id == Seccion.seccion_id)
        .where(Seccion.periodo_id == periodo_id)
    ).all()
    filas = []
    for r in registros:
        esperadas = r.evaluaciones * r.activos
        pendientes = esperadas - r.registradas
        # Pendiente: faltan notas, o hay estudiantes y la sección aún no tiene evaluaciones.
        if pendientes > 0 or (r.activos and not r.evaluaciones):
            filas.append((r.codigo_materia, r.nombre, r.numero_seccion, r.codigo_docente,
                          r.evaluaciones, r.activos, esperadas, r.registradas, pendientes,
                          _fraccion(r.registradas, esperadas)))
    filas.sort(key=lambda f: (-f[8], f[0], f[2]))
    return Reporte(
        "Notas pendientes de registro", "notas_pendientes",
        [
            Columna("codigo_materia", "Código", "texto", 0.8),
            Columna("materia", "Materia", "texto", 2.2),
            Columna("seccion", "Secc.", "id", 0.5),
            Columna("codigo_docente", "Docente", "texto", 0.9),
            Columna("evaluaciones", "Evaluaciones", "entero", 0.9),
            Columna("estudiantes_activos", "Estudiantes", "entero", 0.9),
            Columna("notas_esperadas", "Notas esperadas", "entero", 1.0),
            Columna("notas_registradas", "Registradas", "entero", 0.9),
            Columna("notas_pendientes", "Pendientes", "entero", 0.9),
            Columna("avance", "Avance", "porcentaje", 0.8),
        ],
        filas,
        [_filtro_periodo(db, periodo_id)],
    )


@dataclass(frozen=True)
class ReporteAdicional:
    titulo: str
    descripcion: str
    construir: Callable[[Session, int], Reporte]


REPORTES_ADICIONALES = {
    "rendimiento-materias": ReporteAdicional(
        "Rendimiento por materia",
        "Inscritos, retiros, aprobados y reprobados de cada materia, con su nota promedio.",
        reporte_rendimiento_materias),
    "desempeno-docentes": ReporteAdicional(
        "Desempeño por docente",
        "Secciones a cargo y resultados de sus estudiantes en el período.",
        reporte_rendimiento_docentes),
    "ocupacion-secciones": ReporteAdicional(
        "Ocupación de secciones",
        "Inscritos activos frente al cupo de cada sección.",
        reporte_ocupacion_secciones),
    "notas-pendientes": ReporteAdicional(
        "Notas pendientes de registro",
        "Secciones con calificaciones aún sin registrar, para dar seguimiento al cierre.",
        reporte_notas_pendientes),
}


def _adicional(slug: str) -> ReporteAdicional:
    if slug not in REPORTES_ADICIONALES:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    return REPORTES_ADICIONALES[slug]


@router.get("/{slug}/exportar")
def exportar_adicional(
    slug: str,
    formato: str = FORMATO,
    periodo_id: Optional[int] = Query(None),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    definicion = _adicional(slug)
    periodo_id = _periodo_vigente(db, periodo_id)
    if not periodo_id:
        return responder(Reporte(definicion.titulo, slug, [], [], []), formato)
    return responder(definicion.construir(db, periodo_id), formato)


@router.get("/{slug}")
def ver_adicional(
    request: Request,
    slug: str,
    periodo_id: Optional[int] = Query(None),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    definicion = _adicional(slug)
    periodos = _periodos(db)
    periodo_id = _periodo_vigente(db, periodo_id)
    reporte = definicion.construir(db, periodo_id) if periodo_id else None
    filas = [
        [(formatear(v, c.tipo), c.tipo) for c, v in zip(reporte.columnas, fila)]
        for fila in reporte.filas[:LIMITE_FILAS]
    ] if reporte else []
    return templates.TemplateResponse(
        request,
        "modulos/reporte_tabla.html",
        {
            "usuario": usuario,
            "slug": slug,
            "definicion": definicion,
            "reporte": reporte,
            "filas": filas,
            "total": len(reporte.filas) if reporte else 0,
            "limite_filas": LIMITE_FILAS,
            "periodos": periodos,
            "periodo_id": periodo_id,
        },
    )
