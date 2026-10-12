"""Dashboard estratégico — panorama institucional (datos reales del DW).

Reemplaza la maqueta ilustrativa que había en /dashboard. Igual que la vista
ejecutiva y el análisis diagnóstico, NO usa database.get_db() ni consulta Neo4j:
lee el Data Warehouse con su propia conexión como rol_dashboard (app/dw.py).
La malla (materias que más bloquean) llega al DW desde Neo4j por el ETL.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.exc import DBAPIError

from .. import dashboard_estrategico as panel, dw, indicadores as ind, red_curricular as rc
from ..dependencies import UsuarioSesion, requiere_rol
from ..templating import templates
from .vista_ejecutiva import _variacion

router = APIRouter(prefix="/dashboard", tags=["analitica"])

TODOS = "todos"
PLANTILLA = "dashboard.html"


def _error(request: Request, usuario: UsuarioSesion, mensaje: str):
    return templates.TemplateResponse(request, PLANTILLA, {"usuario": usuario, "error": mensaje})


@router.get("")
def dashboard_estrategico(
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
        return _error(request, usuario, str(exc))
    except DBAPIError:
        return _error(request, usuario,
                      "No se pudo leer el Data Warehouse. Verifica que exista (database/oltp/10 a 15) "
                      "y que esté cargado: python -m etl.carga")
    if periodos.empty:
        return _error(request, usuario, "El Data Warehouse está vacío. Cárgalo con: python -m etl.carga")

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
    filtros = dw.Filtros(sel_periodos, (carrera,) if carrera else (),
                         (departamento,) if departamento else ())

    seleccion = periodos[periodos["codigo_periodo"].isin(sel_periodos)] if sel_periodos else periodos
    moneda = seleccion["moneda"].dropna().iloc[0] if seleccion["moneda"].notna().any() else "USD"

    def dinero(v):
        return ind.dinero(v, moneda)

    # --- Indicadores (con variación contra el período anterior si hay uno solo) -----
    actual = ind.calcular(dw.totales(filtros))
    periodo_anterior = None
    if len(sel_periodos) == 1:
        posicion = codigos.index(sel_periodos[0])
        periodo_anterior = codigos[posicion - 1] if posicion > 0 else None
    previo = ind.calcular(dw.totales(filtros.con_periodos((periodo_anterior,)))) if periodo_anterior else None

    def aprobacion(i):
        return None if i is None or i.tasa_reprobacion is None else 1 - i.tasa_reprobacion

    tarjetas = [
        {"etiqueta": "Estudiantes evaluados", "valor": f"{actual.estudiantes_evaluados:,}",
         "ayuda": "Estudiantes distintos con al menos una inscripción con nota final.",
         "variacion": _variacion(actual.estudiantes_evaluados,
                                 previo.estudiantes_evaluados if previo else None,
                                 lambda v: f"{v:,.0f}", menor_es_mejor=False)},
        {"etiqueta": "Tasa de aprobación", "valor": ind.porcentaje(aprobacion(actual)),
         "ayuda": "Inscripciones aprobadas entre las que tienen nota final.",
         "variacion": _variacion(aprobacion(actual), aprobacion(previo),
                                 lambda v: ind.formatear_cambio(v, "puntos", moneda), menor_es_mejor=False)},
        {"etiqueta": "Costo de reprobación", "valor": dinero(actual.costo_reprobacion),
         "ayuda": "Lo que la institución invirtió en inscripciones que terminaron reprobadas.",
         "variacion": _variacion(actual.costo_reprobacion, previo.costo_reprobacion if previo else None,
                                 lambda v: dinero(v))},
        {"etiqueta": "Costo por estudiante que reprobó", "valor": dinero(actual.costo_por_estudiante),
         "ayuda": "Costo de reprobación entre los estudiantes distintos que reprobaron.",
         "variacion": _variacion(actual.costo_por_estudiante,
                                 previo.costo_por_estudiante if previo else None, lambda v: dinero(v))},
    ]

    # --- Aprobación por ciclo del plan ----------------------------------------------
    ciclos = panel.aprobacion_por_ciclo(dw.aprobacion_por_ciclo(filtros), moneda)

    # --- Evolución de la reprobación por período -------------------------------------
    evolucion = dw.evolucion_por_periodo(filtros)
    maxima = float(evolucion["tasa_reprobacion"].max()) if not evolucion.empty and \
        evolucion["tasa_reprobacion"].notna().any() else 0.0
    columnas = [
        {"codigo": f["codigo_periodo"], "tasa_texto": ind.porcentaje(f["tasa_reprobacion"]),
         "pct": (f["tasa_reprobacion"] / maxima) if maxima and f["tasa_reprobacion"] == f["tasa_reprobacion"] else 0,
         "seleccionado": not sel_periodos or f["codigo_periodo"] in sel_periodos}
        for f in evolucion.to_dict("records")
    ]

    # --- Materias que más bloquean la malla ------------------------------------------
    malla, relaciones = dw.malla(), dw.prerrequisitos()
    cruce = rc.cruce_costo_posicion(malla, dw.costo_por_materia(filtros))
    materias = panel.materias_que_mas_bloquean(cruce, moneda)
    sin_red = not len(relaciones)

    fuentes = seleccion["fuente_costo"].dropna().unique().tolist()
    supuesto = None
    if any("SUPUESTO" in f.upper() for f in fuentes):
        supuesto = {"cifra": ", ".join(dinero(c) for c in seleccion["costo_por_uv"].dropna().unique()),
                    "fuente": fuentes[0]}

    return templates.TemplateResponse(request, PLANTILLA, {
        "usuario": usuario,
        "periodos": codigos,
        "periodo": sel_periodos[0] if sel_periodos else TODOS,
        "departamentos": departamentos,
        "departamento": departamento,
        "carreras": carreras_visibles.to_dict("records"),
        "carrera": carrera,
        "etiqueta_periodo": sel_periodos[0] if sel_periodos else "todos los períodos",
        "periodo_anterior": periodo_anterior,
        "tarjetas": tarjetas,
        "sin_datos": not actual.hay_datos,
        "ciclos": ciclos,
        "lectura_ciclos": panel.leer_aprobacion(ciclos),
        "columnas": columnas,
        "materias": materias,
        "sin_red": sin_red,
        "lectura_impacto": panel.leer_impacto(materias, int(cruce["bloqueos"].sum())) if not sin_red else rc.SIN_RED,
        "cuellos": int(cruce["es_cuello_botella"].fillna(False).astype(bool).sum()),
        "supuesto": supuesto,
        "ultima_carga": dw.ultima_carga(),
        "moneda": moneda,
    })
