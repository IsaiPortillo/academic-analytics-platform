"""Red curricular y materias cuello de botella — Fase 4.3 (SCRUM-46).

Nivel analítico diagnóstico (¿por qué un costo se propaga?). La malla curricular
es un grafo dirigido: (A)-[:REQUIERE_APROBADA]->(B) significa "para cursar A hay
que haber aprobado B". Aquí se arma ese grafo con NetworkX a partir de lo que el
ETL trajo de Neo4j al Data Warehouse (dim_materia + bridge_prerrequisito), se
dispone en columnas por ciclo para dibujarlo, se cruza con el costo de
reprobación de cada materia y se redacta lo que la red muestra.

Todo es función pura sobre DataFrames: no toca la base de datos, así que se
prueba sin ella (backend/tests/test_red_curricular.py).

Sentido de las flechas del dibujo: de prerrequisito a materia, es decir, en la
dirección en que avanza el estudiante. Los DEPENDIENTES de una materia son sus
descendientes en este grafo: lo que reprobarla deja sin poder cursar.
"""

from __future__ import annotations

from collections import defaultdict

import networkx as nx
import pandas as pd

from .indicadores import dinero, porcentaje

# Geometría del dibujo (unidades del viewBox del SVG).
ANCHO_NODO = 136
ALTO_NODO = 68
SEPARACION_COLUMNAS = 60
SEPARACION_FILAS = 24
MARGEN = 20
ALTO_ROTULOS = 28

# Una materia es cuello de botella si bloquea, directa o indirectamente, al menos
# esta fracción del resto del plan. Es el MISMO valor que usa el ETL para marcar
# dim_materia.es_cuello_botella (etl/grafo.py, SCRUM-34); etl/validar_dw.py
# comprueba que no se desalineen.
UMBRAL_CUELLO_BOTELLA = 0.25

SIN_RED = "La malla curricular aún no está cargada en el Data Warehouse."

TIPOS = {
    "propaga": "Costo que se propaga",
    "estructural": "Bloquea más de lo que cuesta",
    "contenido": "Costo contenido",
    "sin_hallazgo": "Sin hallazgo",
}


# ---------------------------------------------------------------------------
# El grafo
# ---------------------------------------------------------------------------

def construir_red(materias: pd.DataFrame, prerrequisitos: pd.DataFrame) -> nx.DiGraph:
    """Grafo dirigido prerrequisito -> materia. Las relaciones hacia una materia
    que no está en `materias` se ignoran: sin ficha no hay nada que dibujar."""
    red = nx.DiGraph()
    for fila in materias.to_dict("records"):
        red.add_node(fila["codigo_materia"], **fila)
    for fila in prerrequisitos.to_dict("records"):
        if fila["codigo_materia"] in red and fila["codigo_prerrequisito"] in red:
            red.add_edge(fila["codigo_prerrequisito"], fila["codigo_materia"])
    return red


def metricas_recalculadas(red: nx.DiGraph) -> dict[str, dict[str, int]]:
    """Las mismas métricas que calcula Neo4j (etl/grafo.py), pero recorriendo el
    grafo del DW. Sirven para comprobar que la estructura cargada y las métricas
    cargadas cuentan la misma historia."""
    longitud: dict[str, int] = {}
    for nodo in reversed(list(nx.topological_sort(red))):
        longitud[nodo] = max((longitud[s] + 1 for s in red.successors(nodo)), default=0)
    resultado = {}
    for nodo in red:
        totales = len(nx.descendants(red, nodo))
        directos = red.out_degree(nodo)
        resultado[nodo] = {
            "dependientes_directos": directos,
            "dependientes_indirectos": totales - directos,
            "dependientes_totales": totales,
            "longitud_cascada": longitud[nodo],
        }
    return resultado


def discrepancias(red: nx.DiGraph) -> list[str]:
    """Diferencias entre las métricas guardadas en dim_materia (calculadas en
    Neo4j) y las recalculadas desde las relaciones del DW. Vacía = coinciden."""
    problemas = []
    for codigo, calculadas in metricas_recalculadas(red).items():
        if not red.nodes[codigo].get("en_grafo", True):
            continue
        for metrica, valor in calculadas.items():
            guardado = red.nodes[codigo].get(metrica)
            if guardado is not None and int(guardado) != valor:
                problemas.append(f"{codigo}.{metrica}: guardado {int(guardado)}, recalculado {valor}")
    return problemas


def cadena_mas_larga(red: nx.DiGraph) -> list[str]:
    """La cadena de prerrequisitos más larga: de la primera materia que hay que
    aprobar a la última que depende de ella."""
    return nx.dag_longest_path(red) if red.number_of_edges() else []


# ---------------------------------------------------------------------------
# Disposición para dibujar
# ---------------------------------------------------------------------------

