"""Módulo de calificaciones — SCRUM-8 (responsable: Isai Portillo).

Registro de evaluaciones (ponderación por sección) y de notas por inscripción,
más una vista de notas por sección con el acumulado ponderado.

La ponderación (<=100% por sección) y la auditoría de cambios de nota ya están
resueltas por triggers en la base (script 01); esta capa solo intenta la
operación y muestra el error que devuelve PostgreSQL cuando la rechaza — no
reimplementa esas reglas.

Nota de alcance: la GRANT de rol_docente sobre calificaciones/evaluaciones es a
nivel de tabla, sin políticas de fila que la limiten a sus propias secciones
(a diferencia de matrícula, aquí no hay ningún control de cupo o similar que ya
viva en la base). Por eso esta capa filtra explícitamente por
Seccion.docente_id en cada consulta y valida que las inscripciones enviadas en
el formulario de notas pertenezcan al roster de la sección — sin esa
validación, un docente podría enviar un inscripcion_id de otra sección y el
rol de base de datos no lo impediría.
"""

from decimal import Decimal, InvalidOperation
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import UsuarioSesion, requiere_rol
from ..models import Calificacion, Estudiante, Evaluacion, Inscripcion, Materia, PeriodoAcademico, Seccion
from ..templating import templates

router = APIRouter(prefix="/calificaciones", tags=["calificaciones"])

ESTADO_ACTIVO = "INSCRITO"


def _mensaje_amigable(exc: DBAPIError) -> str:
    """Extrae el mensaje del RAISE EXCEPTION / CHECK de PostgreSQL sin ruido del driver."""
    diag = getattr(exc.orig, "diag", None)
    if diag is not None and diag.message_primary:
        return diag.message_primary
    return "La base de datos rechazó la operación."


def _destino(periodo_id: int, seccion_id: Optional[int] = None, evaluacion_id: Optional[int] = None) -> str:
    url = f"/calificaciones?periodo_id={periodo_id}"
    if seccion_id:
        url += f"&seccion_id={seccion_id}"
    if evaluacion_id:
        url += f"&evaluacion_id={evaluacion_id}"
    return url


def _periodos(db: Session):
    return db.scalars(
        select(PeriodoAcademico).order_by(
            PeriodoAcademico.anio.desc(), PeriodoAcademico.ciclo_romano.desc()
        )
    ).all()


def _secciones_visibles(db: Session, periodo_id: int, usuario: UsuarioSesion):
    condiciones = [Seccion.periodo_id == periodo_id]
    if not usuario.es_coordinador:
        condiciones.append(Seccion.docente_id == usuario.docente_id)

    ponderacion_usada = func.coalesce(func.sum(Evaluacion.porcentaje), 0)
    return db.execute(
        select(Seccion, Materia, ponderacion_usada.label("ponderacion"))
        .join(Materia, Seccion.materia_id == Materia.materia_id)
        .outerjoin(Evaluacion, Evaluacion.seccion_id == Seccion.seccion_id)
        .where(*condiciones)
        .group_by(Seccion.seccion_id, Materia.materia_id)
        .order_by(Materia.codigo_materia, Seccion.numero_seccion)
    ).all()


def _seccion_permitida(db: Session, seccion_id: int, usuario: UsuarioSesion) -> Optional[Seccion]:
    seccion = db.get(Seccion, seccion_id)
    if seccion is None:
        return None
    if not usuario.es_coordinador and seccion.docente_id != usuario.docente_id:
        return None
    return seccion


