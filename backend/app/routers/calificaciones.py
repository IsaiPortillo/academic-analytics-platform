"""Módulo de calificaciones — SCRUM-8 (responsable: Isai Portillo).

Registro de evaluaciones (ponderación por sección) y de notas por inscripción,
más una vista de notas por sección con el acumulado ponderado.

La ponderación (<=100% por sección) y la auditoría de cambios de nota ya están
resueltas por triggers en la base (script 01); esta capa solo intenta la
operación y muestra el error que devuelve PostgreSQL cuando la rechaza — no
reimplementa esas reglas.

Buscar por carnet: la matriz identifica a cada estudiante por su ID interno,
porque el sistema no guarda nombres ni el carnet (solo su hash). El docente, que
tiene el carnet en la mano, necesita el ID; el coordinador ya podía resolverlo en
Catálogos, pero esa pantalla no es suya. La búsqueda vive aquí, limitada al
roster de la sección, y va por POST: el carnet es un dato personal y en un GET
quedaría en el historial del navegador y en los registros de nginx. Lo que viaja
de vuelta en la URL es el ID, que la propia matriz ya muestra.

Secciones del docente: el motor solo le deja leer y escribir evaluaciones y
notas de sus propias secciones (seguridad por fila, database/oltp/16). Esta capa
filtra igual por Seccion.docente_id y valida que las inscripciones del
formulario sean del roster de la sección: así la pantalla no ofrece lo que el
motor rechazaría, y un id manipulado se descarta con un mensaje claro en vez de
un error de base de datos.
"""

import re
from decimal import Decimal, InvalidOperation
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from ..avisos import redirigir, tomar_aviso
from ..busqueda_carnet import localizar
from ..database import get_db
from ..dependencies import UsuarioSesion, requiere_rol
from ..fechas_periodo import periodo_de, problema_fecha
from ..importar import (TIPO_XLSX, ErrorArchivo, como_entero, como_nota, leer_filas, normalizar,
                        plantilla_xlsx, ubicar_cabecera, vacio)
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


def _roster(db: Session, seccion_id: int, incluir_finalizados: bool = False):
    # Con el acta cerrada sus inscripciones pasan a FINALIZADO: para mostrar las
    # notas (solo lectura) se incluyen; para registrar, solo las activas.
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
    evaluaciones = []
    roster = []
    tabla = []
    evaluacion_actual = None
    notas_evaluacion_actual = {}
    notas_faltantes = 0
    notas_por_evaluacion = {}
    if seccion_id:
        seccion = _seccion_permitida(db, seccion_id, usuario)
        if seccion and seccion.periodo_id != periodo_id:
            # Mismo caso que en matrícula: el filtro de periodo cambió sin
            # refrescar la sección, así que se ignora para no mostrar datos
            # de una sección de otro periodo.
            seccion = None
        if seccion:
            materia = db.get(Materia, seccion.materia_id)
            evaluaciones = _evaluaciones_de_seccion(db, seccion_id)
            roster = _roster(db, seccion_id, incluir_finalizados=seccion.acta_cerrada)
            tabla = _tabla_notas(db, roster, evaluaciones)
            notas_faltantes = sum(1 for f in tabla for c in f["celdas"] if c is None)
            notas_por_evaluacion = {e.evaluacion_id: sum(1 for f in tabla if f["celdas"][k] is not None)
                                    for k, e in enumerate(evaluaciones)}

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
            "periodo": periodo_de(db, seccion) if seccion else None,
            "materia": materia,
            "evaluaciones": evaluaciones,
            "ponderacion_usada": ponderacion_usada,
            "roster": roster,
            "tabla": tabla,
            "evaluacion_actual": evaluacion_actual,
            "notas_evaluacion_actual": notas_evaluacion_actual,
            "notas_faltantes": notas_faltantes,
            "notas_por_evaluacion": notas_por_evaluacion,
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
    evaluacion_id: Optional[int] = Form(None),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_docente", "rol_coordinador")),
    db: Session = Depends(get_db),
):
    """Traduce un carnet al ID con el que la matriz identifica al estudiante.

    La búsqueda en sí está en app/busqueda_carnet.py, compartida con asistencia.
    """
    destino = _destino(periodo_id, seccion_id, evaluacion_id)

    seccion = _seccion_permitida(db, seccion_id, usuario)
    if seccion is None:
        return redirigir(request, destino, error="Sección no encontrada")

    # La matriz solo dibuja las inscripciones finalizadas cuando el acta está
    # cerrada, así que lo visible no siempre es toda la sección.
    resultado = localizar(
        carnet,
        completo=[e for _, e in _roster(db, seccion_id, incluir_finalizados=True)],
        visible=[e for _, e in _roster(db, seccion_id, incluir_finalizados=seccion.acta_cerrada)],
    )
    if resultado.estudiante_id is None:
        return redirigir(request, destino, error=resultado.error)

    return redirigir(request, f"{destino}&resaltar={resultado.estudiante_id}", ok=resultado.ok)