def _columnas(red: nx.DiGraph) -> tuple[dict[str, int], str]:
    """Columna de cada materia: su ciclo del plan si TODAS las relaciones avanzan
    de ciclo (lo que espera un coordinador); si alguna no, la profundidad en el
    grafo, que siempre es coherente."""
    ciclos = {n: red.nodes[n].get("ciclo_plan") for n in red}
    if all(c is not None and not pd.isna(c) for c in ciclos.values()) and all(
        ciclos[a] < ciclos[b] for a, b in red.edges
    ):
        return {n: int(c) for n, c in ciclos.items()}, "ciclo"
    capas = {}
    for indice, generacion in enumerate(nx.topological_generations(red), start=1):
        for nodo in generacion:
            capas[nodo] = indice
    return capas, "profundidad"


def disponer(red: nx.DiGraph) -> dict:
    """Coordenadas de cada nodo y trayecto de cada relación.

    Columnas por ciclo y, dentro de cada columna, un orden que reduce los cruces
    (método del baricentro: cada materia se coloca cerca del promedio de sus
    vecinas). Es determinista: los empates se resuelven por código de materia.
    """
    if not len(red):
        return {"nodos": {}, "aristas": [], "columnas": [], "ancho": 0, "alto": 0,
                "criterio_columnas": "ciclo"}
    etiqueta_columna, criterio = _columnas(red)
    valores = sorted(set(etiqueta_columna.values()))
    indice_columna = {v: i for i, v in enumerate(valores)}
    columna = {n: indice_columna[v] for n, v in etiqueta_columna.items()}

    por_columna: dict[int, list[str]] = defaultdict(list)
    for nodo in sorted(red):
        por_columna[columna[nodo]].append(nodo)
    posicion = {n: i for c in por_columna.values() for i, n in enumerate(c)}

    def reordenar(c: int, vecinas):
        def baricentro(nodo):
            cercanas = [posicion[v] for v in vecinas(nodo)]
            return (sum(cercanas) / len(cercanas)) if cercanas else posicion[nodo]
        por_columna[c].sort(key=lambda n: (baricentro(n), n))
        for i, n in enumerate(por_columna[c]):
            posicion[n] = i

    n_columnas = len(valores)
    for _ in range(4):
        for c in range(1, n_columnas):
            reordenar(c, red.predecessors)
        for c in range(n_columnas - 2, -1, -1):
            reordenar(c, red.successors)

    filas_max = max(len(v) for v in por_columna.values())
    paso_x = ANCHO_NODO + SEPARACION_COLUMNAS
    paso_y = ALTO_NODO + SEPARACION_FILAS
    nodos = {}
    for c, codigos in por_columna.items():
        desplazamiento = (filas_max - len(codigos)) / 2
        for i, codigo in enumerate(codigos):
            nodos[codigo] = {
                "columna": c,
                "x": MARGEN + c * paso_x,
                "y": MARGEN + ALTO_ROTULOS + (desplazamiento + i) * paso_y,
            }

    aristas = []
    for origen, destino in sorted(red.edges):
        a, b = nodos[origen], nodos[destino]
        x1, y1 = a["x"] + ANCHO_NODO, a["y"] + ALTO_NODO / 2
        x2, y2 = b["x"], b["y"] + ALTO_NODO / 2
        medio = x1 + (x2 - x1) / 2
        aristas.append({
            "origen": origen,
            "destino": destino,
            "d": f"M{x1:.0f},{y1:.0f} C{medio:.0f},{y1:.0f} {medio:.0f},{y2:.0f} {x2:.0f},{y2:.0f}",
        })

    rotulo = "Ciclo {}" if criterio == "ciclo" else "Nivel {}"
    columnas = [{"etiqueta": rotulo.format(v), "x": MARGEN + indice_columna[v] * paso_x}
                for v in valores]
    return {
        "nodos": nodos,
        "aristas": aristas,
        "columnas": columnas,
        "ancho": MARGEN * 2 + n_columnas * ANCHO_NODO + (n_columnas - 1) * SEPARACION_COLUMNAS,
        "alto": MARGEN * 2 + ALTO_ROTULOS + filas_max * ALTO_NODO + (filas_max - 1) * SEPARACION_FILAS,
        "criterio_columnas": criterio,
    }


# ---------------------------------------------------------------------------
# Costo × posición en la malla
# ---------------------------------------------------------------------------

