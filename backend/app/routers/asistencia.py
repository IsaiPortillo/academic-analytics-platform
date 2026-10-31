"""Módulo de asistencia — SCRUM-9 (responsable: Isai Portillo).

Registro de asistencia por sección y fecha de sesión, más un resumen de
faltas acumuladas por estudiante en la sección.

uq_inscripcion_sesion (una fila por inscripción y fecha_sesion) ya está
resuelto por la base; esta capa hace upsert (UPDATE si ya existe una marca
para esa inscripción+fecha, INSERT si no) en vez de reimplementar la regla,
igual que calificaciones.py con uq_inscripcion_evaluacion.

Buscar por carnet: la lista identifica a cada estudiante por su ID interno,
porque el sistema no guarda nombres ni el carnet (solo su hash). La traducción
está en app/busqueda_carnet.py, compartida con calificaciones, y va por POST
para que el carnet no quede en la URL.

Secciones del docente: igual que en calificaciones.py, el motor limita al
docente a la asistencia de sus secciones (database/oltp/16) y esta capa además
valida que las inscripciones del formulario sean del roster de la sección.
"""

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from ..avisos import redirigir, tomar_aviso
from ..busqueda_carnet import localizar
from ..database import get_db
from ..dependencies import UsuarioSesion, requiere_rol
from ..fechas_periodo import periodo_de, problema_fecha
from ..importar import (TIPO_XLSX, ErrorArchivo, como_entero, como_fecha, leer_filas, normalizar,
                        plantilla_xlsx, ubicar_cabecera)
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


def _roster(db: Session, seccion_id: int, incluir_finalizados: bool = False):
    # Con el acta cerrada las inscripciones pasan a FINALIZADO: se muestran para consulta.
    estados = (ESTADO_ACTIVO, "FINALIZADO") if incluir_finalizados else (ESTADO_ACTIVO,)
    return db.execute(
        select(Inscripcion, Estudiante)
        .join(Estudiante, Inscripcion.estudiante_id == Estudiante.estudiante_id)
        .where(
            Inscripcion.seccion_id == seccion_id,
            Inscripcion.estado_inscripcion.in_(estados),
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
    resaltar: Optional[int] = Query(None),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_docente", "rol_coordinador")),
    db: Session = Depends(get_db),
):
    ok, error = tomar_aviso(request)
    periodos = _periodos(db)
    if periodo_id is None and periodos:
        periodo_id = periodos[0].periodo_id

    secciones = _secciones_visibles(db, periodo_id, usuario) if periodo_id else []

    seccion = None
    materia = None
    roster = []
    estados_sesion = {}
    resumen = []
    sesiones = []
    periodo = None
    if seccion_id:
        seccion = _seccion_permitida(db, seccion_id, usuario)
        if seccion and seccion.periodo_id != periodo_id:
            # Mismo caso que en matrícula/calificaciones: el filtro de periodo
            # cambió sin refrescar la sección, así que se ignora.
            seccion = None
        if seccion:
            materia = db.get(Materia, seccion.materia_id)
            periodo = periodo_de(db, seccion)
            if fecha_sesion is None:
                # Hoy, o el último día del ciclo si ya terminó (o el primero si no empezó).
                fecha_sesion = min(max(date.today(), periodo.fecha_inicio), periodo.fecha_fin)
            roster = _roster(db, seccion_id, incluir_finalizados=seccion.acta_cerrada)
            estados_sesion = _asistencias_de_sesion(db, fecha_sesion, roster)
            resumen = _resumen_faltas(db, roster)
            sesiones = _sesiones_de_seccion(db, seccion_id)

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
            "materia": materia,
            "fecha_sesion": fecha_sesion,
            "periodo": periodo,
            "fecha_maxima": min(date.today(), periodo.fecha_fin) if periodo else None,
            "roster": roster,
            "estados_sesion": estados_sesion,
            "estados_validos": ESTADOS_VALIDOS,
            "resumen": resumen,
            "sesiones": sesiones,
            "resaltar": resaltar,
            "ok": ok,
            "error": error,
        },
    )


