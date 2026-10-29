"""Gráficas en SVG generadas en el servidor (reportes personalizados).

Sin librerías de JavaScript: el SVG sale con la página, se imprime nítido y
respeta el tema claro/oscuro porque los colores son variables CSS (--chart-N,
--color-border, --color-muted). Cada gráfica lleva <title> y una descripción
para lectores de pantalla; la tabla de abajo tiene los mismos datos.

Las barras horizontales no están aquí: usan el componente .bar-list que ya
tiene el sistema de diseño.
"""

from html import escape
from typing import Optional, Sequence

from markupsafe import Markup

from .exportar import formatear

ANCHO, ALTO = 720, 280
MARGEN = {"arriba": 16, "derecha": 16, "abajo": 56, "izquierda": 56}


def _escala(valores: Sequence[Optional[float]], tipo: str) -> tuple[float, float]:
    numeros = [v for v in valores if v is not None]
    maximo = max(numeros) if numeros else 1
    if tipo == "porcentaje":
        return 0.0, min(1.0, maximo * 1.1) or 1.0
    if tipo == "decimal" and maximo <= 10:
        return 0.0, 10.0          # notas: siempre la escala completa de 0 a 10
    return 0.0, (maximo * 1.1) or 1.0


def _marcas_y(minimo: float, maximo: float, tipo: str, n: int = 4) -> list[tuple[float, str]]:
    paso = (maximo - minimo) / n
    return [(minimo + paso * i, formatear(minimo + paso * i, tipo if tipo != "decimal" else "decimal")
             if tipo != "entero" else f"{minimo + paso * i:,.0f}") for i in range(n + 1)]


def _base(titulo: str, descripcion: str, cuerpo: list[str], series: list[str]) -> Markup:
    leyenda = ""
    if len(series) > 1:
        leyenda = '<ul class="chart-leyenda">' + "".join(
            f'<li><span class="chart-muestra serie-{i % 6 + 1}"></span>{escape(n)}</li>'
            for i, n in enumerate(series)) + "</ul>"
    svg = (f'<svg class="chart-svg" viewBox="0 0 {ANCHO} {ALTO}" role="img" aria-labelledby="g-t g-d" '
           f'preserveAspectRatio="xMidYMid meet"><title id="g-t">{escape(titulo)}</title>'
           f'<desc id="g-d">{escape(descripcion)}</desc>{"".join(cuerpo)}</svg>')
    return Markup(f'<figure class="chart-figura">{svg}{leyenda}</figure>')


def _ejes(categorias, minimo, maximo, tipo, rotar: bool) -> tuple[list[str], float, float, float]:
    ancho_util = ANCHO - MARGEN["izquierda"] - MARGEN["derecha"]
    alto_util = ALTO - MARGEN["arriba"] - MARGEN["abajo"]
    partes = []
    for valor, texto in _marcas_y(minimo, maximo, tipo):
        y = MARGEN["arriba"] + alto_util * (1 - (valor - minimo) / ((maximo - minimo) or 1))
        partes.append(f'<line class="chart-grid" x1="{MARGEN["izquierda"]}" x2="{ANCHO - MARGEN["derecha"]}" '
                      f'y1="{y:.1f}" y2="{y:.1f}"/>'
                      f'<text class="chart-eje" x="{MARGEN["izquierda"] - 6}" y="{y + 3:.1f}" text-anchor="end">'
                      f'{escape(texto)}</text>')
    paso = ancho_util / max(len(categorias), 1)
    cada = max(1, round(len(categorias) / 14))        # no más de ~14 etiquetas legibles
    for i, c in enumerate(categorias):
        if i % cada:
            continue
        x = MARGEN["izquierda"] + paso * (i + 0.5)
        y = ALTO - MARGEN["abajo"] + 14
        etiqueta = escape(str(c)[:16])
        if rotar:
            partes.append(f'<text class="chart-eje" x="{x:.1f}" y="{y:.1f}" text-anchor="end" '
                          f'transform="rotate(-35 {x:.1f} {y:.1f})">{etiqueta}</text>')
        else:
            partes.append(f'<text class="chart-eje" x="{x:.1f}" y="{y:.1f}" text-anchor="middle">{etiqueta}</text>')
    return partes, ancho_util, alto_util, paso


def lineas(titulo: str, categorias: list, series: list[tuple[str, list]], tipo: str) -> Markup:
    minimo, maximo = _escala([v for _, s in series for v in s], tipo)
    rotar = len(categorias) > 8
    partes, _, alto_util, paso = _ejes(categorias, minimo, maximo, tipo, rotar)

    def y(v):
        return MARGEN["arriba"] + alto_util * (1 - (v - minimo) / ((maximo - minimo) or 1))

    for k, (nombre, valores) in enumerate(series):
        clase = f"serie-{k % 6 + 1}"
        # Un hueco (sin dato) corta la línea en vez de inventar un cero.
        tramos, actual = [], []
        for i, v in enumerate(valores):
            if v is None:
                if actual:
                    tramos.append(actual)
                actual = []
                continue
            actual.append((MARGEN["izquierda"] + paso * (i + 0.5), y(v), v, categorias[i]))
        if actual:
            tramos.append(actual)
        for tramo in tramos:
            puntos = " ".join(f"{px:.1f},{py:.1f}" for px, py, _, _ in tramo)
            partes.append(f'<polyline class="chart-linea {clase}" points="{puntos}"/>')
            for px, py, v, c in tramo:
                partes.append(f'<circle class="chart-punto {clase}" cx="{px:.1f}" cy="{py:.1f}" r="3">'
                              f'<title>{escape(str(c))} · {escape(nombre)}: {escape(formatear(v, tipo))}</title></circle>')
    descripcion = f"Gráfica de líneas con {len(categorias)} puntos y {len(series)} serie(s)."
    return _base(titulo, descripcion, partes, [n for n, _ in series])


def columnas(titulo: str, categorias: list, series: list[tuple[str, list]], tipo: str) -> Markup:
    minimo, maximo = _escala([v for _, s in series for v in s], tipo)
    rotar = len(categorias) > 8
    partes, _, alto_util, paso = _ejes(categorias, minimo, maximo, tipo, rotar)
    grupo = paso * 0.78
    ancho_barra = grupo / max(len(series), 1)
    base = MARGEN["arriba"] + alto_util
    for k, (nombre, valores) in enumerate(series):
        clase = f"serie-{k % 6 + 1}"
        for i, v in enumerate(valores):
            if v is None:
                continue
            alto = alto_util * (v - minimo) / ((maximo - minimo) or 1)
            x = MARGEN["izquierda"] + paso * i + (paso - grupo) / 2 + ancho_barra * k
            partes.append(f'<rect class="chart-barra {clase}" x="{x:.1f}" y="{base - alto:.1f}" '
                          f'width="{max(ancho_barra - 1.5, 1):.1f}" height="{max(alto, 0):.1f}" rx="2">'
                          f'<title>{escape(str(categorias[i]))} · {escape(nombre)}: {escape(formatear(v, tipo))}</title></rect>')
    descripcion = f"Gráfica de columnas con {len(categorias)} grupos y {len(series)} serie(s)."
    return _base(titulo, descripcion, partes, [n for n, _ in series])
