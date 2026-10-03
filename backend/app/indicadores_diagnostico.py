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
    """Una frase por par: dirección, fuerza y si se distingue del azar."""
    a, b, r, n = par["x"], par["y"], par["r"], par["n"]
    if not _valido(r) or n < 3:
        return (f"Sin datos suficientes para relacionar {ETIQUETAS[a]} con {ETIQUETAS[b]} "
                f"({n} observaciones).")
    texto = (f"{ETIQUETAS[a].capitalize()} y {ETIQUETAS[b]}: r = {r:+.2f}, relación "
             f"{fuerza(r)}")
    if frozenset({a, b}) in PARES_POR_CONSTRUCCION:
        return texto + (" por construcción: el costo de reprobación solo existe cuando la nota es "
                        "menor a 6.00, así que esta cifra confirma la regla, no es un hallazgo.")
    if not correlacion_significativa(r, n):
        return texto + f" y no distinguible del azar con {n:,} observaciones."
    if fuerza(r) == "despreciable":
        return texto + (f": aunque con {n:,} observaciones no es cero, es tan pequeña que no "
                        "explica diferencias en la práctica.")
    sentido = "en el mismo sentido" if r > 0 else "en sentido contrario"
    return texto + f" ({n:,} observaciones): en promedio, las dos se mueven {sentido}."


def interpretar_correlaciones(pares: list[dict]) -> str:
    """Lectura de conjunto: qué relación sí aparece y cuál no, sin causalidad."""
    utiles = [p for p in pares
              if _valido(p["r"]) and p["n"] >= 3
              and frozenset({p["x"], p["y"]}) not in PARES_POR_CONSTRUCCION]
    if not utiles:
        return "No hay inscripciones cerradas suficientes para calcular correlaciones con estos filtros."

    con_hallazgo = [p for p in utiles
                    if correlacion_significativa(p["r"], p["n"]) and fuerza(p["r"]) != "despreciable"]
    texto = []
    if con_hallazgo:
        mayor = max(con_hallazgo, key=lambda p: abs(p["r"]))
        texto.append(
            f"La relación más clara es entre {ETIQUETAS[mayor['x']]} y {ETIQUETAS[mayor['y']]} "
            f"(r = {mayor['r']:+.2f}, {fuerza(mayor['r'])})."
        )
    else:
        texto.append("Ninguna de las relaciones entre estas variables pasa de despreciable.")

    asistencia_nota = next((p for p in pares if {p["x"], p["y"]} == {"asistencia", "nota"}), None)
    if asistencia_nota and _valido(asistencia_nota["r"]) and asistencia_nota["n"] >= 3:
        if fuerza(asistencia_nota["r"]) == "despreciable":
            texto.append(
                f"La asistencia prácticamente no acompaña a la nota (r = {asistencia_nota['r']:+.2f}): "
                "en estos datos, faltar más no se asocia con sacar menos."
            )
        else:
            texto.append(
                f"La asistencia sí acompaña a la nota (r = {asistencia_nota['r']:+.2f}, "
                f"{fuerza(asistencia_nota['r'])})."
            )
    elif asistencia_nota:
        texto.append("No hay asistencia registrada en los períodos elegidos, así que no se puede "
                     "relacionar con la nota.")

    texto.append("Una correlación describe que dos variables se mueven juntas; no demuestra que "
                 "una cause la otra.")
    return " ".join(texto)


# ---------------------------------------------------------------------------
# Reprobación según el umbral de ausencias
# ---------------------------------------------------------------------------

def interpretar_ausencias(sobre: dict | None, bajo: dict | None, umbral: int) -> str:
    if not sobre or not bajo or not sobre["cerradas"] or not bajo["cerradas"]:
        return ("No hay asistencia registrada en los períodos elegidos: no se puede comparar la "
                "reprobación según las ausencias.")
    diferencia, significativa = diferencia_proporciones(
        sobre["reprobadas"], sobre["cerradas"], bajo["reprobadas"], bajo["cerradas"]
    )
    tasa_sobre = sobre["reprobadas"] / sobre["cerradas"]
    tasa_bajo = bajo["reprobadas"] / bajo["cerradas"]
    texto = (f"Con {umbral} o más ausencias reprobó el {_pct(tasa_sobre)} "
             f"({sobre['cerradas']:,} inscripciones); con menos, el {_pct(tasa_bajo)} "
             f"({bajo['cerradas']:,}).")
    if not significativa:
        return texto + (f" La diferencia ({_pp(diferencia)}) no se distingue del azar: en estos "
                        "datos las ausencias no explican la reprobación.")
    sentido = "más" if diferencia > 0 else "menos"
    return texto + f" Quienes acumulan faltas reprueban {_pp(diferencia)} {sentido}."


