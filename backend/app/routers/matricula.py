"""Módulo de matrícula — SCRUM-7 (responsable: Edras Ariel Viera Lazo).

CRUD de inscripciones sobre academico_oltp.inscripciones:
  - "Retirar" es un UPDATE a estado_inscripcion='RETIRADO', nunca un DELETE:
    calificaciones/asistencias referencian inscripcion_id y el historial debe
    conservarse.
  - El cupo máximo NO tiene trigger en la base (a diferencia de la ponderación
    de evaluaciones), así que esta capa es la única que lo hace cumplir. Se
    bloquea la fila de la sección (SELECT ... FOR UPDATE) antes de contar los
    inscritos activos, para que dos matrículas simultáneas no lean el mismo
    cupo disponible y ambas lo den por válido.
  - uq_estudiante_seccion sí es del motor: si el estudiante ya tiene una fila
    RETIRADO para esa sección, se reactiva (no se puede insertar una segunda
    fila para el mismo par estudiante/sección) e incrementa numero_intento.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import UsuarioSesion, requiere_rol
from ..models import Estudiante, Inscripcion, Materia, PeriodoAcademico, Seccion
from ..templating import templates

router = APIRouter(prefix="/matricula", tags=["matrícula"])

ESTADO_ACTIVO = "INSCRITO"
ESTADO_RETIRADO = "RETIRADO"


def _destino(periodo_id: int, seccion_id: Optional[int] = None) -> str:
    url = f"/matricula?periodo_id={periodo_id}"
    if seccion_id:
        url += f"&seccion_id={seccion_id}"
    return url


def _periodos(db: Session):
    return db.scalars(
        select(PeriodoAcademico).order_by(
            PeriodoAcademico.anio.desc(), PeriodoAcademico.ciclo_romano.desc()
        )
    ).all()


def _secciones_de_periodo(db: Session, periodo_id: int):
    inscritos_activos = func.count(Inscripcion.inscripcion_id).filter(
        Inscripcion.estado_inscripcion == ESTADO_ACTIVO
    )
    return db.execute(
        select(Seccion, Materia, inscritos_activos.label("inscritos"))
        .join(Materia, Seccion.materia_id == Materia.materia_id)
        .outerjoin(Inscripcion, Inscripcion.seccion_id == Seccion.seccion_id)
        .where(Seccion.periodo_id == periodo_id)
        .group_by(Seccion.seccion_id, Materia.materia_id)
        .order_by(Materia.codigo_materia, Seccion.numero_seccion)
    ).all()


def _roster(db: Session, seccion_id: int):
    return db.execute(
        select(Inscripcion, Estudiante)
        .join(Estudiante, Inscripcion.estudiante_id == Estudiante.estudiante_id)
        .where(
            Inscripcion.seccion_id == seccion_id,
            Inscripcion.estado_inscripcion == ESTADO_ACTIVO,
        )
        .order_by(Estudiante.estudiante_id)
    ).all()


def _buscar_estudiantes(db: Session, termino: str):
    termino = termino.strip()
    if not termino:
        return []
    filtro = Estudiante.carnet_hash.ilike(f"%{termino}%")
    if termino.isdigit():
        filtro = (Estudiante.estudiante_id == int(termino)) | filtro
    return db.scalars(
        select(Estudiante).where(filtro, Estudiante.activo.is_(True)).limit(15)
    ).all()


@router.get("")
def inicio_matricula(
    request: Request,
    periodo_id: Optional[int] = Query(None),
    seccion_id: Optional[int] = Query(None),
    buscar: Optional[str] = Query(None),
    ok: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    periodos = _periodos(db)
    if periodo_id is None and periodos:
        periodo_id = periodos[0].periodo_id

    secciones = _secciones_de_periodo(db, periodo_id) if periodo_id else []

    seccion_actual = None
    roster = []
    if seccion_id:
        seccion_actual = db.get(Seccion, seccion_id)
        if seccion_actual and seccion_actual.periodo_id != periodo_id:
            # El filtro de periodo cambió sin refrescar la sección: se ignora
            # para no mostrar el roster de una sección de otro periodo.
            seccion_actual = None
        if seccion_actual:
            roster = _roster(db, seccion_id)

    resultados_busqueda = _buscar_estudiantes(db, buscar) if buscar else []

    return templates.TemplateResponse(
        request,
        "modulos/matricula.html",
        {
            "usuario": usuario,
            "periodos": periodos,
            "periodo_id": periodo_id,
            "secciones": secciones,
            "seccion_id": seccion_id,
            "seccion": seccion_actual,
            "roster": roster,
            "buscar": buscar or "",
            "resultados_busqueda": resultados_busqueda,
            "ok": ok,
            "error": error,
            "estado_activo": ESTADO_ACTIVO,
        },
    )


@router.post("/inscribir")
def inscribir(
    periodo_id: int = Form(...),
    seccion_id: int = Form(...),
    estudiante_id: int = Form(...),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    destino = _destino(periodo_id, seccion_id)

    seccion = db.execute(
        select(Seccion).where(Seccion.seccion_id == seccion_id).with_for_update()
    ).scalar_one_or_none()
    if seccion is None:
        return RedirectResponse(f"{destino}&error=Sección no encontrada", status_code=303)

    estudiante = db.get(Estudiante, estudiante_id)
    if estudiante is None:
        return RedirectResponse(f"{destino}&error=Estudiante no encontrado", status_code=303)

    existente = db.scalar(
        select(Inscripcion).where(
            Inscripcion.estudiante_id == estudiante_id,
            Inscripcion.seccion_id == seccion_id,
        )
    )
    if existente and existente.estado_inscripcion == ESTADO_ACTIVO:
        return RedirectResponse(
            f"{destino}&error=El estudiante {estudiante_id} ya está matriculado en esta sección",
            status_code=303,
        )

    inscritos_actuales = db.scalar(
        select(func.count())
        .select_from(Inscripcion)
        .where(
            Inscripcion.seccion_id == seccion_id,
            Inscripcion.estado_inscripcion == ESTADO_ACTIVO,
        )
    )
    if inscritos_actuales >= seccion.cupo_maximo:
        return RedirectResponse(
            f"{destino}&error=La sección alcanzó su cupo máximo ({seccion.cupo_maximo} estudiantes)",
            status_code=303,
        )

    try:
        if existente:
            # Ya existía una fila (RETIRADO): se reactiva como nuevo intento
            # en vez de insertar, porque uq_estudiante_seccion prohíbe una
            # segunda fila para el mismo par estudiante/sección.
            existente.estado_inscripcion = ESTADO_ACTIVO
            existente.numero_intento += 1
        else:
            db.add(
                Inscripcion(
                    estudiante_id=estudiante_id,
                    seccion_id=seccion_id,
                    estado_inscripcion=ESTADO_ACTIVO,
                )
            )
        db.flush()
    except IntegrityError:
        db.rollback()
        return RedirectResponse(
            f"{destino}&error=No se pudo matricular: la base de datos rechazó la operación",
            status_code=303,
        )

    return RedirectResponse(
        f"{destino}&ok=Estudiante {estudiante_id} matriculado correctamente", status_code=303
    )


@router.post("/retirar/{inscripcion_id}")
def retirar(
    inscripcion_id: int,
    periodo_id: int = Form(...),
    seccion_id: int = Form(...),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    destino = _destino(periodo_id, seccion_id)

    inscripcion = db.get(Inscripcion, inscripcion_id)
    if inscripcion is None or inscripcion.seccion_id != seccion_id:
        return RedirectResponse(f"{destino}&error=Inscripción no encontrada", status_code=303)
    if inscripcion.estado_inscripcion != ESTADO_ACTIVO:
        return RedirectResponse(
            f"{destino}&error=Esa inscripción ya estaba retirada", status_code=303
        )

    inscripcion.estado_inscripcion = ESTADO_RETIRADO

    return RedirectResponse(
        f"{destino}&ok=Estudiante {inscripcion.estudiante_id} retirado de la sección",
        status_code=303,
    )
