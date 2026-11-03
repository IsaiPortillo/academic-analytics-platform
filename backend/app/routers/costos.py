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

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from .. import dw, recarga
from ..avisos import redirigir, tomar_aviso
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


SIN_COSTO, EN_TABLERO, PENDIENTE = "sin_costo", "en_tablero", "pendiente"


def estado_en_tablero(costo, en_almacen):
    """¿El costo guardado en el OLTP ya llegó al Data Warehouse?

    `en_almacen` es lo que dim_periodo tiene hoy para el período (o None si el
    período ni siquiera está). Se compara lo que importa para las cifras —el
    valor por UV a dos decimales— y también la moneda y la fuente, porque la
    fuente viaja al tablero para advertir cuando la cifra es un supuesto.
    """
    if costo is None:
        return SIN_COSTO
    if not en_almacen or en_almacen.get("costo_por_uv") is None:
        return PENDIENTE
    mismo_valor = Decimal(str(round(en_almacen["costo_por_uv"], 2))) == costo.costo_por_uv.quantize(Decimal("0.01"))
    if mismo_valor and en_almacen.get("moneda") == costo.moneda and en_almacen.get("fuente") == costo.fuente:
        return EN_TABLERO
    return PENDIENTE


def _periodos_con_costo(db: Session, almacen=None):
    """Todos los períodos con su costo, incluidos los que aún no tienen ninguno.

    almacen: lo que devuelve dw.costos_cargados(), o None si no se pudo consultar
    (entonces no se afirma nada sobre el tablero: el estado queda en None).
    """
    filas = db.execute(
        select(PeriodoAcademico, CostoUV)
        .outerjoin(CostoUV, CostoUV.periodo_id == PeriodoAcademico.periodo_id)
        .order_by(PeriodoAcademico.anio, PeriodoAcademico.codigo_periodo)
    ).all()
    resultado = []
    for periodo, costo in filas:
        en_almacen = None if almacen is None else almacen.get(periodo.periodo_id)
        resultado.append({
            "periodo": periodo,
            "costo": costo,
            "es_supuesto": bool(costo and MARCA_SUPUESTO in (costo.fuente or "").upper()),
            "estado": None if almacen is None else estado_en_tablero(costo, en_almacen),
            "en_almacen": en_almacen,
        })
    return resultado


@router.get("")
def listar(
    request: Request,
    guardado: Optional[int] = None,
    recargado: Optional[int] = None,
    usuario: UsuarioSesion = Depends(requiere_rol("rol_admin")),
    db: Session = Depends(get_db),
):
    ok, error = tomar_aviso(request)
    # Si el DW no está disponible la página debe seguir sirviendo: editar costos
    # no depende de él, solo el aviso de cuándo se cargó y de si el tablero está
    # al día.
    try:
        ultima_carga = dw.ultima_carga()
        almacen = dw.costos_cargados()
    except Exception:  # noqa: BLE001 - el detalle ya queda en el log del servidor
        ultima_carga, almacen = None, None
    filas = _periodos_con_costo(db, almacen)
    pendientes = [f for f in filas if f["estado"] == PENDIENTE]
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
            "almacen_consultado": almacen is not None,
            "pendientes": pendientes,
            "al_dia": sum(1 for f in filas if f["estado"] == EN_TABLERO),
            "guardado": guardado,
            "recargado": bool(recargado),
            "ok": ok,
            "error": error,
        },
    )


@router.post("/recargar")
def recargar(
    request: Request,
    usuario: UsuarioSesion = Depends(requiere_rol("rol_admin")),
):
    """Recarga el Data Warehouse para que el tablero vea los costos editados.

    No recibe `db`: la carga la hace un proceso aparte con su propio rol de
    escritura (ver app/recarga.py). Esta ruta solo la dispara.
    """
    resultado = recarga.ejecutar_carga()
    if resultado.ok:
        # El resultado se muestra dentro de la tarjeta de recarga (?recargado=1#recarga),
        # a donde lleva la página: un aviso arriba quedaría fuera de la vista.
        return RedirectResponse("/costos?recargado=1#recarga", status_code=303)

    mensaje = resultado.mensaje
    if resultado.detalle:
        # Una sola línea: la interfaz no es el lugar para una traza entera, pero
        # sin ninguna pista el coordinador no sabe ni a quién avisar.
        mensaje += f" Detalle: {resultado.detalle.splitlines()[-1][:160]}"
    return redirigir(request, "/costos", error=mensaje)


# Declarada ANTES de "/{periodo_id}": FastAPI resuelve las rutas en orden, y
# "/{periodo_id}" tambien casa con "/costos/recargar", intentando convertir
# "recargar" a entero y devolviendo 422.
@router.post("/{periodo_id}")
def guardar(
    request: Request,
    periodo_id: int,
    costo_por_uv: str = Form(...),
    moneda: str = Form("USD"),
    fuente: str = Form(...),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_admin")),
    db: Session = Depends(get_db),
):
    fuente = fuente.strip()
    if not fuente:
        return redirigir(request, "/costos", error=(
            "La fuente es obligatoria: una cifra sin procedencia declarada no se puede sustentar"
        ))

    # Se valida aquí para dar un mensaje entendible, pero quien realmente impide
    # un costo no positivo es el CHECK de la tabla.
    try:
        valor = Decimal(costo_por_uv.replace(",", "."))
    except (InvalidOperation, AttributeError):
        return redirigir(request, "/costos", error=f"«{costo_por_uv}» no es una cantidad válida")
    if valor <= 0:
        return redirigir(request, "/costos", error="El costo por unidad valorativa debe ser mayor que cero")

    if moneda not in MONEDAS:
        return redirigir(request, "/costos", error=f"Moneda no reconocida: {moneda}")

    periodo = db.get(PeriodoAcademico, periodo_id)
    if periodo is None:
        return redirigir(request, "/costos", error="Período no encontrado")

    registro = db.scalar(select(CostoUV).where(CostoUV.periodo_id == periodo_id))
    try:
        if registro is None:
            db.add(CostoUV(
                periodo_id=periodo_id, costo_por_uv=valor, moneda=moneda, fuente=fuente
            ))
        else:
            registro.costo_por_uv = valor
            registro.moneda = moneda
            registro.fuente = fuente
        db.flush()
    except DBAPIError:
        db.rollback()
        return redirigir(request, "/costos", error="La base de datos rechazó la operación")

    # La confirmación va en la fila del período (?guardado=<id>#costo-<id>): con la
    # lista larga, un aviso arriba queda fuera de la vista y no se sabe si guardó.
    return RedirectResponse(f"/costos?guardado={periodo_id}#costo-{periodo_id}", status_code=303)
