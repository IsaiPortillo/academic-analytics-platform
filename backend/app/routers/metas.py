"""Metas de los indicadores (coordinador): catálogo del CMI, meta y banda de
tolerancia de cada KPI (database/oltp/20).

Se editan en el esquema operacional, como el costo por UV, y llegan al tablero
con la siguiente carga del DW. La meta de un porcentaje se escribe en puntos
(22 = 22 %) y se guarda como fracción (0.22), igual que el resto del sistema.
"""

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from .. import recarga
from ..avisos import redirigir, tomar_aviso
from ..database import get_db
from ..dependencies import UsuarioSesion, requiere_rol
from ..templating import templates

router = APIRouter(prefix="/admin/metas", tags=["metas"])
COORDINADOR = requiere_rol("rol_coordinador")
PERSPECTIVAS = ("Financiera", "Estudiantes", "Procesos internos", "Aprendizaje y crecimiento")


def _indicadores(db: Session):
    return db.execute(text("""
        SELECT i.codigo, i.nombre, i.definicion, i.unidad, i.sentido, i.perspectiva, i.responsable_cargo,
               i.meta_por_periodo, m.meta, m.tolerancia, m.justificacion, m.actualizado_en, m.actualizado_por
        FROM academico_oltp.indicadores i
        LEFT JOIN academico_oltp.metas_indicador m ON m.codigo = i.codigo
        ORDER BY i.orden
    """)).mappings().all()


def _a_pantalla(valor, unidad):
    if valor is None:
        return ""
    return f"{Decimal(valor) * 100:.2f}".rstrip("0").rstrip(".") if unidad == "porcentaje" else f"{Decimal(valor):.2f}"


@router.get("")
def ver(request: Request, usuario: UsuarioSesion = Depends(COORDINADOR), db: Session = Depends(get_db)):
    ok, error = tomar_aviso(request)
    try:
        indicadores = _indicadores(db)
    except DBAPIError:
        db.rollback()
        indicadores = None
    filas = [{**i, "meta_pantalla": _a_pantalla(i["meta"], i["unidad"]),
              "tolerancia_pantalla": _a_pantalla(i["tolerancia"], i["unidad"])} for i in indicadores or []]
    return templates.TemplateResponse(request, "modulos/admin_metas.html", {
        "usuario": usuario, "ok": ok, "error": error, "filas": filas, "sin_tablas": indicadores is None,
        "perspectivas": PERSPECTIVAS, "carga_en_curso": recarga.hay_carga_en_curso(),
    })


@router.post("/{codigo}")
def guardar(
    request: Request,
    codigo: str,
    meta: str = Form(...),
    tolerancia: str = Form(...),
    justificacion: str = Form(...),
    perspectiva: str = Form(...),
    responsable_cargo: str = Form(...),
    usuario: UsuarioSesion = Depends(COORDINADOR),
    db: Session = Depends(get_db),
):
    destino = "/admin/metas"
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
    if perspectiva not in PERSPECTIVAS:
        return redirigir(request, destino, error="Perspectiva del cuadro de mando no reconocida.")
    responsable_cargo = " ".join(responsable_cargo.split())[:80]
    if not responsable_cargo:
        return redirigir(request, destino, error="Indica el cargo responsable del indicador.")
    try:
        db.execute(text("""
            INSERT INTO academico_oltp.metas_indicador (codigo, meta, tolerancia, justificacion, actualizado_por)
            VALUES (:c, :m, :t, :j, :u)
            ON CONFLICT (codigo) DO UPDATE SET meta = EXCLUDED.meta, tolerancia = EXCLUDED.tolerancia,
                justificacion = EXCLUDED.justificacion, actualizado_por = EXCLUDED.actualizado_por,
                actualizado_en = now()
        """), {"c": codigo, "m": valor_meta, "t": valor_tolerancia, "j": justificacion[:400], "u": usuario.username})
        db.execute(text("UPDATE academico_oltp.indicadores SET perspectiva = :p, responsable_cargo = :r "
                        "WHERE codigo = :c"), {"p": perspectiva, "r": responsable_cargo, "c": codigo})
    except DBAPIError as exc:
        db.rollback()
        diag = getattr(exc.orig, "diag", None)
        return redirigir(request, destino, error=diag.message_primary if diag else "La base rechazó la meta.")
    return redirigir(request, destino, ok=f"Meta de «{indicador['nombre']}» guardada. "
                                          "Recarga el Data Warehouse para verla en el tablero.")