@router.post("/buscar")
def buscar_por_carnet(
    request: Request,
    periodo_id: int = Form(...),
    seccion_id: int = Form(...),
    carnet: str = Form(""),
    fecha_sesion: Optional[date] = Form(None),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_docente", "rol_coordinador")),
    db: Session = Depends(get_db),
):
    """Traduce un carnet al ID con el que la lista identifica al estudiante."""
    destino = _destino(periodo_id, seccion_id, fecha_sesion)

    seccion = _seccion_permitida(db, seccion_id, usuario)
    if seccion is None:
        return redirigir(request, destino, error="Sección no encontrada")

    # La lista solo dibuja las inscripciones finalizadas cuando el acta está
    # cerrada, así que lo visible no siempre es toda la sección.
    resultado = localizar(
        carnet,
        completo=[e for _, e in _roster(db, seccion_id, incluir_finalizados=True)],
        visible=[e for _, e in _roster(db, seccion_id, incluir_finalizados=seccion.acta_cerrada)],
    )
    if resultado.estudiante_id is None:
        return redirigir(request, destino, error=resultado.error)

    return redirigir(request, f"{destino}&resaltar={resultado.estudiante_id}", ok=resultado.ok)


@router.post("/registrar")
def registrar_asistencia(
    request: Request,
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
        return redirigir(request, destino, error="Sección no encontrada")

    if len(inscripcion_id) != len(estado):
        return redirigir(request, destino, error="Formulario de asistencia inconsistente")

    problema = problema_fecha(periodo_de(db, seccion), fecha_sesion, permitir_futura=False)
    if problema:
        return redirigir(request, destino, error=problema)

    # Solo se aceptan inscripciones del roster real de la sección. El motor ya
    # rechaza las de secciones ajenas (RLS); aquí se descartan antes de intentarlo.
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
        return redirigir(request, destino, error=f"{_mensaje_amigable(exc)}")

    return redirigir(request, destino, ok=f"{registradas} asistencia(s) registrada(s)")

# ---------------------------------------------------------------------------
# Sesiones registradas: listado y eliminación de una sesión completa
# ---------------------------------------------------------------------------

def _sesiones_de_seccion(db: Session, seccion_id: int):
    return db.execute(
        select(Asistencia.fecha_sesion, func.count().label("marcas"),
               func.count().filter(Asistencia.estado_asistencia == "AUSENTE").label("ausentes"))
        .join(Inscripcion, Inscripcion.inscripcion_id == Asistencia.inscripcion_id)
        .where(Inscripcion.seccion_id == seccion_id)
        .group_by(Asistencia.fecha_sesion)
        .order_by(Asistencia.fecha_sesion.desc())
    ).all()


@router.post("/sesion/eliminar")
def eliminar_sesion(
    request: Request,
    periodo_id: int = Form(...),
    seccion_id: int = Form(...),
    fecha_sesion: date = Form(...),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_docente", "rol_coordinador")),
    db: Session = Depends(get_db),
):
    destino = _destino(periodo_id, seccion_id, fecha_sesion)
    if _seccion_permitida(db, seccion_id, usuario) is None:
        return redirigir(request, destino, error="Sección no encontrada")
    try:
        registros = db.scalars(
            select(Asistencia)
            .join(Inscripcion, Inscripcion.inscripcion_id == Asistencia.inscripcion_id)
            .where(Inscripcion.seccion_id == seccion_id, Asistencia.fecha_sesion == fecha_sesion)
        ).all()
        for registro in registros:
            db.delete(registro)
        db.flush()  # el bloqueo de acta cerrada lo aplica el motor
    except DBAPIError as exc:
        db.rollback()
        return redirigir(request, destino, error=_mensaje_amigable(exc))
    return redirigir(request, destino,
                     ok=f"Sesión del {fecha_sesion:%d/%m/%Y} eliminada ({len(registros)} marca(s))")


# ---------------------------------------------------------------------------
# Plantilla e importación de asistencia
# ---------------------------------------------------------------------------

COLUMNA_ID = "ID estudiante"


@router.get("/plantilla")
def descargar_plantilla(
    seccion_id: int = Query(...),
    fecha_sesion: Optional[date] = Query(None),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_docente", "rol_coordinador")),
    db: Session = Depends(get_db),
):
    seccion = _seccion_permitida(db, seccion_id, usuario)
    if seccion is None:
        raise HTTPException(status_code=404, detail="Sección no encontrada")
    materia = db.get(Materia, seccion.materia_id)
    fecha = fecha_sesion or date.today()
    roster = _roster(db, seccion_id)
    actuales = _asistencias_de_sesion(db, fecha, roster)
    filas = [[e.estudiante_id, fecha.isoformat(), actuales.get(i.inscripcion_id, "")] for i, e in roster]
    contenido = plantilla_xlsx(
        f"Asistencia · {materia.codigo_materia} sección {seccion.numero_seccion}",
        "Una fila por estudiante y sesión. Fecha en formato AAAA-MM-DD; estado PRESENTE, AUSENTE o "
        "JUSTIFICADO. Para varias sesiones, copia las filas y cambia la fecha. No cambies la columna A.",
        [COLUMNA_ID, "Fecha (AAAA-MM-DD)", "Estado"],
        filas,
        validaciones={2: ("lista", list(ESTADOS_VALIDOS))},
        anchos=[14, 20, 16],
    )
    nombre = f"asistencia_{materia.codigo_materia}_s{seccion.numero_seccion}_{fecha.isoformat()}.xlsx".lower()
    return Response(contenido, media_type=TIPO_XLSX, headers={
        "Content-Disposition": f'attachment; filename="{nombre}"', "Cache-Control": "no-store"})


def analizar_importacion_asistencia(filas, roster, actuales, periodo=None):
    """actuales: {(inscripcion_id, fecha): estado}. Devuelve (cambios, errores).
    Con periodo, rechaza además las fechas fuera de su ciclo."""
    errores = []
    inicio = ubicar_cabecera(filas, COLUMNA_ID)
    inscripcion_de = {e.estudiante_id: i.inscripcion_id for i, e in roster}
    cambios, vistos = [], set()
    for numero, fila in enumerate(filas[inicio + 1:], start=inicio + 2):
        fila = list(fila) + [None] * 3
        estudiante_id = como_entero(fila[0])
        fecha = como_fecha(fila[1])
        estado = normalizar(fila[2]).upper()
        if estudiante_id is None:
            errores.append(f"Fila {numero}: el ID de estudiante «{fila[0]}» no es válido.")
            continue
        if estudiante_id not in inscripcion_de:
            errores.append(f"Fila {numero}: el estudiante {estudiante_id} no está inscrito en esta sección.")
            continue
        if fecha is None:
            errores.append(f"Fila {numero}: la fecha «{fila[1]}» no es válida (usa AAAA-MM-DD).")
            continue
        if fecha > date.today():
            errores.append(f"Fila {numero}: la fecha {fecha:%d/%m/%Y} es futura.")
            continue
        problema = problema_fecha(periodo, fecha, permitir_futura=False) if periodo else None
        if problema:
            errores.append(f"Fila {numero}: {problema[0].lower()}{problema[1:]}")
            continue
        if not estado:
            continue  # sin estado: no se registra nada para esa fila
        if estado not in ESTADOS_VALIDOS:
            errores.append(f"Fila {numero}: el estado «{fila[2]}» no es PRESENTE, AUSENTE ni JUSTIFICADO.")
            continue
        clave = (estudiante_id, fecha)
        if clave in vistos:
            errores.append(f"Fila {numero}: el estudiante {estudiante_id} se repite para el {fecha:%d/%m/%Y}.")
            continue
        vistos.add(clave)
        inscripcion_id = inscripcion_de[estudiante_id]
        antes = actuales.get((inscripcion_id, fecha))
        tipo = "nueva" if antes is None else ("igual" if antes == estado else "cambio")
        cambios.append({"inscripcion_id": inscripcion_id, "estudiante_id": estudiante_id, "fecha": fecha,
                        "antes": antes, "despues": estado, "tipo": tipo})
    return cambios, errores


def _asistencias_actuales(db: Session, roster) -> dict:
    ids = [i.inscripcion_id for i, _ in roster]
    if not ids:
        return {}
    return {(a.inscripcion_id, a.fecha_sesion): a.estado_asistencia
            for a in db.scalars(select(Asistencia).where(Asistencia.inscripcion_id.in_(ids))).all()}


@router.post("/importar")
async def importar_asistencia(
    request: Request,
    periodo_id: int = Form(...),
    seccion_id: int = Form(...),
    archivo: UploadFile = File(...),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_docente", "rol_coordinador")),
    db: Session = Depends(get_db),
):
    destino = _destino(periodo_id, seccion_id)
    seccion = _seccion_permitida(db, seccion_id, usuario)
    if seccion is None:
        return redirigir(request, destino, error="Sección no encontrada")
    if seccion.acta_cerrada:
        return redirigir(request, destino, error="El acta de esta sección está cerrada: no se puede importar asistencia.")
    roster = _roster(db, seccion_id)
    try:
        filas = await leer_filas(archivo)
        cambios, errores = analizar_importacion_asistencia(filas, roster, _asistencias_actuales(db, roster),
                                                           periodo_de(db, seccion))
    except ErrorArchivo as exc:
        return redirigir(request, destino, error=str(exc))
    pendientes = [c for c in cambios if c["tipo"] != "igual"]
    return templates.TemplateResponse(request, "modulos/importar_vista_previa.html", {
        "usuario": usuario,
        "titulo": "Importar asistencia",
        "subtitulo": f"{db.get(Materia, seccion.materia_id).codigo_materia} · sección {seccion.numero_seccion}",
        "archivo": archivo.filename,
        "columnas": ["Estudiante", "Fecha", "Registrado", "Nuevo"],
        "filas": [(c["tipo"], [c["estudiante_id"], f"{c['fecha']:%d/%m/%Y}",
                               (c["antes"] or "—").capitalize(), c["despues"].capitalize()])
                  for c in pendientes],
        "conteo": {t: sum(1 for c in cambios if c["tipo"] == t) for t in ("nueva", "cambio", "igual")},
        "errores": errores,
        "accion": "/asistencia/importar/confirmar",
        "ocultos": [("periodo_id", periodo_id), ("seccion_id", seccion_id)]
                   + [("cambio", f"{c['inscripcion_id']}:{c['fecha'].isoformat()}:{c['despues']}") for c in pendientes],
        "volver": destino,
    })


@router.post("/importar/confirmar")
def confirmar_importacion_asistencia(
    request: Request,
    periodo_id: int = Form(...),
    seccion_id: int = Form(...),
    cambio: List[str] = Form([]),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_docente", "rol_coordinador")),
    db: Session = Depends(get_db),
):
    destino = _destino(periodo_id, seccion_id)
    seccion = _seccion_permitida(db, seccion_id, usuario)
    if seccion is None:
        return redirigir(request, destino, error="Sección no encontrada")
    periodo = periodo_de(db, seccion)
    roster = _roster(db, seccion_id)
    validas = {i.inscripcion_id for i, _ in roster}
    actuales = {(a.inscripcion_id, a.fecha_sesion): a for a in db.scalars(
        select(Asistencia).where(Asistencia.inscripcion_id.in_(validas or [0]))).all()}
    nuevas = cambiadas = 0
    try:
        for texto_cambio in cambio:
            partes = texto_cambio.split(":")
            insc = como_entero(partes[0]) if len(partes) == 3 else None
            fecha = como_fecha(partes[1]) if len(partes) == 3 else None
            estado = partes[2] if len(partes) == 3 else None
            if (insc not in validas or fecha is None or estado not in ESTADOS_VALIDOS
                    or problema_fecha(periodo, fecha, permitir_futura=False)):
                db.rollback()
                return redirigir(request, destino,
                                 error="La importación cambió desde la vista previa: vuelve a subir el archivo.")
            existente = actuales.get((insc, fecha))
            if existente is None:
                db.add(Asistencia(inscripcion_id=insc, fecha_sesion=fecha, estado_asistencia=estado))
                nuevas += 1
            elif existente.estado_asistencia != estado:
                existente.estado_asistencia = estado
                cambiadas += 1
        db.flush()
    except DBAPIError as exc:
        db.rollback()
        return redirigir(request, destino, error=_mensaje_amigable(exc))
    return redirigir(request, destino,
                     ok=f"Importación aplicada: {nuevas} marca(s) nueva(s) y {cambiadas} corregida(s)")