def cruce_costo_posicion(materias: pd.DataFrame, costos: pd.DataFrame) -> pd.DataFrame:
    """Une la posición de cada materia en la malla con su costo de reprobación.

    - bloqueos: reprobados × dependientes_totales. Cada reprobación deja sin poder
      cursar a todas las materias que dependen de la suya, hasta que se apruebe:
      es un conteo de lo ocurrido en el historial (pares reprobación–materia
      bloqueada), no una proyección.
    - tipo: cruza dos preguntas, ¿es cuello de botella en la red? y ¿su costo de
      reprobación está entre la mitad más alta de las materias con costo?
    """
    cruce = materias.merge(costos, on="codigo_materia", how="left")
    for columna in ("reprobados", "cerradas", "estudiantes_reprobados"):
        cruce[columna] = cruce[columna].fillna(0).astype("int64")
    cruce["costo_reprobacion"] = cruce["costo_reprobacion"].fillna(0.0).astype(float)
    cruce["dependientes_totales"] = cruce["dependientes_totales"].fillna(0).astype("int64")
    cruce["tasa_reprobacion"] = cruce["reprobados"] / cruce["cerradas"].where(cruce["cerradas"] > 0)
    cruce["bloqueos"] = cruce["reprobados"] * cruce["dependientes_totales"]

    total_costo = cruce["costo_reprobacion"].sum()
    total_bloqueos = cruce["bloqueos"].sum()
    cruce["pct_costo"] = cruce["costo_reprobacion"] / total_costo if total_costo else 0.0
    cruce["pct_bloqueos"] = cruce["bloqueos"] / total_bloqueos if total_bloqueos else 0.0

    con_costo = cruce.loc[cruce["costo_reprobacion"] > 0, "costo_reprobacion"]
    mediana = con_costo.median() if not con_costo.empty else float("inf")
    cruce["costo_alto"] = cruce["costo_reprobacion"] >= mediana
    cuello = cruce["es_cuello_botella"].fillna(False).astype(bool)
    cruce["tipo"] = "sin_hallazgo"
    cruce.loc[cuello & cruce["costo_alto"], "tipo"] = "propaga"
    cruce.loc[cuello & ~cruce["costo_alto"], "tipo"] = "estructural"
    cruce.loc[~cuello & cruce["costo_alto"], "tipo"] = "contenido"
    cruce["tipo_texto"] = cruce["tipo"].map(TIPOS)
    return cruce.sort_values(["dependientes_totales", "costo_reprobacion", "codigo_materia"],
                             ascending=[False, False, True], ignore_index=True)


# ---------------------------------------------------------------------------
# Lectura en texto
# ---------------------------------------------------------------------------

def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _nombre(red: nx.DiGraph, codigo: str) -> str:
    return f"{red.nodes[codigo].get('nombre_materia', codigo)} ({codigo})"


def leer_estructura(red: nx.DiGraph) -> str:
    if not red.number_of_edges():
        return SIN_RED
    cadena = cadena_mas_larga(red)
    return (f"{len(red)} materias y {_plural(red.number_of_edges(), 'relación', 'relaciones')} de "
            f"prerrequisito; la cadena más larga tiene {len(cadena)} materias ({' → '.join(cadena)}).")


def leer_cuellos(red: nx.DiGraph, materias: pd.DataFrame) -> str:
    if not red.number_of_edges():
        return SIN_RED
    cuellos = materias[materias["es_cuello_botella"].fillna(False).astype(bool)]
    cuellos = cuellos.sort_values(["dependientes_totales", "codigo_materia"], ascending=[False, True])
    if cuellos.empty:
        mayor = materias.sort_values(["dependientes_totales", "codigo_materia"],
                                     ascending=[False, True]).iloc[0]
        return (f"Ninguna materia llega a cuello de botella; la que más bloquea es "
                f"{mayor['codigo_materia']} ({_plural(int(mayor['dependientes_totales']), 'dependiente', 'dependientes')}).")
    primera = cuellos.iloc[0]
    una = len(cuellos) == 1
    return (f"{', '.join(cuellos['codigo_materia'])} {'es' if una else 'son'} cuello de botella; "
            f"{primera['codigo_materia']} bloquea {int(primera['dependientes_totales'])} materias "
            f"({porcentaje(primera['indice_bloqueo'])} del plan).")


def leer_cruce(cruce: pd.DataFrame, red: nx.DiGraph, moneda: str = "USD") -> str:
    if not red.number_of_edges():
        return SIN_RED
    if float(cruce["costo_reprobacion"].sum()) <= 0:
        return "No hubo costo de reprobación con estos filtros."
    cara = cruce.sort_values(["costo_reprobacion", "codigo_materia"], ascending=[False, True]).iloc[0]
    texto = (f"{cara['codigo_materia']} tiene el mayor costo ({dinero(cara['costo_reprobacion'], moneda)}, "
             f"{porcentaje(cara['pct_costo'])} del total)")
    dependientes = int(cara["dependientes_totales"])
    texto += (" y no bloquea otras materias." if not dependientes
              else f" y bloquea {_plural(dependientes, 'materia', 'materias')}.")
    cuellos = cruce[cruce["es_cuello_botella"].fillna(False).astype(bool)]
    if not cuellos.empty:
        texto += (f" Los cuellos de botella generan el {porcentaje(cuellos['pct_bloqueos'].sum())} "
                  "de los bloqueos.")
    return texto


