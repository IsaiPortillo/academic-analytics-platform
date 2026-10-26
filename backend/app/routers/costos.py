"""Catálogo de costos institucionales — administración del costo por unidad valorativa.

Mantiene `academico_oltp.costos_uv`, la tabla de la que depende TODA la cifra de
negocio del proyecto: el costo de una materia es `unidades_valorativas ×
costo_por_uv` del período, y de ahí salen las tres medidas monetarias del Data
Warehouse.

Hasta ahora esa tabla solo se podía editar con psql, aunque rol_coordinador ya
tenía los permisos desde 08_costos_institucionales.sql. Este módulo usa esos
permisos que ya existían; no concede ninguno nuevo.

Dos decisiones que conviene conocer:

  - La `fuente` es obligatoria. No es burocracia: es lo que permite sustentar la
    cifra ante el jurado. Un costo sin procedencia declarada es un número
    inventado, y la columna existe justamente para distinguir un dato
    presupuestario oficial de un supuesto paramétrico.

  - Guardar aquí NO actualiza el Data Warehouse. El costo viaja a dim_periodo y
    a las medidas del hecho durante la carga, así que después de editar hay que
    correr `python -m etl.carga`. La interfaz lo advierte en vez de dejar que el
    tablero muestre cifras viejas sin explicación.
"""

from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from .. import dw, recarga
from ..database import get_db
from ..dependencies import UsuarioSesion, requiere_rol
from ..models import CostoUV, PeriodoAcademico
from ..templating import templates

router = APIRouter(prefix="/costos", tags=["costos"])

# Mismo texto que siembra 08_costos_institucionales.sql. Sirve para marcar en la
# interfaz qué períodos siguen con el valor de arranque y cuáles ya tienen una
# cifra sustentada.
MARCA_SUPUESTO = "SUPUESTO PARAMETRICO"

MONEDAS = ("USD", "SVC", "EUR")


def _periodos_con_costo(db: Session):
    """Todos los períodos con su costo, incluidos los que aún no tienen ninguno."""
    filas = db.execute(
        select(PeriodoAcademico, CostoUV)
        .outerjoin(CostoUV, CostoUV.periodo_id == PeriodoAcademico.periodo_id)
        .order_by(PeriodoAcademico.anio, PeriodoAcademico.codigo_periodo)
    ).all()
    return [
        {
            "periodo": periodo,
            "costo": costo,
            "es_supuesto": bool(costo and MARCA_SUPUESTO in (costo.fuente or "").upper()),
        }
        for periodo, costo in filas
    ]


@router.get("")
def listar(
    request: Request,
    ok: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    filas = _periodos_con_costo(db)
    # Si el DW no está disponible la página debe seguir sirviendo: editar costos
    # no depende de él, solo el aviso de cuándo se cargó por última vez.
    try:
        ultima_carga = dw.ultima_carga()
    except Exception:  # noqa: BLE001 - el detalle ya queda en el log del servidor
        ultima_carga = None
    return templates.TemplateResponse(
        request,
        "modulos/costos.html",
        {
            "usuario": usuario,
            "filas": filas,
            "ultima_carga": ultima_carga,
            "carga_en_curso": recarga.hay_carga_en_curso(),
            "monedas": MONEDAS,
            "sin_costo": sum(1 for f in filas if f["costo"] is None),
            "con_supuesto": sum(1 for f in filas if f["es_supuesto"]),
            "ok": ok,
            "error": error,
        },
    )


@router.post("/recargar")
def recargar(
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
):
    """Recarga el Data Warehouse para que el tablero vea los costos editados.

    No recibe `db`: la carga la hace un proceso aparte con su propio rol de
    escritura (ver app/recarga.py). Esta ruta solo la dispara.
    """
    resultado = recarga.ejecutar_carga()
    if resultado.ok:
        return RedirectResponse(f"/costos?ok={resultado.mensaje}", status_code=303)

    mensaje = resultado.mensaje
    if resultado.detalle:
        # Una sola línea: la interfaz no es el lugar para una traza entera, pero
        # sin ninguna pista el coordinador no sabe ni a quién avisar.
        mensaje += f" Detalle: {resultado.detalle.splitlines()[-1][:160]}"
    return RedirectResponse(f"/costos?error={mensaje}", status_code=303)


# Declarada ANTES de "/{periodo_id}": FastAPI resuelve las rutas en orden, y
# "/{periodo_id}" tambien casa con "/costos/recargar", intentando convertir
# "recargar" a entero y devolviendo 422.
@router.post("/{periodo_id}")
def guardar(
    periodo_id: int,
    costo_por_uv: str = Form(...),
    moneda: str = Form("USD"),
    fuente: str = Form(...),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    fuente = fuente.strip()
    if not fuente:
        return RedirectResponse(
            "/costos?error=La fuente es obligatoria: una cifra sin procedencia declarada "
            "no se puede sustentar", status_code=303
        )

    # Se valida aquí para dar un mensaje entendible, pero quien realmente impide
    # un costo no positivo es el CHECK de la tabla.
    try:
        valor = Decimal(costo_por_uv.replace(",", "."))
    except (InvalidOperation, AttributeError):
        return RedirectResponse(
            f"/costos?error=«{costo_por_uv}» no es una cantidad válida", status_code=303
        )
    if valor <= 0:
        return RedirectResponse(
            "/costos?error=El costo por unidad valorativa debe ser mayor que cero",
            status_code=303,
        )

    if moneda not in MONEDAS:
        return RedirectResponse(f"/costos?error=Moneda no reconocida: {moneda}", status_code=303)

    periodo = db.get(PeriodoAcademico, periodo_id)
    if periodo is None:
        return RedirectResponse("/costos?error=Período no encontrado", status_code=303)

    registro = db.scalar(select(CostoUV).where(CostoUV.periodo_id == periodo_id))
    try:
        if registro is None:
            db.add(CostoUV(
                periodo_id=periodo_id, costo_por_uv=valor, moneda=moneda, fuente=fuente
            ))
            accion = "registrado"
        else:
            registro.costo_por_uv = valor
            registro.moneda = moneda
            registro.fuente = fuente
            accion = "actualizado"
        db.flush()
    except DBAPIError:
        db.rollback()
        return RedirectResponse(
            "/costos?error=La base de datos rechazó la operación", status_code=303
        )

    return RedirectResponse(
        f"/costos?ok=Costo {accion} para {periodo.codigo_periodo}. "
        f"Para que el cambio llegue al tablero hay que recargar el Data Warehouse "
        f"(python -m etl.carga)",
        status_code=303,
    )
