"""Lecturas del análisis diagnóstico — Fase 4.2 (¿por qué ocurrió?).

Cada gráfico de la pantalla va acompañado de su lectura en texto, generada
aquí con las cifras del filtro activo. Las lecturas describen relaciones
OBSERVADAS en datos históricos: no predicen quién va a reprobar o desertar ni
recomiendan acciones (predictivo y prescriptivo están fuera del alcance).

Dos reglas para no afirmar de más:

  1. Fuerza de una correlación según los rangos convencionales de Cohen (1988):
     |r| < 0.10 despreciable, < 0.30 débil, < 0.50 moderada, ≥ 0.50 fuerte.
  2. Una diferencia o correlación solo se presenta como hallazgo si es
     estadísticamente distinguible del azar al 95 % (|t| o |z| ≥ 1.96). Con
     miles de inscripciones casi todo es "significativo", por eso además se
     informa la magnitud; y con pocas, una diferencia grande puede no serlo.

Funciones puras, sin FastAPI ni base de datos, para poder probarlas.
"""

import math

Z_95 = 1.96

ETIQUETAS = {
    "asistencia": "la asistencia acumulada",
    "nota": "la nota final",
    "intento": "el número de intento",
    "costo": "el costo de reprobación",
}

# Pares cuya relación existe por definición, no por el comportamiento de los
# estudiantes: el costo de reprobación solo es distinto de cero cuando la nota
# es menor a 6.00. Se muestran en la matriz pero no se leen como hallazgo.
PARES_POR_CONSTRUCCION = {frozenset({"nota", "costo"})}


def fuerza(r: float) -> str:
    a = abs(r)
    if a < 0.10:
        return "despreciable"
    if a < 0.30:
        return "débil"
    if a < 0.50:
        return "moderada"
    return "fuerte"


def correlacion_significativa(r: float, n: int) -> bool:
    """Prueba t de Pearson: t = r·√((n−2)/(1−r²))."""
    if n is None or n < 3 or r is None or math.isnan(r):
        return False
    if abs(r) >= 1:
        return True
    return abs(r * math.sqrt((n - 2) / (1 - r * r))) >= Z_95


def diferencia_proporciones(rep_a: int, n_a: int, rep_b: int, n_b: int) -> tuple[float, bool]:
    """Diferencia de tasas (a − b) y si es significativa (prueba z de dos proporciones)."""
    if not n_a or not n_b:
        return 0.0, False
    p_a, p_b = rep_a / n_a, rep_b / n_b
    p = (rep_a + rep_b) / (n_a + n_b)
    error = math.sqrt(p * (1 - p) * (1 / n_a + 1 / n_b))
    if error == 0:
        return p_a - p_b, False
    return p_a - p_b, abs((p_a - p_b) / error) >= Z_95


def _pp(diferencia: float) -> str:
    return f"{abs(diferencia) * 100:.1f} puntos porcentuales"


def _pct(valor: float) -> str:
    return f"{valor * 100:.1f} %"


def _valido(r) -> bool:
    return r is not None and not (isinstance(r, float) and math.isnan(r))


# ---------------------------------------------------------------------------
# Matriz de correlaciones
# ---------------------------------------------------------------------------

def leer_correlacion(par: dict) -> str:
    """Una frase por par: fuerza y si se distingue del azar."""
    a, b, r, n = par["x"], par["y"], par["r"], par["n"]
    nombre = f"{ETIQUETAS[a].capitalize()} y {ETIQUETAS[b]}"
    if not _valido(r) or n < 3:
        return f"{nombre}: sin datos suficientes."
    if frozenset({a, b}) in PARES_POR_CONSTRUCCION:
        return f"{nombre}: r = {r:+.2f}, relación por definición."
    if not correlacion_significativa(r, n):
        return f"{nombre}: r = {r:+.2f}, sin relación distinguible del azar."
    if fuerza(r) == "despreciable":
        return f"{nombre}: r = {r:+.2f}, relación despreciable."
    sentido = "en el mismo sentido" if r > 0 else "en sentido contrario"
    return f"{nombre}: r = {r:+.2f}, relación {fuerza(r)} {sentido}."


