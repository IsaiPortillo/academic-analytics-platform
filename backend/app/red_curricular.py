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

SIN_RED = ("El Data Warehouse todavía no tiene la malla curricular. Se carga desde Neo4j con "
           "python -m etl.carga (con el grafo ya cargado: python database/nosql/03_cargar_grafo_neo4j.py).")

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
    """Qué forma tiene la malla: entradas, terminales y cadena más larga."""
    if not red.number_of_edges():
        return SIN_RED
    entradas = sorted(n for n in red if red.in_degree(n) == 0 and red.out_degree(n) > 0)
    terminales = sorted(n for n in red if red.out_degree(n) == 0 and red.in_degree(n) > 0)
    sueltas = sorted(n for n in red if red.degree(n) == 0)
    cadena = cadena_mas_larga(red)
    texto = (
        f"La malla tiene {len(red)} materias unidas por {_plural(red.number_of_edges(), 'relación', 'relaciones')} "
        f"de prerrequisito. {_plural(len(entradas), 'materia no exige', 'materias no exigen')} ninguna previa "
        f"({', '.join(entradas)}) y de ellas parte toda la cascada; {_plural(len(terminales), 'materia no es', 'materias no son')} "
        f"prerrequisito de ninguna otra ({', '.join(terminales)}): reprobarlas retrasa a quien las cursa, "
        f"pero no bloquea nada más. "
    )
    if sueltas:
        texto += (f"{', '.join(sueltas)} no {'tiene' if len(sueltas) == 1 else 'tienen'} relación con "
                  f"ninguna otra materia. ")
    texto += (
        f"La cadena más larga tiene {len(cadena)} materias ({' → '.join(cadena)}): reprobar "
        f"{cadena[0]} deja detenidas, en cascada, a las {len(cadena) - 1} siguientes de la cadena."
    )
    return texto


def leer_cuellos(red: nx.DiGraph, materias: pd.DataFrame) -> str:
    """Quiénes son los cuellos de botella y cuánto del plan bloquean."""
    if not red.number_of_edges():
        return SIN_RED
    cuellos = materias[materias["es_cuello_botella"].fillna(False).astype(bool)]
    cuellos = cuellos.sort_values(["dependientes_totales", "codigo_materia"], ascending=[False, True])
    if cuellos.empty:
        mayor = materias.sort_values(["dependientes_totales", "codigo_materia"],
                                     ascending=[False, True]).iloc[0]
        return (f"Ninguna materia bloquea una parte lo bastante grande del plan para ser cuello de "
                f"botella; la que más bloquea es {mayor['nombre_materia']} ({mayor['codigo_materia']}), "
                f"con {_plural(int(mayor['dependientes_totales']), 'dependiente', 'dependientes')}.")
    primera = cuellos.iloc[0]
    texto = (
        f"{_plural(len(cuellos), 'materia es', 'materias son')} cuello de botella: "
        f"{'bloquea' if len(cuellos) == 1 else 'bloquean'}, directa o indirectamente, al menos el "
        f"{porcentaje(UMBRAL_CUELLO_BOTELLA, 0)} del resto del plan. "
        f"{primera['nombre_materia']} ({primera['codigo_materia']}) es la mayor: {int(primera['dependientes_directos'])} "
        f"dependientes directos y {int(primera['dependientes_indirectos'])} indirectos, "
        f"{int(primera['dependientes_totales'])} en total ({porcentaje(primera['indice_bloqueo'])} del plan)."
    )
    if len(cuellos) > 1:
        resto = ", ".join(f"{c.codigo_materia} ({int(c.dependientes_totales)} dependientes)"
                          for c in cuellos.iloc[1:].itertuples())
        texto += f" Le {'siguen' if len(cuellos) > 2 else 'sigue'} {resto}."
    return texto


def leer_cruce(cruce: pd.DataFrame, red: nx.DiGraph, moneda: str = "USD") -> str:
    """El cruce central: costo de cada materia frente a su posición en la malla."""
    if not red.number_of_edges():
        return SIN_RED
    total = float(cruce["costo_reprobacion"].sum())
    if total <= 0:
        return ("No hubo costo de reprobación con los filtros elegidos, así que solo se puede leer la "
                "estructura de la malla, no cuánto cuesta lo que se reprueba en ella.")
    otras = max(len(cruce) - 1, 1)
    cara = cruce.sort_values(["costo_reprobacion", "codigo_materia"], ascending=[False, True]).iloc[0]
    texto = (
        f"{cara['nombre_materia']} ({cara['codigo_materia']}) es la materia con más costo de reprobación: "
        f"{dinero(cara['costo_reprobacion'], moneda)}, el {porcentaje(cara['pct_costo'])} del total. "
    )
    if cara["dependientes_totales"] == 0:
        texto += ("No es prerrequisito de ninguna materia, así que ese costo se queda en ella: "
                  "no se propaga al resto del plan. ")
    else:
        texto += (
            f"Además bloquea a {_plural(int(cara['dependientes_totales']), 'materia', 'materias')} "
            f"({porcentaje(cara['dependientes_totales'] / otras, 0)} del resto del plan), así que cada "
            f"reprobación suya detiene a esos estudiantes en toda la cascada: su costo real es mayor que "
            f"la cifra directa. "
        )
    cuellos = cruce[cruce["es_cuello_botella"].fillna(False).astype(bool)]
    if not cuellos.empty:
        texto += (
            f"Los cuellos de botella ({', '.join(cuellos['codigo_materia'])}) concentran el "
            f"{porcentaje(cuellos['pct_costo'].sum())} del costo de reprobación y generan el "
            f"{porcentaje(cuellos['pct_bloqueos'].sum())} de los bloqueos (reprobaciones × materias "
            f"dependientes). "
        )
    if cruce["bloqueos"].sum() > 0:
        mayor = cruce.sort_values(["bloqueos", "codigo_materia"], ascending=[False, True]).iloc[0]
        if mayor["codigo_materia"] != cara["codigo_materia"]:
            texto += (
                f"La que más bloqueos genera es {mayor['nombre_materia']} ({mayor['codigo_materia']}), "
                f"con {int(mayor['bloqueos']):,} pares reprobación–materia bloqueada y "
                f"{dinero(mayor['costo_reprobacion'], moneda)} de costo directo: lo que cuesta no "
                f"basta para medir lo que detiene."
            )
        else:
            texto += (
                f"También es la que más bloqueos genera ({int(mayor['bloqueos']):,} pares "
                f"reprobación–materia bloqueada): en esta materia coinciden el costo directo y el "
                f"efecto sobre la malla."
            )
    estructurales = cruce[cruce["tipo"] == "estructural"]
    if not estructurales.empty:
        una = len(estructurales) == 1
        texto += (
            f" {', '.join(estructurales['codigo_materia'])} "
            f"{'tiene' if una else 'tienen'} poco o ningún costo de reprobación pero "
            f"{'bloquea' if una else 'bloquean'} mucho de la malla: un costo bajo por sí solo no "
            f"{'la hace menos importante' if una else 'las hace menos importantes'}."
        )
    return texto.strip()


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