def dispersion(cruce: pd.DataFrame, moneda: str = "USD", ancho: int = 560, alto: int = 340) -> dict:
    """Coordenadas del gráfico costo (X) contra dependientes (Y), una materia por punto.

    Dos guías dividen el plano en los cuadrantes de `tipo`: el costo mediano de las
    materias con costo (vertical) y el umbral de cuello de botella (horizontal).
    Solo llevan rótulo las materias con costo o con hallazgo; el resto es un punto
    con título, para que los rótulos no se pisen en la columna de costo cero.
    """
    izq, der, arriba, abajo = 56, 18, 16, 46
    ancho_util, alto_util = ancho - izq - der, alto - arriba - abajo
    x_max = max(float(cruce["costo_reprobacion"].max()), 1.0)
    x_min = float(cruce["costo_reprobacion"].min())
    # Con costos parecidos entre sí (todos entre $44 000 y $59 000, por ejemplo) un eje
    # que arranca en cero apila todos los puntos a la derecha. En un gráfico de
    # dispersión la posición, no la longitud de una barra, es lo que se lee, así que
    # se recorta el eje; las marcas rotulan siempre el valor real. Con costos muy
    # distintos el eje sigue partiendo de cero.
    x_ini = x_min - 0.15 * (x_max - x_min) if x_min > 0.5 * x_max else 0.0
    x_ini = max(x_ini, 0.0)
    y_max = max(int(cruce["dependientes_totales"].max()), 1)

    def px(costo):
        return izq + ancho_util * (float(costo) - x_ini) / (x_max - x_ini)

    def py(dependientes):
        return arriba + alto_util * (1 - float(dependientes) / y_max)

    puntos = []
    for fila in cruce.itertuples():
        puntos.append({
            "codigo": fila.codigo_materia,
            "titulo": (f"{fila.nombre_materia} ({fila.codigo_materia}): {dinero(fila.costo_reprobacion, moneda)} "
                       f"de costo de reprobación, {int(fila.dependientes_totales)} dependientes. {fila.tipo_texto}."),
            "cx": round(px(fila.costo_reprobacion), 1),
            "cy": round(py(fila.dependientes_totales), 1),
            "tipo": fila.tipo,
            "con_rotulo": fila.tipo != "sin_hallazgo" or fila.costo_reprobacion > 0,
        })
    # Rótulos: se separan hacia abajo los que caerían encima de otro ya colocado.
    colocados: list[tuple[float, float]] = []
    for p in sorted((p for p in puntos if p["con_rotulo"]), key=lambda p: (p["cy"], p["cx"])):
        ty = p["cy"] - 8
        while any(abs(p["cx"] - cx) < 46 and abs(ty - cy) < 11 for cx, cy in colocados):
            ty += 11
        colocados.append((p["cx"], ty))
        p["ty"] = round(ty, 1)

    con_costo = cruce.loc[cruce["costo_reprobacion"] > 0, "costo_reprobacion"]
    n_otras = max(len(cruce) - 1, 1)
    return {
        "ancho": ancho, "alto": alto,
        "area": {"x1": izq, "x2": ancho - der, "y1": arriba, "y2": alto - abajo},
        "puntos": puntos,
        "marcas_x": [{"x": round(px(x_ini + (x_max - x_ini) * k / 4), 1),
                      "texto": dinero(x_ini + (x_max - x_ini) * k / 4, moneda)} for k in range(5)],
        "eje_x_recortado": x_ini > 0,
        "marcas_y": [{"y": round(py(v), 1), "texto": str(v)} for v in range(0, y_max + 1)
                     if y_max <= 10 or v % 2 == 0],
        "x_mediana": round(px(con_costo.median()), 1) if not con_costo.empty else None,
        "y_cuello": round(py(UMBRAL_CUELLO_BOTELLA * n_otras), 1) if UMBRAL_CUELLO_BOTELLA * n_otras <= y_max else None,
        "umbral_dependientes": UMBRAL_CUELLO_BOTELLA * n_otras,
    }


def resumen(red: nx.DiGraph, cruce: pd.DataFrame) -> dict:
    """Cifras de cabecera de la pantalla."""
    cuellos = cruce[cruce["es_cuello_botella"].fillna(False).astype(bool)]
    return {
        "materias": len(red),
        "relaciones": red.number_of_edges(),
        "cuellos": len(cuellos),
        "cadena": len(cadena_mas_larga(red)),
        "pct_costo_cuellos": float(cuellos["pct_costo"].sum()) if not cuellos.empty else 0.0,
    }
