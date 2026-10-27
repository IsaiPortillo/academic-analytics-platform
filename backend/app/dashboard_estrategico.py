"""Dashboard estratégico — panorama institucional con datos reales del DW.

Reúne en una pantalla lo que un coordinador mira primero: cuántos estudiantes
se evaluaron, qué tan bien aprobaron, cuánto costó lo que no aprobaron, en qué
ciclos del plan se concentra la reprobación y qué materias frenan más la malla.
Todo sale del Data Warehouse; este módulo solo da forma y redacta la lectura.

Nivel analítico descriptivo y diagnóstico. No hay aquí nada predictivo: ni
alertas de deserción ni proyecciones.
"""

from __future__ import annotations

import pandas as pd

from .indicadores import dinero, porcentaje

# Un ciclo con pocas inscripciones con nota final no sostiene una comparación.
MINIMO_CERRADAS_CICLO = 100


def aprobacion_por_ciclo(df: pd.DataFrame, moneda: str = "USD") -> list[dict]:
    """Aprobación de cada ciclo del plan, lista para las barras. La escala es
    0–100 %: una tasa de aprobación se lee contra el total, no contra el mayor."""
    filas = []
    for fila in df.to_dict("records"):
        cerradas = int(fila["cerradas"])
        reprobados = int(fila["reprobados"])
        aprobacion = (cerradas - reprobados) / cerradas if cerradas else None
        filas.append({
            "ciclo": int(fila["ciclo_plan"]),
            "cerradas": cerradas,
            "reprobados": reprobados,
            "aprobacion": aprobacion,
            "aprobacion_texto": porcentaje(aprobacion),
            "pct": aprobacion or 0.0,
            "costo_texto": dinero(float(fila["costo_reprobacion"]), moneda),
        })
    return filas


def leer_aprobacion(filas: list[dict]) -> str:
    validas = [f for f in filas if f["aprobacion"] is not None and f["cerradas"] >= MINIMO_CERRADAS_CICLO]
    if len(validas) < 2:
        return "No hay datos suficientes por ciclo para comparar."
    baja = min(validas, key=lambda f: f["aprobacion"])
    alta = max(validas, key=lambda f: f["aprobacion"])
    if alta["aprobacion"] - baja["aprobacion"] < 0.02:
        return f"Aprobación similar en todos los ciclos ({baja['aprobacion_texto']} a {alta['aprobacion_texto']})."
    return (f"Menor aprobación en el ciclo {baja['ciclo']} ({baja['aprobacion_texto']}); "
            f"mayor en el ciclo {alta['ciclo']} ({alta['aprobacion_texto']}).")


def materias_que_mas_bloquean(cruce: pd.DataFrame, moneda: str = "USD", n: int = 5) -> list[dict]:
    """Las materias que más bloquean la malla, con su costo, del cruce de la red
    curricular (app/red_curricular.py). Ordena por dependientes y desempata por costo."""
    ordenado = cruce.sort_values(["dependientes_totales", "costo_reprobacion", "codigo_materia"],
                                 ascending=[False, False, True]).head(n)
    return [
        {
            "codigo": f.codigo_materia,
            "nombre": f.nombre_materia,
            "dependientes": int(f.dependientes_totales),
            "pct_plan": porcentaje(f.indice_bloqueo),
            "cuello": bool(f.es_cuello_botella),
            "reprobados": int(f.reprobados),
            "costo_texto": dinero(float(f.costo_reprobacion), moneda),
            "bloqueos": int(f.bloqueos),
        }
        for f in ordenado.itertuples()
    ]


def leer_impacto(materias: list[dict], total_bloqueos: int) -> str:
    if not materias or total_bloqueos <= 0:
        return "No hubo bloqueos con estos filtros."
    parte = sum(m["bloqueos"] for m in materias) / total_bloqueos
    cuellos = [m["codigo"] for m in materias if m["cuello"]]
    texto = f"Estas {len(materias)} materias generan el {porcentaje(parte)} de los bloqueos."
    if cuellos:
        texto += f" {', '.join(cuellos)} {'es' if len(cuellos) == 1 else 'son'} cuello de botella."
    return texto


