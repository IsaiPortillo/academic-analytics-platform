"""Cubo OLAP — resultados por dimensiones con subtotales (ROLLUP / CUBE).

Reemplaza la maqueta «Alertas & OLAP» de /analitica-olap. El coordinador elige
hasta tres dimensiones del catálogo de app/olap.py y PostgreSQL calcula las medidas
de cada combinación, los subtotales y el total sobre fact_inscripcion.

Lee solo el Data Warehouse con rol_dashboard (app/dw.py). Es descriptivo: no hay
alertas de deserción ni proyecciones; el análisis de los estudiantes que ya
presentan el patrón de riesgo observado vive en /analisis-diagnostico.
"""

import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.exc import DBAPIError

from .. import dw, indicadores as ind, olap
from ..dependencies import UsuarioSesion, requiere_rol
from ..templating import templates

router = APIRouter(prefix="/analitica-olap", tags=["analitica"])

TODOS = "todos"
PLANTILLA = "analitica_olap.html"
# Con filtros vacíos el cubo por defecto: cómo cambia la reprobación por período y ciclo del plan.
POR_DEFECTO = ["periodo", "ciclo"]


def _error(request: Request, usuario: UsuarioSesion, mensaje: str):
    return templates.TemplateResponse(request, PLANTILLA, {"usuario": usuario, "error": mensaje})


def _contexto_filtros(periodo, departamento, carrera):
    """Valida los filtros contra el catálogo (llegan por URL) y los traduce a dw.Filtros."""
    periodos = dw.catalogo_periodos()
    carreras = dw.catalogo_carreras()
    codigos = periodos["codigo_periodo"].tolist()
    sel_periodos = () if periodo in (None, TODOS) or periodo not in codigos else (periodo,)
    departamentos = (carreras[["codigo_departamento", "nombre_departamento"]]
                     .drop_duplicates().to_dict("records"))
    if departamento not in {d["codigo_departamento"] for d in departamentos}:
        departamento = None
    visibles = carreras if not departamento else carreras[carreras["codigo_departamento"] == departamento]
    if carrera not in set(visibles["codigo_carrera"]):
        carrera = None
    filtros = dw.Filtros(sel_periodos, (carrera,) if carrera else (), (departamento,) if departamento else ())
    seleccion = periodos[periodos["codigo_periodo"].isin(sel_periodos)] if sel_periodos else periodos
    moneda = seleccion["moneda"].dropna().iloc[0] if seleccion["moneda"].notna().any() else "USD"
    return {
        "codigos": codigos, "periodo": sel_periodos[0] if sel_periodos else TODOS,
        "departamentos": departamentos, "departamento": departamento,
        "carreras": visibles.to_dict("records"), "carrera": carrera,
        "filtros": filtros, "moneda": moneda, "seleccion": seleccion,
    }


def _dimensiones(d1, d2, d3) -> list[str]:
    elegidas = olap.validar_dimensiones([d1, d2, d3])
    return elegidas or list(POR_DEFECTO)


@router.get("")
def cubo_olap(
    request: Request,
    d1: Optional[str] = Query(None),
    d2: Optional[str] = Query(None),
    d3: Optional[str] = Query(None),
    modo: Optional[str] = Query(None),
    periodo: Optional[str] = Query(None),
    departamento: Optional[str] = Query(None),
    carrera: Optional[str] = Query(None),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
):
    try:
        ctx = _contexto_filtros(periodo, departamento, carrera)
        dims = _dimensiones(d1, d2, d3)
        modo = olap.validar_modo(modo)
        df = dw.cubo(ctx["filtros"], dims, modo)
    except dw.DWNoConfigurado as exc:
        return _error(request, usuario, str(exc))
    except DBAPIError:
        return _error(request, usuario,
                      "No se pudo leer el Data Warehouse. Verifica que exista (database/oltp/10 a 15) "
                      "y que esté cargado: python -m etl.carga")

    truncado = len(df) > olap.LIMITE_FILAS
    filas = olap.preparar_filas(df.head(olap.LIMITE_FILAS), dims, ctx["moneda"])
    elegidas = dims + [""] * (olap.MAX_DIMENSIONES - len(dims))

    fuentes = ctx["seleccion"]["fuente_costo"].dropna().unique().tolist()
    supuesto = None
    if any("SUPUESTO" in f.upper() for f in fuentes):
        supuesto = {"cifra": ", ".join(ind.dinero(c, ctx["moneda"])
                                       for c in ctx["seleccion"]["costo_por_uv"].dropna().unique()),
                    "fuente": fuentes[0]}

    return templates.TemplateResponse(request, PLANTILLA, {
        "usuario": usuario,
        "periodos": ctx["codigos"], "periodo": ctx["periodo"],
        "departamentos": ctx["departamentos"], "departamento": ctx["departamento"],
        "carreras": ctx["carreras"], "carrera": ctx["carrera"],
        "dimensiones": olap.DIMENSIONES, "elegidas": elegidas, "modos": olap.MODOS, "modo": modo,
        "etiquetas": olap.etiquetas(dims),
        "filas": filas, "truncado": truncado, "limite": olap.LIMITE_FILAS,
        "lectura": olap.leer_cubo(filas, dims, modo, ctx["moneda"]),
        "supuesto": supuesto, "moneda": ctx["moneda"],
        "ultima_carga": dw.ultima_carga(),
        "consulta": request.url.query,
    })


@router.get("/csv")
def cubo_csv(
    d1: Optional[str] = Query(None),
    d2: Optional[str] = Query(None),
    d3: Optional[str] = Query(None),
    modo: Optional[str] = Query(None),
    periodo: Optional[str] = Query(None),
    departamento: Optional[str] = Query(None),
    carrera: Optional[str] = Query(None),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
):
    """El mismo cubo que muestra la pantalla, completo, en CSV."""
    ctx = _contexto_filtros(periodo, departamento, carrera)
    dims = _dimensiones(d1, d2, d3)
    modo = olap.validar_modo(modo)
    filas = olap.preparar_filas(dw.cubo(ctx["filtros"], dims, modo).head(olap.LIMITE_FILAS), dims, ctx["moneda"])
    salida = io.StringIO()
    escritor = csv.writer(salida)
    escritor.writerow(olap.etiquetas(dims) + ["Nivel", "Con nota final", "Reprobados",
                                              "Tasa de reprobación", "Nota promedio",
                                              f"Costo de reprobación ({ctx['moneda']})"])
    for f in filas:
        escritor.writerow(f["celdas"] + [f["nivel"], f["cerradas"], f["reprobados"],
                                         "" if f["tasa"] is None else f"{f['tasa']:.4f}",
                                         "" if f["nota_texto"] == "—" else f["nota_texto"],
                                         f"{f['costo']:.2f}"])
    return Response(
        content="﻿" + salida.getvalue(),  # BOM: Excel abre bien las tildes
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="cubo_olap.csv"'},
    )
