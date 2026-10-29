"""Red curricular y materias cuello de botella — Fase 4.3 (SCRUM-46).

Para el coordinador académico: ver la malla como red, qué materias frenan a más
estudiantes y por qué su costo de reprobación se propaga. Nivel analítico
diagnóstico (¿por qué ocurrió?), sobre datos históricos: no pronostica ni
recomienda.

Igual que la vista ejecutiva, NO usa database.get_db() ni habla con Neo4j: lee el
Data Warehouse con su propia conexión como rol_dashboard (app/dw.py). La malla
llegó al DW desde Neo4j por el ETL (dim_materia con las métricas y
bridge_prerrequisito con las relaciones), así que esta pantalla no necesita
ninguna credencial del grafo y sigue funcionando con Neo4j apagado.
"""

from typing import Optional

import networkx as nx
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.exc import DBAPIError

from .. import dw, indicadores as ind, red_curricular as rc
from ..dependencies import UsuarioSesion, requiere_rol
from ..templating import templates

router = APIRouter(prefix="/red-curricular", tags=["analitica"])

TODOS = "todos"
PLANTILLA = "modulos/red_curricular.html"


def _error(request: Request, usuario: UsuarioSesion, mensaje: str):
    return templates.TemplateResponse(request, PLANTILLA, {"usuario": usuario, "error": mensaje})


@router.get("")
def red_curricular(
    request: Request,
    periodo: Optional[str] = Query(None),
    departamento: Optional[str] = Query(None),
    carrera: Optional[str] = Query(None),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
):
    try:
        periodos = dw.catalogo_periodos()
        carreras = dw.catalogo_carreras()
        materias = dw.malla()
        relaciones = dw.prerrequisitos()
    except dw.DWNoConfigurado as exc:
        return _error(request, usuario, str(exc))
    except DBAPIError:
        return _error(
            request, usuario,
            "No se pudo leer la malla del Data Warehouse. Verifica que exista (database/oltp/10 a 15) "
            "y que esté cargado: python -m etl.carga",
        )
    if materias.empty:
        return _error(request, usuario, "El Data Warehouse está vacío. Cárgalo con: python -m etl.carga")

    red = rc.construir_red(materias, relaciones)
    if not red.number_of_edges():
        return _error(request, usuario, rc.SIN_RED)
    if not nx.is_directed_acyclic_graph(red):
        return _error(request, usuario,
                      "La malla cargada en el Data Warehouse tiene un ciclo de prerrequisitos, y una malla "
                      "así no se puede cursar. Revisa el grafo de Neo4j y recarga con: python -m etl.carga")

    # El diagnóstico mira el historial: por defecto, todos los períodos.
    codigos = periodos["codigo_periodo"].tolist()
    sel_periodos = (periodo,) if periodo in codigos else ()
    # La red es la de las carreras que tienen malla en el grafo; las demás no tienen qué dibujar.
    carreras = carreras[carreras["codigo_carrera"].isin(set(materias["codigo_carrera"]))]
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

    cruce = rc.cruce_costo_posicion(materias, dw.costo_por_materia(filtros))
    disposicion = rc.disponer(red)

    nodos = []
    for fila in cruce.to_dict("records"):
        codigo = fila["codigo_materia"]
        posicion = disposicion["nodos"][codigo]
        nodos.append({
            "codigo": codigo,
            "nombre": fila["nombre_materia"],
            "ciclo": int(fila["ciclo_plan"]),
            "area": fila["area"],
            "x": posicion["x"],
            "y": posicion["y"],
            "calor": fila["dependientes_totales"] / max(int(cruce["dependientes_totales"].max()), 1),
            "cuello": bool(fila["es_cuello_botella"]),
            "directos": int(fila["dependientes_directos"]),
            "indirectos": int(fila["dependientes_indirectos"]),
            "totales": int(fila["dependientes_totales"]),
            "pct_plan": ind.porcentaje(fila["indice_bloqueo"]),
            "cascada": int(fila["longitud_cascada"]),
            "costo": dinero(fila["costo_reprobacion"]),
            "reprobados": int(fila["reprobados"]),
            "tasa": ind.porcentaje(fila["tasa_reprobacion"] if fila["tasa_reprobacion"] == fila["tasa_reprobacion"] else None),
            "pct_costo": ind.porcentaje(fila["pct_costo"]),
            "bloqueos": int(fila["bloqueos"]),
            "tipo": fila["tipo"],
            "tipo_texto": fila["tipo_texto"],
            "dependientes": sorted(nx.descendants(red, codigo)),
            "dependientes_directos": sorted(red.successors(codigo)),
            "requisitos": sorted(nx.ancestors(red, codigo)),
            "requisitos_directos": sorted(red.predecessors(codigo)),
        })

    tabla = [
        {
            **fila,
            "costo_texto": dinero(fila["costo_reprobacion"]),
            "tasa_texto": ind.porcentaje(fila["tasa_reprobacion"] if fila["tasa_reprobacion"] == fila["tasa_reprobacion"] else None),
            "pct_plan_texto": ind.porcentaje(fila["indice_bloqueo"]),
            "pct_costo_texto": ind.porcentaje(fila["pct_costo"]),
            "pct_bloqueos_texto": ind.porcentaje(fila["pct_bloqueos"]),
        }
        for fila in cruce.to_dict("records")
    ]

    # El aviso sale del dato (costos_uv.fuente → dim_periodo.fuente_costo), no está
    # escrito aquí: con la cifra oficial registrada, desaparece solo.
    fuentes = seleccion["fuente_costo"].dropna().unique().tolist()
    supuesto = None
    if any("SUPUESTO" in f.upper() for f in fuentes):
        supuesto = {
            "cifra": ", ".join(dinero(c) for c in seleccion["costo_por_uv"].dropna().unique()),
            "fuente": fuentes[0],
        }

    cuellos = cruce[cruce["es_cuello_botella"].fillna(False).astype(bool)]
    inicial = cuellos.iloc[0]["codigo_materia"] if not cuellos.empty else nodos[0]["codigo"]
    cifras = rc.resumen(red, cruce)
    return templates.TemplateResponse(request, PLANTILLA, {
        "usuario": usuario,
        "periodos": codigos,
        "periodo": sel_periodos[0] if sel_periodos else TODOS,
        "departamentos": departamentos,
        "departamento": departamento,
        "carreras": carreras_visibles.to_dict("records"),
        "carrera": carrera,
        "etiqueta_periodo": sel_periodos[0] if sel_periodos else "todos los períodos",
        "resumen": {**cifras, "pct_costo_cuellos_texto": ind.porcentaje(cifras["pct_costo_cuellos"])},
        "disposicion": {k: v for k, v in disposicion.items() if k != "nodos"},
        "nodos": nodos,
        "red_datos": {"inicial": inicial, "nodos": {n["codigo"]: n for n in nodos}},
        "aristas": disposicion["aristas"],
        "alto_nodo": rc.ALTO_NODO,
        "ancho_nodo": rc.ANCHO_NODO,
        "tabla": tabla,
        "dispersion": rc.dispersion(cruce, moneda),
        "tipos": rc.TIPOS,
        "lectura_estructura": rc.leer_estructura(red),
        "lectura_cuellos": rc.leer_cuellos(red, materias),
        "lectura_cruce": rc.leer_cruce(cruce, red, moneda),
        "discrepancias": rc.discrepancias(red),
        "supuesto": supuesto,
        "ultima_carga": dw.ultima_carga(),
        "moneda": moneda,
    })