# ---------------------------------------------------------------------------
# Segmentos y cohortes (misma lógica: el grupo más alto contra el más bajo)
# ---------------------------------------------------------------------------

def interpretar_segmentos(filas: list[dict], variable: str) -> str:
    """filas: dicts con segmento, cerradas, reprobadas. variable: 'el turno', ..."""
    filas = [f for f in filas if f["cerradas"]]
    if len(filas) < 2:
        return f"No hay suficientes grupos con inscripciones cerradas para comparar {variable}."
    for f in filas:
        f["tasa"] = f["reprobadas"] / f["cerradas"]
    alto = max(filas, key=lambda f: f["tasa"])
    bajo = min(filas, key=lambda f: f["tasa"])
    diferencia, significativa = diferencia_proporciones(
        alto["reprobadas"], alto["cerradas"], bajo["reprobadas"], bajo["cerradas"]
    )
    texto = (f"La reprobación más alta está en {alto['segmento']} ({_pct(alto['tasa'])}) y la más "
             f"baja en {bajo['segmento']} ({_pct(bajo['tasa'])}): {_pp(diferencia)} de diferencia.")
    if not significativa:
        return texto + (f" Esa diferencia no se distingue del azar, así que {variable} no explica "
                        "por qué se reprueba en estos datos.")
    if diferencia < 0.02:
        return texto + (f" Es estadísticamente real pero pequeña: {variable} pesa poco en la "
                        "reprobación.")
    return texto + (f" Es una diferencia real y apreciable: {variable} sí se asocia con la "
                    "reprobación.")


def interpretar_cohortes(filas: list[dict]) -> str:
    filas = [dict(f, segmento=f"la cohorte {f['cohorte']}") for f in filas]
    texto = interpretar_segmentos(filas, "el año de ingreso")
    con_patron = sorted((f for f in filas if f.get("estudiantes_patron")),
                        key=lambda f: f["cohorte"])
    if con_patron:
        mayor = max(con_patron, key=lambda f: f["estudiantes_patron"] / f["estudiantes"])
        texto += (f" La cohorte {mayor['cohorte']} concentra la mayor proporción de estudiantes con "
                  f"el patrón de riesgo ({_pct(mayor['estudiantes_patron'] / mayor['estudiantes'])} "
                  "de sus estudiantes).")
    return texto


# ---------------------------------------------------------------------------
# Patrón de riesgo
# ---------------------------------------------------------------------------

def interpretar_patron(resumen: dict, umbral_faltas: int, umbral_nota) -> str:
    texto = (f"{resumen['estudiantes']:,} estudiantes ya presentan el patrón (nota final menor a "
             f"{umbral_nota} y {umbral_faltas} o más ausencias en una misma materia), en "
             f"{resumen['inscripciones']:,} inscripciones.")
    if not resumen["periodos_con_asistencia"]:
        return texto + (" Ninguno de los períodos elegidos tiene asistencia registrada, así que el "
                        "patrón no se puede observar en ellos.")
    if resumen["reprobadas_con_asistencia"]:
        proporcion = resumen["inscripciones"] / resumen["reprobadas_con_asistencia"]
        texto += (f" Equivalen al {_pct(proporcion)} de las reprobaciones que tienen asistencia "
                  "registrada: el resto de los reprobados no acumuló faltas.")
    if resumen["periodos_con_asistencia"] < resumen["periodos"]:
        texto += (f" Solo {resumen['periodos_con_asistencia']} de los {resumen['periodos']} "
                  "períodos elegidos tienen asistencia registrada; en los demás el patrón no se "
                  "puede observar.")
    return texto + " Es un patrón observado en el historial, no un pronóstico."
