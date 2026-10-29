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

from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..avisos import redirigir, tomar_aviso
from ..database import get_db
from ..dependencies import UsuarioSesion, requiere_rol
from ..importar import TIPO_XLSX, ErrorArchivo, como_entero, leer_filas, normalizar, plantilla_xlsx, ubicar_cabecera
from ..models import Estudiante, Inscripcion, Materia, PeriodoAcademico, Seccion
from ..templating import templates

router = APIRouter(prefix="/matricula", tags=["matrícula"])

ESTADO_ACTIVO = "INSCRITO"
ESTADO_RETIRADO = "RETIRADO"

# Motivos de retiro: una lista cerrada permite contarlos en los reportes; el
# detalle libre es opcional.
MOTIVOS_RETIRO = (
    "Solicitud del estudiante",
    "Situación económica",
    "Motivos de salud",
    "Choque de horario",
    "Cambio de carrera o institución",
    "Carga laboral",
    "Bajo rendimiento",
    "Otro",
)


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


def _retirados(db: Session, seccion_id: int):
    return db.execute(
        select(Inscripcion, Estudiante)
        .join(Estudiante, Inscripcion.estudiante_id == Estudiante.estudiante_id)
        .where(Inscripcion.seccion_id == seccion_id, Inscripcion.estado_inscripcion == ESTADO_RETIRADO)
        .order_by(Inscripcion.fecha_retiro.desc().nulls_last(), Estudiante.estudiante_id)
    ).all()


def _buscar_estudiantes(db: Session, termino: str):
    termino = termino.strip()
    if not termino:
        return []
    filtro = Estudiante.carnet_hash.ilike(f"%{termino}%")
    orden = [Estudiante.estudiante_id]
    if termino.isdigit():
        filtro = (Estudiante.estudiante_id == int(termino)) | filtro
        # Sin este orden, un ID exacto puede quedar sepultado entre los
        # resultados del ILIKE (o incluso fuera del limit) si el motor no
        # los devuelve en un orden predecible.
        orden = [
            case((Estudiante.estudiante_id == int(termino), 0), else_=1),
            Estudiante.estudiante_id,
        ]
    return db.scalars(
        select(Estudiante)
        .where(filtro, Estudiante.activo.is_(True))
        .order_by(*orden)
        .limit(15)
    ).all()


@router.get("")
def inicio_matricula(
    request: Request,
    periodo_id: Optional[int] = Query(None),
    seccion_id: Optional[int] = Query(None),
    buscar: Optional[str] = Query(None),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    ok, error = tomar_aviso(request)
    periodos = _periodos(db)
    if periodo_id is None and periodos:
        periodo_id = periodos[0].periodo_id

    secciones = _secciones_de_periodo(db, periodo_id) if periodo_id else []

    seccion_actual = None
    materia_actual = None
    roster = []
    retirados = []
    if seccion_id:
        seccion_actual = db.get(Seccion, seccion_id)
        if seccion_actual and seccion_actual.periodo_id != periodo_id:
            # El filtro de periodo cambió sin refrescar la sección: se ignora
            # para no mostrar el roster de una sección de otro periodo.
            seccion_actual = None
        if seccion_actual:
            materia_actual = db.get(Materia, seccion_actual.materia_id)
            roster = _roster(db, seccion_id)
            retirados = _retirados(db, seccion_id)

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
            "materia": materia_actual,
            "roster": roster,
            "retirados": retirados,
            "motivos_retiro": MOTIVOS_RETIRO,
            "buscar": buscar or "",
            "resultados_busqueda": resultados_busqueda,
            "ok": ok,
            "error": error,
            "estado_activo": ESTADO_ACTIVO,
        },
    )


def _matricular(db: Session, seccion_id: int, estudiante_id: int) -> Optional[str]:
    """Matricula al estudiante en una sección. Devuelve None si se pudo, o el motivo."""
    seccion = db.execute(
        select(Seccion).where(Seccion.seccion_id == seccion_id).with_for_update()
    ).scalar_one_or_none()
    if seccion is None:
        return "Sección no encontrada"

    existente = db.scalar(
        select(Inscripcion).where(
            Inscripcion.estudiante_id == estudiante_id,
            Inscripcion.seccion_id == seccion_id,
        )
    )
    if existente and existente.estado_inscripcion == ESTADO_ACTIVO:
        return f"El estudiante {estudiante_id} ya está matriculado en esta sección"

    inscritos_actuales = db.scalar(
        select(func.count())
        .select_from(Inscripcion)
        .where(
            Inscripcion.seccion_id == seccion_id,
            Inscripcion.estado_inscripcion == ESTADO_ACTIVO,
        )
    )
    if inscritos_actuales >= seccion.cupo_maximo:
        return f"La sección alcanzó su cupo máximo ({seccion.cupo_maximo} estudiantes)"

    try:
        # Punto de guardado: si una sección falla, las demás del dock no se pierden.
        with db.begin_nested():
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
        return "No se pudo matricular: la base de datos rechazó la operación"
    return None