@router.post("/evaluaciones")
def crear_evaluacion(
    request: Request,
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
        return redirigir(request, destino, error="Sección no encontrada")

    nombre_evaluacion = nombre_evaluacion.strip()
    if not nombre_evaluacion:
        return redirigir(request, destino, error="El nombre de la evaluación es obligatorio")
    problema = problema_fecha(periodo_de(db, seccion), fecha_evaluacion, permitir_futura=True)
    if problema:
        return redirigir(request, destino, error=problema)

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
        return redirigir(request, destino, error=f"{_mensaje_amigable(exc)}")

    return redirigir(request, destino, ok=f"Evaluación «{nombre_evaluacion}» creada correctamente")


@router.post("/registrar")
def registrar_notas(
    request: Request,
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
        return redirigir(request, destino, error="Sección no encontrada")

    evaluacion = db.get(Evaluacion, evaluacion_id)
    if evaluacion is None or evaluacion.seccion_id != seccion_id:
        return redirigir(request, destino, error="Evaluación no encontrada")

    if len(inscripcion_id) != len(nota):
        return redirigir(request, destino, error="Formulario de notas inconsistente")

    # Solo se aceptan inscripciones del roster real de la sección. El motor ya
    # rechaza las de secciones ajenas (RLS); aquí se descartan antes de intentarlo.
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
        return redirigir(request, destino, error="Una de las notas ingresadas no es un número válido")
    except DBAPIError as exc:
        db.rollback()
        return redirigir(request, destino, error=f"{_mensaje_amigable(exc)}")

    return redirigir(request, destino, ok=f"{registradas} nota(s) registrada(s)")


# ---------------------------------------------------------------------------
# Editar y eliminar evaluaciones
# ---------------------------------------------------------------------------

def _evaluacion_permitida(db: Session, evaluacion_id: int, seccion_id: int, usuario: UsuarioSesion):
    seccion = _seccion_permitida(db, seccion_id, usuario)
    evaluacion = db.get(Evaluacion, evaluacion_id)
    if seccion is None or evaluacion is None or evaluacion.seccion_id != seccion_id:
        return None
    return evaluacion


@router.post("/evaluaciones/{evaluacion_id}/editar")
def editar_evaluacion(
    request: Request,
    evaluacion_id: int,
    periodo_id: int = Form(...),
    seccion_id: int = Form(...),
    nombre_evaluacion: str = Form(...),
    porcentaje: Decimal = Form(...),
    fecha_evaluacion: date = Form(...),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_docente", "rol_coordinador")),
    db: Session = Depends(get_db),
):
    destino = _destino(periodo_id, seccion_id)
    evaluacion = _evaluacion_permitida(db, evaluacion_id, seccion_id, usuario)
    if evaluacion is None:
        return redirigir(request, destino, error="Evaluación no encontrada")
    nombre_evaluacion = nombre_evaluacion.strip()
    if not nombre_evaluacion:
        return redirigir(request, destino, error="El nombre de la evaluación es obligatorio")
    # Solo si se cambia la fecha: no se bloquea editar el nombre de una evaluación antigua.
    if fecha_evaluacion != evaluacion.fecha_evaluacion:
        seccion = db.get(Seccion, evaluacion.seccion_id)
        problema = problema_fecha(periodo_de(db, seccion), fecha_evaluacion, permitir_futura=True)
        if problema:
            return redirigir(request, destino, error=problema)
    try:
        evaluacion.nombre_evaluacion = nombre_evaluacion
        evaluacion.porcentaje = porcentaje
        evaluacion.fecha_evaluacion = fecha_evaluacion
        db.flush()  # la ponderación (<= 100 %) y el acta cerrada los valida el motor
    except DBAPIError as exc:
        db.rollback()
        return redirigir(request, destino, error=_mensaje_amigable(exc))
    return redirigir(request, destino, ok=f"Evaluación «{nombre_evaluacion}» actualizada")


@router.post("/evaluaciones/{evaluacion_id}/eliminar")
def eliminar_evaluacion(
    request: Request,
    evaluacion_id: int,
    periodo_id: int = Form(...),
    seccion_id: int = Form(...),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_docente", "rol_coordinador")),
    db: Session = Depends(get_db),
):
    destino = _destino(periodo_id, seccion_id)
    evaluacion = _evaluacion_permitida(db, evaluacion_id, seccion_id, usuario)
    if evaluacion is None:
        return redirigir(request, destino, error="Evaluación no encontrada")
    nombre = evaluacion.nombre_evaluacion
    try:
        # Primero las notas, una por una: así el trigger de auditoría todavía
        # encuentra la evaluación y deja en la bitácora a cuál pertenecían.
        notas = db.scalars(select(Calificacion).where(Calificacion.evaluacion_id == evaluacion_id)).all()
        for nota in notas:
            db.delete(nota)
        db.flush()
        db.delete(evaluacion)
        db.flush()
    except DBAPIError as exc:
        db.rollback()
        return redirigir(request, destino, error=_mensaje_amigable(exc))
    return redirigir(request, destino, ok=f"Evaluación «{nombre}» eliminada junto con {len(notas)} nota(s)")


# ---------------------------------------------------------------------------
# Plantilla e importación de notas desde Excel
# ---------------------------------------------------------------------------

COLUMNA_ID = "ID estudiante"


def _cabecera_evaluacion(evaluacion: Evaluacion) -> str:
    # El id entre corchetes es lo que el sistema lee al importar: el nombre se
    # puede repetir entre secciones o cambiar después de descargar la plantilla.
    return f"{evaluacion.nombre_evaluacion} ({evaluacion.porcentaje}%) [{evaluacion.evaluacion_id}]"


@router.get("/plantilla")
def descargar_plantilla(
    seccion_id: int = Query(...),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_docente", "rol_coordinador")),
    db: Session = Depends(get_db),
):
    seccion = _seccion_permitida(db, seccion_id, usuario)
    if seccion is None:
        raise HTTPException(status_code=404, detail="Sección no encontrada")
    materia = db.get(Materia, seccion.materia_id)
    evaluaciones = _evaluaciones_de_seccion(db, seccion_id)
    roster = _roster(db, seccion_id)
    tabla = _tabla_notas(db, roster, evaluaciones) if evaluaciones else []
    filas = [[f["estudiante"].estudiante_id] + [float(n) if n is not None else None for n in f["celdas"]]
             for f in tabla] or [[e.estudiante_id] for _, e in roster]
    contenido = plantilla_xlsx(
        f"Notas · {materia.codigo_materia} sección {seccion.numero_seccion}",
        "Escribe las notas (0 a 10) en las columnas de cada evaluación. No cambies la columna A "
        "ni los números entre corchetes. Una celda vacía no modifica la nota registrada.",
        [COLUMNA_ID] + [_cabecera_evaluacion(e) for e in evaluaciones],
        filas,
        validaciones={i: ("decimal", 0, 10) for i in range(1, len(evaluaciones) + 1)},
        anchos=[14] + [max(len(_cabecera_evaluacion(e)) + 2, 16) for e in evaluaciones],
    )
    nombre = f"notas_{materia.codigo_materia}_s{seccion.numero_seccion}.xlsx".lower()
    return Response(contenido, media_type=TIPO_XLSX, headers={
        "Content-Disposition": f'attachment; filename="{nombre}"', "Cache-Control": "no-store"})


def analizar_importacion_notas(filas, evaluaciones, roster, notas_actuales):
    """Compara el archivo con lo registrado. Devuelve (cambios, errores).

    cambios: dicts con inscripcion_id, estudiante_id, evaluacion_id, evaluacion,
    antes, despues y tipo ('nueva' | 'cambio' | 'igual').
    notas_actuales: {(inscripcion_id, evaluacion_id): nota}
    """
    errores = []
    inicio = ubicar_cabecera(filas, COLUMNA_ID)
    cabecera = filas[inicio]
    por_id = {e.evaluacion_id: e for e in evaluaciones}
    por_nombre = {normalizar(e.nombre_evaluacion): e for e in evaluaciones}
    columnas = {}
    for j, titulo in enumerate(cabecera[1:], start=1):
        if vacio(titulo):
            continue
        m = re.search(r"\[(\d+)\]\s*$", str(titulo))
        evaluacion = por_id.get(int(m.group(1))) if m else por_nombre.get(normalizar(titulo))
        if evaluacion is None:
            errores.append(f"La columna «{titulo}» no corresponde a ninguna evaluación de esta sección.")
        else:
            columnas[j] = evaluacion
    if not columnas and not errores:
        errores.append("El archivo no tiene columnas de evaluaciones.")

    inscripcion_de = {e.estudiante_id: i.inscripcion_id for i, e in roster}
    cambios, vistos = [], set()
    for numero, fila in enumerate(filas[inicio + 1:], start=inicio + 2):
        estudiante_id = como_entero(fila[0] if fila else None)
        if estudiante_id is None:
            errores.append(f"Fila {numero}: el ID de estudiante «{fila[0] if fila else ''}» no es válido.")
            continue
        if estudiante_id not in inscripcion_de:
            errores.append(f"Fila {numero}: el estudiante {estudiante_id} no está inscrito en esta sección.")
            continue
        if estudiante_id in vistos:
            errores.append(f"Fila {numero}: el estudiante {estudiante_id} aparece más de una vez.")
            continue
        vistos.add(estudiante_id)
        inscripcion_id = inscripcion_de[estudiante_id]
        for j, evaluacion in columnas.items():
            valor = fila[j] if j < len(fila) else None
            if vacio(valor):
                continue
            nota = como_nota(valor)
            if nota is None:
                errores.append(f"Fila {numero}, «{evaluacion.nombre_evaluacion}»: «{valor}» no es una nota de 0 a 10.")
                continue
            antes = notas_actuales.get((inscripcion_id, evaluacion.evaluacion_id))
            tipo = "nueva" if antes is None else ("igual" if Decimal(antes) == nota else "cambio")
            cambios.append({"inscripcion_id": inscripcion_id, "estudiante_id": estudiante_id,
                            "evaluacion_id": evaluacion.evaluacion_id, "evaluacion": evaluacion.nombre_evaluacion,
                            "antes": antes, "despues": nota, "tipo": tipo})
    return cambios, errores


def _notas_actuales(db: Session, roster) -> dict:
    ids = [i.inscripcion_id for i, _ in roster]
    if not ids:
        return {}
    return {(c.inscripcion_id, c.evaluacion_id): c.nota
            for c in db.scalars(select(Calificacion).where(Calificacion.inscripcion_id.in_(ids))).all()}


@router.post("/importar")
async def importar_notas(
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
        return redirigir(request, destino, error="El acta de esta sección está cerrada: no se pueden importar notas.")
    evaluaciones = _evaluaciones_de_seccion(db, seccion_id)
    roster = _roster(db, seccion_id)
    try:
        filas = await leer_filas(archivo)
        cambios, errores = analizar_importacion_notas(filas, evaluaciones, roster, _notas_actuales(db, roster))
    except ErrorArchivo as exc:
        return redirigir(request, destino, error=str(exc))
    pendientes = [c for c in cambios if c["tipo"] != "igual"]
    return templates.TemplateResponse(request, "modulos/importar_vista_previa.html", {
        "usuario": usuario,
        "titulo": "Importar notas",
        "subtitulo": f"{db.get(Materia, seccion.materia_id).codigo_materia} · sección {seccion.numero_seccion}",
        "archivo": archivo.filename,
        "columnas": ["Estudiante", "Evaluación", "Registrada", "Nueva"],
        "filas": [(c["tipo"], [c["estudiante_id"], c["evaluacion"],
                               "—" if c["antes"] is None else f"{c['antes']:.2f}", f"{c['despues']:.2f}"])
                  for c in pendientes],
        "conteo": {t: sum(1 for c in cambios if c["tipo"] == t) for t in ("nueva", "cambio", "igual")},
        "errores": errores,
        "accion": "/calificaciones/importar/confirmar",
        "ocultos": [("periodo_id", periodo_id), ("seccion_id", seccion_id)]
                   + [("cambio", f"{c['inscripcion_id']}:{c['evaluacion_id']}:{c['despues']}") for c in pendientes],
        "volver": destino,
    })


@router.post("/importar/confirmar")
def confirmar_importacion_notas(
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
    # Se vuelve a validar todo: lo que llega del formulario de confirmación lo
    # puede alterar el navegador igual que cualquier otro envío.
    validas_insc = {i.inscripcion_id for i, _ in _roster(db, seccion_id)}
    validas_ev = {e.evaluacion_id for e in _evaluaciones_de_seccion(db, seccion_id)}
    actuales = {(c.inscripcion_id, c.evaluacion_id): c for c in db.scalars(
        select(Calificacion).where(Calificacion.inscripcion_id.in_(validas_insc or [0]))).all()}
    nuevas = cambiadas = 0
    try:
        for texto_cambio in cambio:
            partes = texto_cambio.split(":")
            insc, ev, nota = ((como_entero(partes[0]), como_entero(partes[1]), como_nota(partes[2]))
                              if len(partes) == 3 else (None, None, None))
            if insc not in validas_insc or ev not in validas_ev or nota is None:
                db.rollback()
                return redirigir(request, destino,
                                 error="La importación cambió desde la vista previa: vuelve a subir el archivo.")
            existente = actuales.get((insc, ev))
            if existente is None:
                db.add(Calificacion(inscripcion_id=insc, evaluacion_id=ev, nota=nota))
                nuevas += 1
            elif existente.nota != nota:
                existente.nota = nota
                cambiadas += 1
        db.flush()
    except DBAPIError as exc:
        db.rollback()
        return redirigir(request, destino, error=_mensaje_amigable(exc))
    return redirigir(request, destino,
                     ok=f"Importación aplicada: {nuevas} nota(s) nueva(s) y {cambiadas} corregida(s)")


# ---------------------------------------------------------------------------
# Acta: cierre (docente o coordinador) y reapertura (solo coordinador)
# ---------------------------------------------------------------------------

@router.post("/acta/cerrar")
def cerrar_acta(
    request: Request,
    periodo_id: int = Form(...),
    seccion_id: int = Form(...),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_docente", "rol_coordinador")),
    db: Session = Depends(get_db),
):
    destino = _destino(periodo_id, seccion_id)
    if _seccion_permitida(db, seccion_id, usuario) is None:
        return redirigir(request, destino, error="Sección no encontrada")
    try:
        # Las condiciones (100 %, todas las notas, permiso) las valida la función del motor.
        finalizadas = db.scalar(text("SELECT academico_oltp.cerrar_acta(:s)"), {"s": seccion_id})
    except DBAPIError as exc:
        db.rollback()
        return redirigir(request, destino, error=_mensaje_amigable(exc))
    return redirigir(request, destino, ok=f"Acta cerrada: {finalizadas} inscripción(es) finalizada(s). "
                                          "Las notas de esta sección ya no se pueden modificar.")


@router.post("/acta/reabrir")
def reabrir_acta(
    request: Request,
    periodo_id: int = Form(...),
    seccion_id: int = Form(...),
    motivo: str = Form(""),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    destino = _destino(periodo_id, seccion_id)
    try:
        reabiertas = db.scalar(text("SELECT academico_oltp.reabrir_acta(:s, :m)"),
                               {"s": seccion_id, "m": motivo})
    except DBAPIError as exc:
        db.rollback()
        return redirigir(request, destino, error=_mensaje_amigable(exc))
    return redirigir(request, destino,
                     ok=f"Acta reabierta: {reabiertas} inscripción(es) vuelven a estar en curso.")