def interpretar_correlaciones(pares: list[dict]) -> str:
    utiles = [p for p in pares
              if _valido(p["r"]) and p["n"] >= 3
              and frozenset({p["x"], p["y"]}) not in PARES_POR_CONSTRUCCION]
    if not utiles:
        return "Sin datos suficientes para calcular correlaciones."

    con_hallazgo = [p for p in utiles
                    if correlacion_significativa(p["r"], p["n"]) and fuerza(p["r"]) != "despreciable"]
    if con_hallazgo:
        mayor = max(con_hallazgo, key=lambda p: abs(p["r"]))
        texto = (f"La relación más clara es entre {ETIQUETAS[mayor['x']]} y {ETIQUETAS[mayor['y']]} "
                 f"(r = {mayor['r']:+.2f}).")
    else:
        texto = "Ninguna relación pasa de despreciable."

    asistencia_nota = next((p for p in pares if {p["x"], p["y"]} == {"asistencia", "nota"}), None)
    if asistencia_nota and _valido(asistencia_nota["r"]) and asistencia_nota["n"] >= 3:
        if fuerza(asistencia_nota["r"]) == "despreciable":
            texto += f" La asistencia casi no se relaciona con la nota (r = {asistencia_nota['r']:+.2f})."
        else:
            texto += f" La asistencia sí se relaciona con la nota (r = {asistencia_nota['r']:+.2f})."
    elif asistencia_nota:
        texto += " Sin asistencia registrada en estos períodos."
    return texto


# ---------------------------------------------------------------------------
# Reprobación según el umbral de ausencias
# ---------------------------------------------------------------------------

def interpretar_ausencias(sobre: dict | None, bajo: dict | None, umbral: int) -> str:
    if not sobre or not bajo or not sobre["cerradas"] or not bajo["cerradas"]:
        return "Sin asistencia registrada en estos períodos."
    diferencia, significativa = diferencia_proporciones(
        sobre["reprobadas"], sobre["cerradas"], bajo["reprobadas"], bajo["cerradas"]
    )
    texto = (f"Con {umbral} o más ausencias reprobó el {_pct(sobre['reprobadas'] / sobre['cerradas'])}; "
             f"con menos, el {_pct(bajo['reprobadas'] / bajo['cerradas'])}")
    if not significativa:
        return texto + ": la diferencia no es significativa."
    return texto + f": {_pp(diferencia)} {'más' if diferencia > 0 else 'menos'}."


# ---------------------------------------------------------------------------
# Segmentos y cohortes (misma lógica: el grupo más alto contra el más bajo)
# ---------------------------------------------------------------------------

def interpretar_segmentos(filas: list[dict], variable: str) -> str:
    """filas: dicts con segmento, cerradas, reprobadas. variable: 'el turno', ..."""
    filas = [f for f in filas if f["cerradas"]]
    if len(filas) < 2:
        return "No hay grupos suficientes para comparar."
    for f in filas:
        f["tasa"] = f["reprobadas"] / f["cerradas"]
    alto = max(filas, key=lambda f: f["tasa"])
    bajo = min(filas, key=lambda f: f["tasa"])
    diferencia, significativa = diferencia_proporciones(
        alto["reprobadas"], alto["cerradas"], bajo["reprobadas"], bajo["cerradas"]
    )
    texto = (f"Más alta en {alto['segmento']} ({_pct(alto['tasa'])}), más baja en "
             f"{bajo['segmento']} ({_pct(bajo['tasa'])})")
    if not significativa:
        return texto + ": la diferencia no es significativa."
    if diferencia < 0.02:
        return texto + ": diferencia real pero pequeña."
    return texto + f": {variable} sí marca diferencia."


def interpretar_cohortes(filas: list[dict]) -> str:
    filas = [dict(f, segmento=f"la cohorte {f['cohorte']}") for f in filas]
    return interpretar_segmentos(filas, "el año de ingreso")


# ---------------------------------------------------------------------------
# Patrón de riesgo
# ---------------------------------------------------------------------------

def interpretar_patron(resumen: dict, umbral_faltas: int, umbral_nota) -> str:
    texto = (f"{resumen['estudiantes']:,} estudiantes presentan el patrón en "
             f"{resumen['inscripciones']:,} inscripciones.")
    if not resumen["periodos_con_asistencia"]:
        return texto + " No hay asistencia registrada en estos períodos."
    if resumen["periodos_con_asistencia"] < resumen["periodos"]:
        texto += (f" Solo {resumen['periodos_con_asistencia']} de {resumen['periodos']} períodos "
                  "tienen asistencia registrada.")
    return texto