@router.post("/inscribir")
def inscribir(
    request: Request,
    periodo_id: int = Form(...),
    # Una o varias: el dock de matrícula envía todas sus secciones en un solo POST.
    seccion_id: List[int] = Form(...),
    estudiante_id: int = Form(...),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    destino = _destino(periodo_id, seccion_id[-1])

    if db.get(Estudiante, estudiante_id) is None:
        return redirigir(request, destino, error="Estudiante no encontrado")

    errores = [e for e in (_matricular(db, s, estudiante_id) for s in seccion_id) if e]
    exitos = len(seccion_id) - len(errores)
    total = len(seccion_id)

    if exitos == 0:
        ok = None
    elif total == 1:
        ok = f"Estudiante {estudiante_id} matriculado correctamente"
    elif exitos == total:
        ok = f"Estudiante {estudiante_id} matriculado en {exitos} materia(s) correctamente"
    else:
        ok = f"Estudiante {estudiante_id} matriculado en {exitos} de {total} materia(s)"
    return redirigir(request, destino, ok=ok, error=errores[-1] if errores else None)


@router.post("/retirar/{inscripcion_id}")
def retirar(
    request: Request,
    inscripcion_id: int,
    periodo_id: int = Form(...),
    seccion_id: int = Form(...),
    motivo: str = Form(""),
    detalle: str = Form(""),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    destino = _destino(periodo_id, seccion_id)
    if motivo not in MOTIVOS_RETIRO:
        return redirigir(request, destino, error="Elige el motivo del retiro.")
    detalle = " ".join(detalle.split())
    if motivo == "Otro" and not detalle:
        return redirigir(request, destino, error="Con «Otro», describe el motivo del retiro.")

    inscripcion = db.get(Inscripcion, inscripcion_id)
    if inscripcion is None or inscripcion.seccion_id != seccion_id:
        return redirigir(request, destino, error="Inscripción no encontrada")
    if inscripcion.estado_inscripcion != ESTADO_ACTIVO:
        return redirigir(request, destino, error="Esa inscripción ya estaba retirada")

    inscripcion.estado_inscripcion = ESTADO_RETIRADO
    inscripcion.motivo_retiro = f"{motivo} — {detalle}"[:200] if detalle else motivo

    return redirigir(request, destino, ok=f"Estudiante {inscripcion.estudiante_id} retirado de la sección")


# ---------------------------------------------------------------------------
# Matrícula masiva por archivo
# ---------------------------------------------------------------------------

COLUMNA_ID = "ID estudiante"


def _secciones_con_cupo(db: Session, periodo_id: int):
    """{(codigo_materia, numero_seccion): (seccion, inscritos activos)} del período."""
    return {(m.codigo_materia, s.numero_seccion): (s, inscritos)
            for s, m, inscritos in _secciones_de_periodo(db, periodo_id)}


@router.get("/plantilla")
def descargar_plantilla(
    periodo_id: int = Query(...),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    periodo = db.get(PeriodoAcademico, periodo_id)
    if periodo is None:
        raise HTTPException(status_code=404, detail="Período no encontrado")
    secciones = _secciones_de_periodo(db, periodo_id)
    filas = [["", m.codigo_materia, s.numero_seccion] for s, m, _ in secciones[:3]]
    contenido = plantilla_xlsx(
        f"Matrícula masiva · {periodo.codigo_periodo}",
        "Una fila por estudiante y sección. Escribe el ID del estudiante, el código de la materia y el "
        "número de sección (las de ejemplo son secciones reales del período; borra las que no uses).",
        [COLUMNA_ID, "Materia (código)", "Sección"],
        filas,
        validaciones={1: ("lista", sorted({m.codigo_materia for _, m, _ in secciones}))} if secciones else None,
        anchos=[14, 18, 10],
    )
    return Response(contenido, media_type=TIPO_XLSX, headers={
        "Content-Disposition": f'attachment; filename="matricula_{periodo.codigo_periodo}.xlsx"',
        "Cache-Control": "no-store"})


def analizar_matricula_masiva(filas, secciones, existentes, estudiantes_validos):
    """secciones: {(materia, numero): (seccion, inscritos)}; existentes: {(estudiante, seccion_id): estado}.
    Devuelve (cambios, errores). Tipos: nueva | cambio (reactiva un retiro) | igual (ya matriculado)."""
    errores = []
    inicio = ubicar_cabecera(filas, COLUMNA_ID)
    ocupados = {clave: inscritos for clave, (_, inscritos) in secciones.items()}
    cambios, vistos = [], set()
    for numero, fila in enumerate(filas[inicio + 1:], start=inicio + 2):
        fila = list(fila) + [None] * 3
        estudiante_id = como_entero(fila[0])
        materia = normalizar(fila[1]).upper()
        numero_seccion = como_entero(fila[2])
        if estudiante_id is None:
            errores.append(f"Fila {numero}: el ID de estudiante «{fila[0]}» no es válido.")
            continue
        if estudiante_id not in estudiantes_validos:
            errores.append(f"Fila {numero}: el estudiante {estudiante_id} no existe o no está activo.")
            continue
        clave = (materia, numero_seccion)
        if clave not in secciones:
            errores.append(f"Fila {numero}: no hay sección {fila[2]} de «{fila[1]}» en este período.")
            continue
        seccion, _ = secciones[clave]
        if (estudiante_id, seccion.seccion_id) in vistos:
            errores.append(f"Fila {numero}: el estudiante {estudiante_id} se repite en {materia} sección {numero_seccion}.")
            continue
        vistos.add((estudiante_id, seccion.seccion_id))
        estado = existentes.get((estudiante_id, seccion.seccion_id))
        if estado == ESTADO_ACTIVO:
            cambios.append({"tipo": "igual", "estudiante_id": estudiante_id, "seccion": seccion,
                            "materia": materia, "fila": numero})
            continue
        if ocupados[clave] >= seccion.cupo_maximo:
            errores.append(f"Fila {numero}: {materia} sección {numero_seccion} no tiene cupo "
                           f"({seccion.cupo_maximo} estudiantes) contando las filas anteriores del archivo.")
            continue
        ocupados[clave] += 1
        cambios.append({"tipo": "cambio" if estado == ESTADO_RETIRADO else "nueva", "estudiante_id": estudiante_id,
                        "seccion": seccion, "materia": materia, "fila": numero})
    return cambios, errores


@router.post("/importar")
async def importar_matricula(
    request: Request,
    periodo_id: int = Form(...),
    archivo: UploadFile = File(...),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    destino = _destino(periodo_id)
    periodo = db.get(PeriodoAcademico, periodo_id)
    if periodo is None:
        return redirigir(request, destino, error="Período no encontrado")
    secciones = _secciones_con_cupo(db, periodo_id)
    ids_secciones = [s.seccion_id for s, _ in secciones.values()]
    existentes = {(i.estudiante_id, i.seccion_id): i.estado_inscripcion for i in db.scalars(
        select(Inscripcion).where(Inscripcion.seccion_id.in_(ids_secciones or [0]))).all()}
    try:
        filas = await leer_filas(archivo)
        candidatos = {como_entero((list(f) + [None])[0]) for f in filas}
        validos = set(db.scalars(select(Estudiante.estudiante_id).where(
            Estudiante.estudiante_id.in_([c for c in candidatos if c] or [0]), Estudiante.activo.is_(True))).all())
        cambios, errores = analizar_matricula_masiva(filas, secciones, existentes, validos)
    except ErrorArchivo as exc:
        return redirigir(request, destino, error=str(exc))
    pendientes = [c for c in cambios if c["tipo"] != "igual"]
    return templates.TemplateResponse(request, "modulos/importar_vista_previa.html", {
        "usuario": usuario,
        "titulo": "Matrícula masiva",
        "subtitulo": periodo.codigo_periodo,
        "archivo": archivo.filename,
        "columnas": ["Fila", "Estudiante", "Materia", "Sección", "Turno"],
        "filas": [(c["tipo"], [c["fila"], c["estudiante_id"], c["materia"], c["seccion"].numero_seccion,
                               c["seccion"].turno.capitalize()]) for c in pendientes],
        "conteo": {t: sum(1 for c in cambios if c["tipo"] == t) for t in ("nueva", "cambio", "igual")},
        "etiquetas": {"nueva": "Matrículas nuevas", "cambio": "Reactivan un retiro", "igual": "Ya matriculados"},
        "errores": errores,
        "accion": "/matricula/importar/confirmar",
        "ocultos": [("periodo_id", periodo_id)]
                   + [("cambio", f"{c['estudiante_id']}:{c['seccion'].seccion_id}") for c in pendientes],
        "volver": destino,
    })


@router.post("/importar/confirmar")
def confirmar_matricula_masiva(
    request: Request,
    periodo_id: int = Form(...),
    cambio: List[str] = Form([]),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    destino = _destino(periodo_id)
    secciones_validas = {s.seccion_id for s, _, _ in _secciones_de_periodo(db, periodo_id)}
    pares = []
    for texto_cambio in cambio:
        partes = texto_cambio.split(":")
        estudiante_id = como_entero(partes[0]) if len(partes) == 2 else None
        seccion_id = como_entero(partes[1]) if len(partes) == 2 else None
        if estudiante_id is None or seccion_id not in secciones_validas:
            return redirigir(request, destino, error="La importación cambió desde la vista previa: vuelve a subir el archivo.")
        pares.append((estudiante_id, seccion_id))
    # Cada fila con su punto de guardado y el mismo control de cupo bajo bloqueo
    # que la matrícula individual: si entretanto se llenó una sección, esa fila
    # se informa y las demás se aplican.
    errores = []
    for estudiante_id, seccion_id in pares:
        motivo = _matricular(db, seccion_id, estudiante_id)
        if motivo:
            errores.append(f"{estudiante_id}: {motivo}")
    hechas = len(pares) - len(errores)
    return redirigir(request, destino,
                     ok=f"Matrícula masiva aplicada: {hechas} de {len(pares)} inscripción(es)." if hechas else None,
                     error=("No se aplicaron: " + "; ".join(errores[:5]) + (" …" if len(errores) > 5 else ""))
                     if errores else None)
