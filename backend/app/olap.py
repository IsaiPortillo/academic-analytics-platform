"""Cubo OLAP sobre el Data Warehouse — consulta de resultados por dimensiones.

Nivel analítico descriptivo: el coordinador elige hasta tres dimensiones y el
cubo devuelve las medidas de cada combinación MÁS los subtotales y el total,
calculados por PostgreSQL con GROUP BY ROLLUP o GROUP BY CUBE.

  ROLLUP(a, b, c)  jerarquía: detalle, subtotal por (a, b), subtotal por (a) y total.
  CUBE(a, b, c)    todas las combinaciones: cada subconjunto de dimensiones.

Seguridad: el usuario nunca escribe SQL. Elige CLAVES de un catálogo fijo
(DIMENSIONES) y el texto SQL sale de ese catálogo; una clave desconocida se ignora.
Los filtros de período, carrera y departamento siguen yendo como parámetros ligados
(app/dw.py).

Este módulo es puro (sin base de datos): construir_sql y preparar_filas se prueban
en backend/tests/test_olap.py.
"""

from __future__ import annotations

import pandas as pd

from .indicadores import dinero, porcentaje

MAX_DIMENSIONES = 3
LIMITE_FILAS = 1000
# Una tasa sobre pocas inscripciones es ruido: la lectura en texto solo compara
# celdas con al menos este número de inscripciones con nota final.
MINIMO_CERRADAS_LECTURA = 100

# clave -> (etiqueta, expresión SQL sobre el esquema de DESDE_HECHOS_DIAGNOSTICO).
# El orden del diccionario es el orden de los selectores en pantalla.
DIMENSIONES: dict[str, tuple[str, str]] = {
    "periodo": ("Período", "p.codigo_periodo"),
    "departamento": ("Departamento", "c.nombre_departamento"),
    "carrera": ("Carrera", "c.nombre_carrera"),
    "ciclo": ("Ciclo del plan", "m.ciclo_plan"),
    "area": ("Área de conocimiento", "m.area"),
    "materia": ("Materia", "m.codigo_materia"),
    "turno": ("Turno", "f.turno"),
    "cohorte": ("Cohorte de ingreso", "e.anio_ingreso"),
}

MODOS = {
    "rollup": "ROLLUP — jerarquía con subtotales",
    "cube": "CUBE — todas las combinaciones",
}

# Medidas del cubo, en el orden de las columnas.
MEDIDAS = [
    ("cerradas", "Con nota final", "COUNT(*) FILTER (WHERE f.cerrada)"),
    ("reprobados", "Reprobados", "COUNT(*) FILTER (WHERE f.reprobado)"),
    ("tasa_reprobacion", "Tasa de reprobación",
     "ROUND(COUNT(*) FILTER (WHERE f.reprobado)::numeric "
     "/ NULLIF(COUNT(*) FILTER (WHERE f.cerrada), 0), 4)"),
    ("nota_promedio", "Nota promedio", "ROUND(AVG(f.nota_final) FILTER (WHERE f.cerrada), 2)"),
    ("costo_reprobacion", "Costo de reprobación", "COALESCE(SUM(f.costo_reprobacion), 0)"),
]


def validar_dimensiones(solicitadas) -> list[str]:
    """Claves válidas, sin repetir y en el orden pedido; lo demás se descarta."""
    elegidas: list[str] = []
    for clave in solicitadas or ():
        if clave in DIMENSIONES and clave not in elegidas:
            elegidas.append(clave)
    return elegidas[:MAX_DIMENSIONES]


def validar_modo(modo: str | None) -> str:
    return modo if modo in MODOS else "rollup"


def construir_sql(dimensiones: list[str], modo: str, desde_y_donde: str) -> str:
    """SELECT del cubo. `desde_y_donde` es el FROM + WHERE ya armado por app/dw.py
    (con parámetros ligados); las dimensiones salen solo del catálogo."""
    claves = validar_dimensiones(dimensiones)
    if not claves:
        raise ValueError("El cubo necesita al menos una dimensión")
    expresiones = [DIMENSIONES[c][1] for c in claves]
    dims_select = ",\n        ".join(
        f"{expr} AS d{i}, GROUPING({expr}) AS g{i}" for i, expr in enumerate(expresiones, start=1)
    )
    medidas = ",\n        ".join(f"{sql} AS {nombre}" for nombre, _, sql in MEDIDAS)
    agrupar = ", ".join(expresiones)
    orden = ", ".join(f"g{i}, d{i}" for i in range(1, len(claves) + 1))
    return f"""
        SELECT
        {dims_select},
        {medidas}
        {desde_y_donde}
        GROUP BY {'CUBE' if validar_modo(modo) == 'cube' else 'ROLLUP'} ({agrupar})
        ORDER BY {orden}
        LIMIT {LIMITE_FILAS + 1}
    """