def _evaluaciones_de_seccion(db: Session, seccion_id: int):
    return db.scalars(
        select(Evaluacion)
        .where(Evaluacion.seccion_id == seccion_id)
        .order_by(Evaluacion.fecha_evaluacion)
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


def _tabla_notas(db: Session, roster, evaluaciones):
    """Matriz estudiante x evaluación con la nota (o None) y el acumulado ponderado."""
    if not roster or not evaluaciones:
        return []

    inscripcion_ids = [inscripcion.inscripcion_id for inscripcion, _ in roster]
    calificaciones = db.scalars(
        select(Calificacion).where(Calificacion.inscripcion_id.in_(inscripcion_ids))
    ).all()
    notas = {(c.inscripcion_id, c.evaluacion_id): c.nota for c in calificaciones}

    filas = []
    for inscripcion, estudiante in roster:
        celdas = [notas.get((inscripcion.inscripcion_id, ev.evaluacion_id)) for ev in evaluaciones]
        acumulado = sum(
            (nota * ev.porcentaje / Decimal("100") for nota, ev in zip(celdas, evaluaciones) if nota is not None),
            Decimal("0.00"),
        )
        filas.append(
            {
                "estudiante": estudiante,
                "inscripcion": inscripcion,
                "celdas": celdas,
                "acumulado": acumulado.quantize(Decimal("0.01")),
            }
        )
    return filas


def _notas_de_evaluacion(db: Session, evaluacion_id: int, roster) -> dict:
    if not roster:
        return {}
    inscripcion_ids = [inscripcion.inscripcion_id for inscripcion, _ in roster]
    calificaciones = db.scalars(
        select(Calificacion).where(
            Calificacion.evaluacion_id == evaluacion_id,
            Calificacion.inscripcion_id.in_(inscripcion_ids),
        )
    ).all()
    return {c.inscripcion_id: c.nota for c in calificaciones}


@router.get("")
def inicio_calificaciones(
    request: Request,
    periodo_id: Optional[int] = Query(None),
    seccion_id: Optional[int] = Query(None),
    evaluacion_id: Optional[int] = Query(None),
    ok: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_docente", "rol_coordinador")),
    db: Session = Depends(get_db),
):
    periodos = _periodos(db)
    if periodo_id is None and periodos:
        periodo_id = periodos[0].periodo_id

    secciones = _secciones_visibles(db, periodo_id, usuario) if periodo_id else []

    seccion = None
    evaluaciones = []
    roster = []
    tabla = []
    evaluacion_actual = None
    notas_evaluacion_actual = {}
    if seccion_id:
        seccion = _seccion_permitida(db, seccion_id, usuario)
        if seccion and seccion.periodo_id != periodo_id:
            # Mismo caso que en matrícula: el filtro de periodo cambió sin
            # refrescar la sección, así que se ignora para no mostrar datos
            # de una sección de otro periodo.
            seccion = None
        if seccion:
            evaluaciones = _evaluaciones_de_seccion(db, seccion_id)
            roster = _roster(db, seccion_id)
            tabla = _tabla_notas(db, roster, evaluaciones)

            evaluacion_actual = next(
                (e for e in evaluaciones if e.evaluacion_id == evaluacion_id), None
            )
            if evaluacion_actual is None and evaluaciones:
                evaluacion_actual = evaluaciones[0]
            if evaluacion_actual:
                notas_evaluacion_actual = _notas_de_evaluacion(db, evaluacion_actual.evaluacion_id, roster)

    ponderacion_usada = sum((e.porcentaje for e in evaluaciones), Decimal("0.00"))

    return templates.TemplateResponse(
        request,
        "modulos/calificaciones.html",
        {
            "usuario": usuario,
            "periodos": periodos,
            "periodo_id": periodo_id,
            "secciones": secciones,
            "seccion_id": seccion_id,
            "seccion": seccion,
            "evaluaciones": evaluaciones,
            "ponderacion_usada": ponderacion_usada,
            "roster": roster,
            "tabla": tabla,
            "evaluacion_actual": evaluacion_actual,
            "notas_evaluacion_actual": notas_evaluacion_actual,
            "ok": ok,
            "error": error,
        },
    )


@router.post("/evaluaciones")
def crear_evaluacion(
    periodo_id: int = Form(...),
    seccion_id: int = Form(...),
    nombre_evaluacion: str = Form(...),
    porcentaje: Decimal = Form(...),
    fecha_evaluacion: date = Form(...),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_docente", "rol_coordinador")),
    db: Session = Depends(get_db),
):
    destino = _destino(periodo_id, seccion_id)

    seccion = _seccion_permitida(db, seccion_id, usuario)
    if seccion is None:
        return RedirectResponse(f"{destino}&error=Sección no encontrada", status_code=303)

    nombre_evaluacion = nombre_evaluacion.strip()
    if not nombre_evaluacion:
        return RedirectResponse(f"{destino}&error=El nombre de la evaluación es obligatorio", status_code=303)

    try:
        db.add(
            Evaluacion(
                seccion_id=seccion_id,
                nombre_evaluacion=nombre_evaluacion,
                porcentaje=porcentaje,
                fecha_evaluacion=fecha_evaluacion,
            )
        )
        db.flush()
    except DBAPIError as exc:
        db.rollback()
        return RedirectResponse(f"{destino}&error={_mensaje_amigable(exc)}", status_code=303)

    return RedirectResponse(
        f"{destino}&ok=Evaluación «{nombre_evaluacion}» creada correctamente", status_code=303
    )


@router.post("/registrar")
def registrar_notas(
    periodo_id: int = Form(...),
    seccion_id: int = Form(...),
    evaluacion_id: int = Form(...),
    inscripcion_id: List[int] = Form(...),
    nota: List[str] = Form(...),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_docente", "rol_coordinador")),
    db: Session = Depends(get_db),
):
    destino = _destino(periodo_id, seccion_id, evaluacion_id)

    seccion = _seccion_permitida(db, seccion_id, usuario)
    if seccion is None:
        return RedirectResponse(f"{destino}&error=Sección no encontrada", status_code=303)

    evaluacion = db.get(Evaluacion, evaluacion_id)
    if evaluacion is None or evaluacion.seccion_id != seccion_id:
        return RedirectResponse(f"{destino}&error=Evaluación no encontrada", status_code=303)

    if len(inscripcion_id) != len(nota):
        return RedirectResponse(f"{destino}&error=Formulario de notas inconsistente", status_code=303)

    # Solo se aceptan inscripciones del roster real de la sección: la GRANT de
    # rol_docente es a nivel de tabla y no impide escribir sobre otra sección.
    ids_validos = {inscripcion.inscripcion_id for inscripcion, _ in _roster(db, seccion_id)}

    existentes = {
        c.inscripcion_id: c
        for c in db.scalars(
            select(Calificacion).where(Calificacion.evaluacion_id == evaluacion_id)
        ).all()
    }

    registradas = 0
    try:
        for insc_id, valor in zip(inscripcion_id, nota):
            if insc_id not in ids_validos:
                continue
            valor = valor.strip()
            if not valor:
                continue
            nota_decimal = Decimal(valor)

            calificacion = existentes.get(insc_id)
            if calificacion is not None:
                if calificacion.nota != nota_decimal:
                    calificacion.nota = nota_decimal  # el trigger de auditoría solo dispara si cambia
                    registradas += 1
            else:
                db.add(
                    Calificacion(
                        inscripcion_id=insc_id,
                        evaluacion_id=evaluacion_id,
                        nota=nota_decimal,
                    )
                )
                registradas += 1
        db.flush()
    except InvalidOperation:
        db.rollback()
        return RedirectResponse(f"{destino}&error=Una de las notas ingresadas no es un número válido", status_code=303)
    except DBAPIError as exc:
        db.rollback()
        return RedirectResponse(f"{destino}&error={_mensaje_amigable(exc)}", status_code=303)

    return RedirectResponse(f"{destino}&ok={registradas} nota(s) registrada(s)", status_code=303)
