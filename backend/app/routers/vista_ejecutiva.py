"""Vista ejecutiva: costo y rendimiento del ciclo — Fase 4.1.

Para el coordinador académico: qué ocurrió con el rendimiento y cuánto costó,
sin escribir consultas. Nivel analítico descriptivo.

A diferencia del resto de la aplicación, esta ruta NO usa database.get_db():
esa sesión adopta rol_coordinador, que puede leer el esquema operacional. Los
datos salen de app/dw.py, que se conecta como rol_dashboard y solo puede leer
dw_academico. La restricción a coordinadores (requiere_rol) decide quién ve la
pantalla; los GRANT de PostgreSQL deciden qué datos puede tocar.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.exc import DBAPIError

from .. import dw, indicadores as ind
from ..dependencies import UsuarioSesion, requiere_rol
from ..templating import templates

router = APIRouter(prefix="/vista-ejecutiva", tags=["analitica"])

TODOS = "todos"
LIMITE_RANKING = 10


def _variacion(actual, previo, formato, menor_es_mejor=True) -> Optional[dict]:
    """Texto y clase CSS de la variación contra el período anterior.

    En los cuatro KPIs subir es empeorar, así que el rojo marca el aumento.
    La flecha siempre indica la dirección real del cambio.
    """
    if actual is None or previo is None:
        return None
    diferencia = actual - previo
    if abs(diferencia) < 1e-9:
        return {"texto": "= sin cambio", "clase": "kpi-trend-neutral"}
    empeora = diferencia > 0 if menor_es_mejor else diferencia < 0
    return {
        "texto": f"{'↑' if diferencia > 0 else '↓'} {formato(abs(diferencia))}",
        "clase": "kpi-trend-down" if empeora else "kpi-trend-up",
    }


def _render_error(request, usuario, mensaje):
    return templates.TemplateResponse(
        request, "modulos/vista_ejecutiva.html", {"usuario": usuario, "error": mensaje},
    )


@router.get("")
def vista_ejecutiva(
    request: Request,
    periodo: Optional[str] = Query(None),
    departamento: Optional[str] = Query(None),
    carrera: Optional[str] = Query(None),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
):
    try:
        periodos = dw.catalogo_periodos()
        carreras = dw.catalogo_carreras()
    except dw.DWNoConfigurado as exc:
        return _render_error(request, usuario, str(exc))
    except DBAPIError:
        return _render_error(
            request, usuario,
            "No se pudo leer el Data Warehouse. Verifica que exista (database/oltp/10 y 11) "
            "y que esté cargado: python -m etl.carga",
        )
    if periodos.empty:
        return _render_error(request, usuario,
                             "El Data Warehouse está vacío. Cárgalo con: python -m etl.carga")

    # Valores fuera del catálogo se ignoran en vez de fallar: llegan por URL.
    codigos = periodos["codigo_periodo"].tolist()
    if periodo is None:
        periodo = codigos[-1]  # por defecto, el ciclo más reciente
    sel_periodos = () if periodo == TODOS or periodo not in codigos else (periodo,)
    departamentos = (carreras[["codigo_departamento", "nombre_departamento"]]
                     .drop_duplicates().to_dict("records"))
    if departamento not in {d["codigo_departamento"] for d in departamentos}:
        departamento = None
    carreras_visibles = carreras if not departamento else carreras[
        carreras["codigo_departamento"] == departamento
    ]
    if carrera not in set(carreras_visibles["codigo_carrera"]):
        carrera = None

    filtros = dw.Filtros(
        sel_periodos,
        (carrera,) if carrera else (),
        (departamento,) if departamento else (),
    )
    seleccion = periodos[periodos["codigo_periodo"].isin(sel_periodos)] if sel_periodos else periodos
    moneda = seleccion["moneda"].dropna().iloc[0] if seleccion["moneda"].notna().any() else "USD"

    totales = ind.calcular(dw.totales(filtros))
    periodo_anterior = None
    if len(sel_periodos) == 1:
        posicion = codigos.index(sel_periodos[0])
        periodo_anterior = codigos[posicion - 1] if posicion > 0 else None
    previos = (ind.calcular(dw.totales(filtros.con_periodos((periodo_anterior,))))
               if periodo_anterior else None)

    def dinero(v):
        return ind.dinero(v, moneda)

    kpis = [
        {
            "etiqueta": t.etiqueta,
            "valor": t.valor,
            "ayuda": t.ayuda,
            "variacion": _variacion(t.actual, t.previo,
                                    lambda v, t=t: ind.formatear_cambio(v, t.formato, moneda)),
            "texto": t.texto,
        }
        for t in ind.tarjetas(totales, previos, periodo_anterior, moneda)
    ]

    ranking = dw.ranking_materias(filtros, LIMITE_RANKING)
    maximo_ranking = float(ranking["costo_reprobacion"].max()) if not ranking.empty else 0.0
    filas_ranking = [
        {
            **fila,
            "costo_texto": dinero(fila["costo_reprobacion"]),
            "tasa_texto": ind.porcentaje(fila["tasa_reprobacion"]),
            "pct": fila["costo_reprobacion"] / maximo_ranking if maximo_ranking else 0,
        }
        for fila in ranking.to_dict("records")
    ]

    evolucion = dw.evolucion_por_periodo(filtros)
    maximo_evolucion = float(evolucion["costo_reprobacion"].max()) if not evolucion.empty else 0.0
    columnas = [
        {
            "codigo": fila["codigo_periodo"],
            "costo_texto": dinero(fila["costo_reprobacion"]),
            "tasa_texto": ind.porcentaje(fila["tasa_reprobacion"]),
            "pct": fila["costo_reprobacion"] / maximo_evolucion if maximo_evolucion else 0,
            "seleccionado": not sel_periodos or fila["codigo_periodo"] in sel_periodos,
        }
        for fila in evolucion.to_dict("records")
    ]
    texto_evolucion = ind.interpretar_evolucion(evolucion, moneda)

    # El aviso sale del dato (costos_uv.fuente → dim_periodo.fuente_costo), no
    # está escrito aquí: con la cifra oficial registrada, desaparece solo.
    fuentes = seleccion["fuente_costo"].dropna().unique().tolist()
    supuesto = None
    if any("SUPUESTO" in f.upper() for f in fuentes):
        supuesto = {
            "cifra": ", ".join(dinero(c) for c in seleccion["costo_por_uv"].dropna().unique()),
            "fuente": fuentes[0],
        }

    return templates.TemplateResponse(
        request,
        "modulos/vista_ejecutiva.html",
        {
            "usuario": usuario,
            "periodos": codigos,
            "periodo": periodo if sel_periodos else TODOS,
            "departamentos": departamentos,
            "departamento": departamento,
            "carreras": carreras_visibles.to_dict("records"),
            "carrera": carrera,
            "etiqueta_periodo": sel_periodos[0] if sel_periodos else "todos los períodos",
            "periodo_anterior": periodo_anterior,
            "kpis": kpis,
            "ranking": filas_ranking,
            "texto_ranking": ind.interpretar_ranking(ranking, totales.costo_reprobacion, moneda),
            "columnas": columnas,
            "texto_evolucion": texto_evolucion,
            "supuesto": supuesto,
            "ultima_carga": dw.ultima_carga(),
            "moneda": moneda,
        },
    )
