"""Metas de los indicadores (admin): catálogo del CMI, meta y banda de
tolerancia de cada KPI (database/oltp/20 y 26).

Hay una meta general por indicador y, opcionalmente, una propia por carrera que
se antepone a la general. Ninguna carrera queda sin meta: la que no tiene propia
hereda la institucional. No se derivan solas desde las de carrera porque cuatro
de los cinco indicadores son razones, y promediar razones es un promedio de
promedios (ver el encabezado del script 26).

Se editan en el esquema operacional, como el costo por UV, y llegan al tablero
con la siguiente carga del DW. La meta de un porcentaje se escribe en puntos
(22 = 22 %) y se guarda como fracción (0.22), igual que el resto del sistema.
"""

from decimal import Decimal, InvalidOperation

from typing import Optional

from fastapi import APIRouter, Depends, Form, Query, Request
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from .. import recarga
from ..avisos import redirigir, tomar_aviso
from ..database import get_db
from ..dependencies import UsuarioSesion, requiere_rol
from ..templating import templates

router = APIRouter(prefix="/admin/metas", tags=["metas"])
COORDINADOR = requiere_rol("rol_admin")
PERSPECTIVAS = ("Financiera", "Estudiantes", "Procesos internos", "Aprendizaje y crecimiento")


def _indicadores(db: Session, carrera_id: int | None = None):
    """Los cinco indicadores con la meta del alcance pedido.

    `meta` es la del alcance (la propia de la carrera, o la general si se pide la
    institucional) y `meta_general` siempre la institucional, para mostrarla como
    referencia de lo que se hereda.
    """
    return db.execute(text("""
        SELECT i.codigo, i.nombre, i.definicion, i.unidad, i.sentido, i.perspectiva, i.responsable_cargo,
               i.meta_por_periodo,
               m.meta, m.tolerancia, m.justificacion, m.actualizado_en, m.actualizado_por,
               g.meta AS meta_general, g.tolerancia AS tolerancia_general
        FROM academico_oltp.indicadores i
        LEFT JOIN academico_oltp.metas_indicador m
               ON m.codigo = i.codigo AND m.carrera_id IS NOT DISTINCT FROM :carrera
        LEFT JOIN academico_oltp.metas_indicador g
               ON g.codigo = i.codigo AND g.carrera_id IS NULL
        ORDER BY i.orden
    """), {"carrera": carrera_id}).mappings().all()


def _carreras(db: Session):
    return db.execute(text(
        "SELECT carrera_id, codigo_carrera, nombre FROM academico_oltp.carreras "
        "WHERE activo ORDER BY nombre")).mappings().all()


def _destino(carrera_id: int | None) -> str:
    return "/admin/metas" if carrera_id is None else f"/admin/metas?carrera_id={carrera_id}"


def _a_pantalla(valor, unidad):
    if valor is None:
        return ""
    return f"{Decimal(valor) * 100:.2f}".rstrip("0").rstrip(".") if unidad == "porcentaje" else f"{Decimal(valor):.2f}"


@router.get("")
def ver(request: Request, carrera_id: Optional[int] = Query(None),
        usuario: UsuarioSesion = Depends(COORDINADOR), db: Session = Depends(get_db)):
    ok, error = tomar_aviso(request)
    try:
        carreras = _carreras(db)
        if carrera_id not in {c["carrera_id"] for c in carreras}:
            carrera_id = None          # alcance institucional
        indicadores = _indicadores(db, carrera_id)
    except DBAPIError:
        db.rollback()
        carreras, indicadores = [], None
    filas = [{**i, "meta_pantalla": _a_pantalla(i["meta"], i["unidad"]),
              "tolerancia_pantalla": _a_pantalla(i["tolerancia"], i["unidad"]),
              "meta_general_pantalla": _a_pantalla(i["meta_general"], i["unidad"]),
              "hereda": carrera_id is not None and i["meta"] is None}
             for i in indicadores or []]
    carrera = next((c for c in carreras if c["carrera_id"] == carrera_id), None)
    return templates.TemplateResponse(request, "modulos/admin_metas.html", {
        "usuario": usuario, "ok": ok, "error": error, "filas": filas, "sin_tablas": indicadores is None,
        "perspectivas": PERSPECTIVAS, "carga_en_curso": recarga.hay_carga_en_curso(),
        "carreras": carreras, "carrera_id": carrera_id, "carrera": carrera,
    })


