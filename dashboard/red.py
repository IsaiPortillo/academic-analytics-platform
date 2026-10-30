"""La malla curricular como SVG para el dashboard de Streamlit.

Mismo dibujo que /red-curricular (la app web): las coordenadas las calcula
backend/app/red_curricular.py con NetworkX y aquí solo se pintan, con los colores
de la paleta de EduMetrics. Cada materia puede estar en uno de cuatro estados al
elegir una: elegida, se bloquea si se reprueba (dependiente), hay que aprobarla
antes (prerrequisito) o sin relación (atenuada). El estado nunca va solo en el
color: cada nodo dice cuántas materias bloquea y el panel de detalle lo repite en
palabras.

Función pura, sin Streamlit: se prueba en dashboard/tests/test_red.py.
"""

from __future__ import annotations

from html import escape

from .tema import mezclar

ANCHO_NODO, ALTO_NODO = 136, 68


def _recortar(texto: str, n: int = 21) -> str:
    return texto if len(texto) <= n else texto[:n] + "…"


def estados(codigo: str, dependientes: set[str], requisitos: set[str], seleccion: str | None) -> str:
    """'seleccion' | 'dependiente' | 'prerrequisito' | 'atenuado' | 'normal'."""
    if seleccion is None:
        return "normal"
    if codigo == seleccion:
        return "seleccion"
    if codigo in dependientes:
        return "dependiente"
    if codigo in requisitos:
        return "prerrequisito"
    return "atenuado"


def svg_red(disposicion: dict, info: dict[str, dict], seleccion: str | None,
            dependientes: set[str], requisitos: set[str], p: dict[str, str]) -> str:
    """SVG completo de la red. `info[codigo]` trae nombre, cuello, calor, totales y costo."""
    linea = mezclar(p["muted"], p["surface"], 0.5)
    partes = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {disposicion["ancho"]} {disposicion["alto"]}" '
        f'width="{disposicion["ancho"]}" height="{disposicion["alto"]}" role="group" '
        f'aria-label="Malla curricular" font-family="Plus Jakarta Sans, Inter, system-ui, sans-serif">'
    ]
    for c in disposicion["columnas"]:
        partes.append(f'<text x="{c["x"]}" y="22" font-size="12" font-weight="700" letter-spacing="0.6" '
                      f'fill="{p["muted"]}">{escape(c["etiqueta"].upper())}</text>')

    for a in disposicion["aristas"]:
        baja = (a["origen"] == seleccion or a["origen"] in dependientes) and a["destino"] in dependientes
        sube = (a["destino"] == seleccion or a["destino"] in requisitos) and a["origen"] in requisitos
        if seleccion is None:
            color, ancho, opacidad = linea, 1.5, 1
        elif baja:
            color, ancho, opacidad = p["danger_text"], 2.5, 1
        elif sube:
            color, ancho, opacidad = p["neutral_text"], 2.5, 1
        else:
            color, ancho, opacidad = linea, 1.5, 0.25
        partes.append(f'<path d="{a["d"]}" fill="none" stroke="{color}" stroke-width="{ancho}" opacity="{opacidad}"/>')

    for codigo, pos in disposicion["nodos"].items():
        n = info[codigo]
        estado = estados(codigo, dependientes, requisitos, seleccion)
        relleno = mezclar(p["brand"], p["surface"], 0.24 * n["calor"])
        trazo, grosor, opacidad = p["border"], 1.5, 1
        if n["cuello"]:
            trazo, grosor = p["danger_text"], 2.5
        if estado == "dependiente":
            relleno, trazo, grosor = p["danger_fill"], p["danger_text"], 2
        elif estado == "prerrequisito":
            relleno, trazo, grosor = p["neutral_fill"], p["neutral_text"], 2
        elif estado == "seleccion":
            trazo, grosor = p["brand"], 3.5
        elif estado == "atenuado":
            opacidad = 0.38
        partes.append(
            f'<g transform="translate({pos["x"]},{pos["y"]})" opacity="{opacidad}">'
            f'<title>{escape(n["nombre"])} — bloquea {n["totales"]} materias. Costo de reprobación {escape(n["costo"])}.</title>'
            f'<rect width="{ANCHO_NODO}" height="{ALTO_NODO}" rx="12" fill="{relleno}" stroke="{trazo}" stroke-width="{grosor}"/>'
            f'<text x="12" y="22" font-size="13" font-weight="800" fill="{p["text"]}">{escape(codigo)}</text>'
            f'<text x="12" y="39" font-size="10.5" fill="{p["muted"]}">{escape(_recortar(n["nombre"]))}</text>'
            f'<text x="12" y="56" font-size="10" font-weight="600" fill="{p["text"]}">Bloquea {n["totales"]} · {escape(n["costo"])}</text>'
            f'</g>'
        )
    partes.append("</svg>")
    return "".join(partes)


def texto_detalle(n: dict, dependientes: list[str], requisitos: list[str], requisitos_directos: list[str]) -> list[str]:
    """Las tres frases del panel de detalle (las mismas que arma app.js en la web)."""
    lista = lambda xs: ", ".join(xs) if xs else "ninguna"  # noqa: E731
    if n["totales"] == 0:
        bloquea = "No es prerrequisito de ninguna materia: reprobarla no deja bloqueada a otra."
    else:
        bloquea = (f"Reprobarla deja sin poder cursar a {n['totales']} materia{'s' if n['totales'] != 1 else ''} "
                   f"({n['directos']} directa{'s' if n['directos'] != 1 else ''} y {n['indirectos']} en cascada, "
                   f"{n['pct_plan']} del plan): {lista(dependientes)}.")
    if not requisitos:
        exige = "No exige ninguna materia previa."
    else:
        extra = f" ({len(requisitos)} en toda la cadena)" if len(requisitos) > len(requisitos_directos) else ""
        exige = f"Exige aprobar antes: {lista(requisitos_directos)}{extra}."
    costo = (f"Costo de reprobación {n['costo']} ({n['pct_costo']} del total) · {n['reprobados']} reprobados"
             f"{' (tasa ' + n['tasa'] + ')' if n['tasa'] != '—' else ''} · {n['bloqueos']:,} bloqueos generados. "
             f"{n['tipo_texto']}.")
    return [bloquea, exige, costo]
