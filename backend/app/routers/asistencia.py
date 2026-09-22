"""Módulo de asistencia — SCRUM-9 (responsable: Isai Portillo).

Registro de asistencia por sección y fecha de sesión, más un resumen de
faltas acumuladas por estudiante en la sección.

uq_inscripcion_sesion (una fila por inscripción y fecha_sesion) ya está
resuelto por la base; esta capa hace upsert (UPDATE si ya existe una marca
para esa inscripción+fecha, INSERT si no) en vez de reimplementar la regla,
igual que calificaciones.py con uq_inscripcion_evaluacion.

Nota de alcance: igual que en calificaciones.py, la GRANT de rol_docente sobre
asistencias es a nivel de tabla, sin políticas de fila que la limiten a sus
propias secciones. Por eso se valida que las inscripciones enviadas en el
formulario pertenezcan al roster real de la sección.
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import UsuarioSesion, requiere_rol
from ..models import Asistencia, Estudiante, Inscripcion, Materia, PeriodoAcademico, Seccion
from ..templating import templates

router = APIRouter(prefix="/asistencia", tags=["asistencia"])

ESTADO_ACTIVO = "INSCRITO"
ESTADOS_VALIDOS = ("PRESENTE", "AUSENTE", "JUSTIFICADO")


def _mensaje_amigable(exc: DBAPIError) -> str:
    """Extrae el mensaje del CHECK / trigger de PostgreSQL sin ruido del driver."""
    diag = getattr(exc.orig, "diag", None)
    if diag is not None and diag.message_primary:
        return diag.message_primary
    return "La base de datos rechazó la operación."


def _destino(periodo_id: int, seccion_id: Optional[int] = None, fecha_sesion: Optional[date] = None) -> str:
    url = f"/asistencia?periodo_id={periodo_id}"
    if seccion_id:
        url += f"&seccion_id={seccion_id}"
    if fecha_sesion:
        url += f"&fecha_sesion={fecha_sesion.isoformat()}"
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

    sesiones_registradas = func.count(func.distinct(Asistencia.fecha_sesion))
    return db.execute(
        select(Seccion, Materia, sesiones_registradas.label("sesiones"))
        .join(Materia, Seccion.materia_id == Materia.materia_id)
        .outerjoin(Inscripcion, Inscripcion.seccion_id == Seccion.seccion_id)
        .outerjoin(Asistencia, Asistencia.inscripcion_id == Inscripcion.inscripcion_id)
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


def _asistencias_de_sesion(db: Session, fecha_sesion: date, roster) -> dict:
    if not roster:
        return {}
    inscripcion_ids = [inscripcion.inscripcion_id for inscripcion, _ in roster]
    registros = db.scalars(
        select(Asistencia).where(
            Asistencia.fecha_sesion == fecha_sesion,
            Asistencia.inscripcion_id.in_(inscripcion_ids),
        )
    ).all()
    return {a.inscripcion_id: a.estado_asistencia for a in registros}


def _resumen_faltas(db: Session, roster):
    """Conteo de PRESENTE/AUSENTE/JUSTIFICADO por estudiante, todas las sesiones registradas."""
    if not roster:
        return []

    inscripcion_ids = [inscripcion.inscripcion_id for inscripcion, _ in roster]
    registros = db.scalars(
        select(Asistencia).where(Asistencia.inscripcion_id.in_(inscripcion_ids))
    ).all()

    conteos = {}
    for a in registros:
        conteo = conteos.setdefault(a.inscripcion_id, {estado: 0 for estado in ESTADOS_VALIDOS})
        conteo[a.estado_asistencia] += 1

    resumen = []
    for inscripcion, estudiante in roster:
        conteo = conteos.get(inscripcion.inscripcion_id, {estado: 0 for estado in ESTADOS_VALIDOS})
        resumen.append(
            {
                "estudiante": estudiante,
                "inscripcion": inscripcion,
                "presentes": conteo["PRESENTE"],
                "ausentes": conteo["AUSENTE"],
                "justificados": conteo["JUSTIFICADO"],
                "total_sesiones": sum(conteo.values()),
            }
        )
    return resumen


@router.get("")
def inicio_asistencia(
    request: Request,
    periodo_id: Optional[int] = Query(None),
    seccion_id: Optional[int] = Query(None),
    fecha_sesion: Optional[date] = Query(None),
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
    roster = []
    estados_sesion = {}
    resumen = []
    if seccion_id:
        seccion = _seccion_permitida(db, seccion_id, usuario)
        if seccion and seccion.periodo_id != periodo_id:
            # Mismo caso que en matrícula/calificaciones: el filtro de periodo
            # cambió sin refrescar la sección, así que se ignora.
            seccion = None
        if seccion:
            if fecha_sesion is None:
                fecha_sesion = date.today()
            roster = _roster(db, seccion_id)
            estados_sesion = _asistencias_de_sesion(db, fecha_sesion, roster)
            resumen = _resumen_faltas(db, roster)

    return templates.TemplateResponse(
        request,
        "modulos/asistencia.html",
        {
            "usuario": usuario,
            "periodos": periodos,
            "periodo_id": periodo_id,
            "secciones": secciones,
            "seccion_id": seccion_id,
            "seccion": seccion,
            "fecha_sesion": fecha_sesion,
            "roster": roster,
            "estados_sesion": estados_sesion,
            "estados_validos": ESTADOS_VALIDOS,
            "resumen": resumen,
            "ok": ok,
            "error": error,
        },
    )


@router.post("/registrar")
def registrar_asistencia(
    periodo_id: int = Form(...),
    seccion_id: int = Form(...),
    fecha_sesion: date = Form(...),
    inscripcion_id: List[int] = Form(...),
    estado: List[str] = Form(...),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_docente", "rol_coordinador")),
    db: Session = Depends(get_db),
):
    destino = _destino(periodo_id, seccion_id, fecha_sesion)

    seccion = _seccion_permitida(db, seccion_id, usuario)
    if seccion is None:
        return RedirectResponse(f"{destino}&error=Sección no encontrada", status_code=303)

    if len(inscripcion_id) != len(estado):
        return RedirectResponse(f"{destino}&error=Formulario de asistencia inconsistente", status_code=303)

    # Solo se aceptan inscripciones del roster real de la sección: la GRANT de
    # rol_docente es a nivel de tabla y no impide escribir sobre otra sección.
    ids_validos = {inscripcion.inscripcion_id for inscripcion, _ in _roster(db, seccion_id)}

    existentes = {
        a.inscripcion_id: a
        for a in db.scalars(
            select(Asistencia).where(
                Asistencia.fecha_sesion == fecha_sesion,
                Asistencia.inscripcion_id.in_(ids_validos),
            )
        ).all()
    }

    registradas = 0
    try:
        for insc_id, valor in zip(inscripcion_id, estado):
            if insc_id not in ids_validos:
                continue
            valor = valor.strip().upper()
            if valor not in ESTADOS_VALIDOS:
                continue  # casilla vacía o valor no reconocido: se omite, no se marca

            asistencia = existentes.get(insc_id)
            if asistencia is not None:
                if asistencia.estado_asistencia != valor:
                    asistencia.estado_asistencia = valor
                    registradas += 1
            else:
                db.add(
                    Asistencia(
                        inscripcion_id=insc_id,
                        fecha_sesion=fecha_sesion,
                        estado_asistencia=valor,
                    )
                )
                registradas += 1
        db.flush()
    except DBAPIError as exc:
        db.rollback()
        return RedirectResponse(f"{destino}&error={_mensaje_amigable(exc)}", status_code=303)

    return RedirectResponse(f"{destino}&ok={registradas} asistencia(s) registrada(s)", status_code=303)