@router.post("/{codigo}")
def guardar(
    request: Request,
    codigo: str,
    meta: str = Form(...),
    tolerancia: str = Form(...),
    justificacion: str = Form(...),
    perspectiva: str = Form(""),
    responsable_cargo: str = Form(""),
    carrera_id: Optional[int] = Form(None),
    usuario: UsuarioSesion = Depends(COORDINADOR),
    db: Session = Depends(get_db),
):
    destino = _destino(carrera_id)
    if carrera_id is not None and not db.execute(
            text("SELECT 1 FROM academico_oltp.carreras WHERE carrera_id = :c AND activo"),
            {"c": carrera_id}).first():
        return redirigir(request, "/admin/metas", error="Carrera no encontrada.")
    indicador = db.execute(text("SELECT unidad, nombre FROM academico_oltp.indicadores WHERE codigo = :c"),
                           {"c": codigo}).mappings().first()
    if indicador is None:
        return redirigir(request, destino, error="Indicador no encontrado.")
    try:
        valor_meta = Decimal(meta.replace(",", ".").strip())
        valor_tolerancia = Decimal(tolerancia.replace(",", ".").strip())
    except InvalidOperation:
        return redirigir(request, destino, error="La meta y la tolerancia deben ser números.")
    if valor_meta < 0 or valor_tolerancia < 0:
        return redirigir(request, destino, error="La meta y la tolerancia no pueden ser negativas.")
    if indicador["unidad"] == "porcentaje":
        if valor_meta > 100 or valor_tolerancia > 100:
            return redirigir(request, destino, error="Un porcentaje va de 0 a 100.")
        valor_meta, valor_tolerancia = valor_meta / 100, valor_tolerancia / 100
    justificacion = " ".join(justificacion.split())
    if len(justificacion) < 10:
        return redirigir(request, destino, error="Explica de dónde sale la meta (al menos 10 caracteres): "
                                                 "una meta sin justificación no se puede defender.")
    # La perspectiva del CMI y el cargo responsable describen al INDICADOR, no a
    # una carrera: solo se editan en el alcance institucional. Editándolos desde
    # una carrera se cambiarían para todas sin que se note.
    if carrera_id is None:
        if perspectiva not in PERSPECTIVAS:
            return redirigir(request, destino, error="Perspectiva del cuadro de mando no reconocida.")
        responsable_cargo = " ".join(responsable_cargo.split())[:80]
        if not responsable_cargo:
            return redirigir(request, destino, error="Indica el cargo responsable del indicador.")
    try:
        db.execute(text("""
            INSERT INTO academico_oltp.metas_indicador
                   (codigo, carrera_id, meta, tolerancia, justificacion, actualizado_por)
            VALUES (:c, :car, :m, :t, :j, :u)
            -- Por nombre de restricción: la inferencia por columnas es ambigua
            -- con NULLS NOT DISTINCT (script 26).
            ON CONFLICT ON CONSTRAINT uq_meta_indicador_carrera
            DO UPDATE SET meta = EXCLUDED.meta, tolerancia = EXCLUDED.tolerancia,
                justificacion = EXCLUDED.justificacion, actualizado_por = EXCLUDED.actualizado_por,
                actualizado_en = now()
        """), {"c": codigo, "car": carrera_id, "m": valor_meta, "t": valor_tolerancia,
               "j": justificacion[:400], "u": usuario.username})
        if carrera_id is None:
            db.execute(text("UPDATE academico_oltp.indicadores SET perspectiva = :p, responsable_cargo = :r "
                            "WHERE codigo = :c"), {"p": perspectiva, "r": responsable_cargo, "c": codigo})
    except DBAPIError as exc:
        db.rollback()
        diag = getattr(exc.orig, "diag", None)
        return redirigir(request, destino, error=diag.message_primary if diag else "La base rechazó la meta.")
    alcance = "institucional" if carrera_id is None else "de la carrera"
    return redirigir(request, destino, ok=f"Meta {alcance} de «{indicador['nombre']}» guardada. "
                                          "Recarga el Data Warehouse para verla en el tablero.")


@router.post("/{codigo}/quitar")
def quitar(
    request: Request,
    codigo: str,
    carrera_id: int = Form(...),
    usuario: UsuarioSesion = Depends(COORDINADOR),
    db: Session = Depends(get_db),
):
    """Quita la meta propia de una carrera: vuelve a heredar la institucional.

    La general no se puede quitar desde aquí: sin ella, las carreras sin meta
    propia se quedarían sin nada contra qué compararse.
    """
    borradas = db.execute(text(
        "DELETE FROM academico_oltp.metas_indicador "
        "WHERE codigo = :c AND carrera_id = :car"),
        {"c": codigo, "car": carrera_id}).rowcount
    destino = _destino(carrera_id)
    if not borradas:
        return redirigir(request, destino, error="Esa carrera no tenía meta propia para ese indicador.")
    return redirigir(request, destino, ok="Meta propia quitada: la carrera vuelve a usar la "
                                          "institucional. Recarga el Data Warehouse para verlo.")