def preparar_filas(df: pd.DataFrame, dimensiones: list[str], moneda: str = "USD") -> list[dict]:
    """Filas listas para mostrar. Cada una trae sus celdas de dimensión ya rotuladas
    ('Todos' donde esa dimensión se agrupó), su nivel y el texto de cada medida.

    nivel: 0 detalle · 1..n-1 subtotal · n total general (todas las dimensiones
    agrupadas). Es el número de dimensiones agrupadas en esa fila.
    """
    claves = validar_dimensiones(dimensiones)
    filas = []
    for fila in df.to_dict("records"):
        celdas, agrupadas = [], 0
        for i in range(1, len(claves) + 1):
            if int(fila[f"g{i}"]) == 1:
                celdas.append("Todos")
                agrupadas += 1
            else:
                valor = fila[f"d{i}"]
                celdas.append("Sin dato" if pd.isna(valor) else _texto_dimension(valor))
        tasa = fila["tasa_reprobacion"]
        nota = fila["nota_promedio"]
        filas.append({
            "celdas": celdas,
            "nivel": agrupadas,
            "es_total": agrupadas == len(claves),
            "cerradas": int(fila["cerradas"]),
            "reprobados": int(fila["reprobados"]),
            "tasa": None if pd.isna(tasa) else float(tasa),
            "tasa_texto": porcentaje(None if pd.isna(tasa) else float(tasa)),
            "nota_texto": "—" if pd.isna(nota) else f"{float(nota):.2f}",
            "costo": float(fila["costo_reprobacion"]),
            "costo_texto": dinero(float(fila["costo_reprobacion"]), moneda),
        })
    return filas


def _texto_dimension(valor) -> str:
    # Los enteros llegan como float cuando hay NULL en la columna (p. ej. cohorte).
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor)


def etiquetas(dimensiones: list[str]) -> list[str]:
    return [DIMENSIONES[c][0] for c in validar_dimensiones(dimensiones)]


def leer_cubo(filas: list[dict], dimensiones: list[str], modo: str, moneda: str = "USD") -> str:
    """Qué muestra el cubo, en una o dos frases, sin inventar donde no hay datos."""
    nombres = etiquetas(dimensiones)
    if not filas:
        return "El cubo no devolvió filas con los filtros elegidos."
    detalle = [f for f in filas if f["nivel"] == 0]
    subtotales = [f for f in filas if 0 < f["nivel"] < len(nombres)]
    total = next((f for f in filas if f["es_total"]), None)
    texto = (
        f"{'ROLLUP' if validar_modo(modo) == 'rollup' else 'CUBE'} por {' → '.join(nombres)}: "
        f"{len(detalle):,} combinaciones de detalle y {len(subtotales):,} "
        f"subtotal{'es' if len(subtotales) != 1 else ''}"
    )
    if total:
        texto += (f"; en total, {total['cerradas']:,} inscripciones con nota final, "
                  f"{total['reprobados']:,} reprobadas ({total['tasa_texto']}) y "
                  f"{total['costo_texto']} de costo de reprobación")
    texto += "."
    comparables = [f for f in detalle if f["cerradas"] >= MINIMO_CERRADAS_LECTURA and f["tasa"] is not None]
    if len(comparables) >= 2:
        alta = max(comparables, key=lambda f: f["tasa"])
        baja = min(comparables, key=lambda f: f["tasa"])
        if alta["tasa"] - baja["tasa"] >= 0.02:
            texto += (
                f" Entre las combinaciones con al menos {MINIMO_CERRADAS_LECTURA} inscripciones con nota "
                f"final, la reprobación más alta es {' · '.join(alta['celdas'])} ({alta['tasa_texto']}) y "
                f"la más baja {' · '.join(baja['celdas'])} ({baja['tasa_texto']})."
            )
        else:
            texto += (f" Entre las combinaciones con al menos {MINIMO_CERRADAS_LECTURA} inscripciones con "
                      f"nota final la tasa de reprobación es casi la misma (de {baja['tasa_texto']} a "
                      f"{alta['tasa_texto']}): ninguna dimensión de las elegidas la separa.")
    return texto
