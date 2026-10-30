"""Identidad visual de EduMetrics para el dashboard de Streamlit.

Los valores son los de backend/app/static/src/input.css (DESIGN.md): la misma
marca carmesí, las mismas superficies frías, la misma tipografía y el mismo modo
oscuro. Así el dashboard no parece otra aplicación: parece una pantalla más del
sistema. Si cambia un token allá, cámbialo aquí.

Este módulo es puro (sin Streamlit salvo `nombre_tema`), por eso se prueba sin
levantar la app (dashboard/tests/test_tema.py).
"""

from __future__ import annotations

FUENTES = ("https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800"
           "&family=JetBrains+Mono:wght@400;500&display=swap")

PALETAS: dict[str, dict[str, str]] = {
    "claro": {
        "brand": "#8b0000", "brand_hover": "#6b0000",
        "bg": "#f7f9fb", "surface": "#ffffff", "sunken": "#eef2f6",
        "border": "#e2e8f0", "input_border": "#cbd5e1",
        "text": "#0f172a", "muted": "#64748b",
        "warning_text": "#b45309", "success_text": "#047857", "danger_text": "#dc2626",
        "neutral_text": "#475569",
        "sombra": "0 1px 2px 0 rgb(15 23 42 / 0.04), 0 1px 3px 0 rgb(15 23 42 / 0.08)",
    },
    "oscuro": {
        "brand": "#c73838", "brand_hover": "#d85c5c",
        "bg": "#0b1220", "surface": "#141b2d", "sunken": "#0f1626",
        "border": "#253046", "input_border": "#324158",
        "text": "#e7ebf3", "muted": "#8b96ab",
        "warning_text": "#f0a94e", "success_text": "#4ade9a", "danger_text": "#f37272",
        "neutral_text": "#b7c2d4",
        "sombra": "0 1px 2px 0 rgb(0 0 0 / 0.3), 0 1px 3px 0 rgb(0 0 0 / 0.35)",
    },
}


def mezclar(color: str, base: str, proporcion: float) -> str:
    """Hex resultante de `proporcion` de `color` sobre `base` (0 = base, 1 = color).
    Los tintes de la app son rgba sobre la superficie; el SVG y los gráficos
    necesitan el color ya resuelto."""
    a = [int(color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    b = [int(base.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{round(x * proporcion + y * (1 - proporcion)):02x}" for x, y in zip(a, b))


def paleta(nombre: str) -> dict[str, str]:
    """Paleta completa con los tintes resueltos (relleno de estados sobre la superficie)."""
    p = dict(PALETAS.get(nombre, PALETAS["claro"]))
    s = p["surface"]
    p["danger_fill"] = mezclar(p["danger_text"], s, 0.16)
    p["warning_fill"] = mezclar(p["warning_text"], s, 0.16)
    p["success_fill"] = mezclar(p["success_text"], s, 0.16)
    p["neutral_fill"] = mezclar(p["neutral_text"], s, 0.14)
    return p


def nombre_tema() -> str:
    """'oscuro' si el usuario ve Streamlit en modo oscuro, si no 'claro'."""
    import streamlit as st
    try:
        return "oscuro" if st.context.theme.type == "dark" else "claro"
    except Exception:  # noqa: BLE001 — versiones sin st.context.theme
        return "claro"


def css(p: dict[str, str]) -> str:
    """Hoja de estilos que viste los componentes de Streamlit con la identidad de la app."""
    return f"""
@import url('{FUENTES}');

:root {{
  --mn-brand: {p['brand']}; --mn-brand-hover: {p['brand_hover']};
  --mn-bg: {p['bg']}; --mn-surface: {p['surface']}; --mn-sunken: {p['sunken']};
  --mn-border: {p['border']}; --mn-input: {p['input_border']};
  --mn-text: {p['text']}; --mn-muted: {p['muted']};
  --mn-sombra: {p['sombra']};
  --mn-fuente: "Plus Jakarta Sans", "Inter", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --mn-mono: "JetBrains Mono", ui-monospace, "SF Mono", Consolas, monospace;
}}

/* Base: fondo, tipografía y márgenes del contenido */
.stApp, [data-testid="stAppViewContainer"] {{ background: var(--mn-bg); color: var(--mn-text); }}
.stApp, .stApp p, .stApp li, .stApp label, .stApp button, .stApp input, .stApp textarea,
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp th, .stApp td,
[data-testid="stMarkdownContainer"], [data-testid="stMetric"], [data-testid="stCaptionContainer"] {{
  font-family: var(--mn-fuente);
}}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding: 1.25rem 1.5rem 3rem; max-width: 88rem; }}
@media (max-width: 640px) {{ .block-container {{ padding: 1rem 0.875rem 3rem; }} }}

/* Títulos: un solo rostro, jerarquía por peso (DESIGN.md) */
.stApp h1 {{ font-size: 1.5rem; font-weight: 800; letter-spacing: -0.01em; line-height: 1.25; padding: 0; }}
.stApp h2 {{ font-size: 1.25rem; font-weight: 700; line-height: 1.3; padding: 0.25rem 0 0.25rem; }}
.stApp h3 {{ font-size: 1rem; font-weight: 700; }}
[data-testid="stCaptionContainer"] {{ color: var(--mn-muted); }}
code {{ font-family: var(--mn-mono); font-size: 0.8em; }}

/* Barra lateral: la misma del sistema (marca, secciones, enlaces) */
[data-testid="stSidebar"] {{ background: var(--mn-surface); border-right: 1px solid var(--mn-border); }}
[data-testid="stSidebar"] > div:first-child {{ padding-top: 0.5rem; }}
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {{ display: none; }}
.mn-brand {{ display: flex; align-items: center; gap: 0.5rem; font-weight: 800; font-size: 1.0625rem;
  color: var(--mn-brand); letter-spacing: -0.01em; padding: 0.5rem 0.25rem 0.75rem; }}
.mn-mark {{ width: 1.75rem; height: 1.75rem; border-radius: 8px; background: var(--mn-brand); color: #fff;
  display: inline-flex; align-items: center; justify-content: center; }}
.mn-seccion {{ font-size: 0.6875rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em;
  color: var(--mn-muted); padding: 0.75rem 0.25rem 0.375rem; }}
.mn-enlace {{ display: flex; align-items: center; gap: 0.5rem; padding: 0.4375rem 0.625rem; border-radius: 8px;
  font-size: 0.875rem; font-weight: 500; color: var(--mn-muted) !important; text-decoration: none !important; }}
.mn-enlace:hover {{ background: var(--mn-sunken); color: var(--mn-text) !important; }}

/* La navegación (st.radio) se ve como la lista de enlaces del sistema */
[data-testid="stSidebar"] [data-testid="stRadioGroup"] {{ gap: 0.125rem; }}
[data-testid="stSidebar"] [data-testid="stRadioOption"] {{ width: 100%; padding: 0.5625rem 0.625rem; border-radius: 8px;
  margin: 0; cursor: pointer; transition: background-color .15s, color .15s; }}
[data-testid="stSidebar"] [data-testid="stRadioOption"] > div > div:first-child {{ display: none; }}
[data-testid="stSidebar"] [data-testid="stRadioOption"] p {{ font-size: 0.875rem; font-weight: 500; color: var(--mn-muted); }}
[data-testid="stSidebar"] [data-testid="stRadioOption"]:hover {{ background: var(--mn-sunken); }}
[data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] {{ background: var(--mn-brand); }}
[data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] p {{ color: #fff; }}

/* Barra superior (misma que la del sistema) */
.mn-topbar {{ display: flex; align-items: center; flex-wrap: wrap; gap: 0.5rem 0.75rem; padding: 0 0 1rem; }}
/* En pantallas angostas el botón de la barra lateral de Streamlit queda sobre el contenido. */
@media (max-width: 991px) {{ .mn-topbar {{ padding-left: 2.75rem; }} }}
.mn-badge {{ display: inline-flex; align-items: center; gap: 0.375rem; font-family: var(--mn-mono); font-size: 0.6875rem;
  padding: 0.25rem 0.5rem; border-radius: 8px; background: var(--mn-sunken); border: 1px solid var(--mn-border);
  color: var(--mn-muted); }}
.mn-punto {{ width: 0.375rem; height: 0.375rem; border-radius: 50%; background: {p['success_text']}; }}
.mn-espacio {{ flex: 1; }}
.mn-usuario {{ font-size: 0.8125rem; color: var(--mn-muted); }}
.mn-rol {{ display: inline-flex; font-size: 0.75rem; font-weight: 700; padding: 0.25rem 0.5625rem; border-radius: 8px;
  color: var(--mn-brand); border: 1px solid {p['danger_text']}55; background: {p['danger_fill']}; margin-left: 0.375rem; }}
.mn-salir {{ border: 1px solid var(--mn-border); border-radius: 8px; padding: 0.3125rem 0.75rem; font-size: 0.8125rem;
  font-weight: 500; color: var(--mn-muted) !important; text-decoration: none !important; }}
.mn-salir:hover {{ background: var(--mn-sunken); color: var(--mn-text) !important; }}

/* Tarjetas: los contenedores con borde y las métricas son las tarjetas de la app */
[data-testid="stVerticalBlockBorderWrapper"] {{ background: var(--mn-surface); border-color: var(--mn-border) !important;
  border-radius: 16px; box-shadow: var(--mn-sombra); }}
[data-testid="stMetric"] {{ padding: 0; }}
[data-testid="stMetricLabel"] p {{ font-size: 0.8125rem; font-weight: 500; color: var(--mn-muted); }}
[data-testid="stMetricValue"] {{ font-size: 1.75rem; font-weight: 800; line-height: 1.1; }}
[data-testid="stMetricDelta"] {{ font-size: 0.75rem; font-weight: 600; }}

/* Controles */
div[data-baseweb="select"] > div, [data-testid="stTextInput"] input, [data-testid="stNumberInput"] input {{
  border-radius: 8px; border-color: var(--mn-input); background: var(--mn-surface); }}
.stButton > button, .stDownloadButton > button {{ background: var(--mn-brand); color: #fff; border: 0;
  border-radius: 8px; font-weight: 600; }}
.stButton > button:hover, .stDownloadButton > button:hover {{ background: var(--mn-brand-hover); color: #fff; }}
[data-testid="stAlertContainer"] {{ border-radius: 12px; color: var(--mn-text); }}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentWarning"]) {{ background: {p['warning_fill']}; border: 1px solid {p['warning_text']}66; }}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]) {{ background: {p['danger_fill']}; border: 1px solid {p['danger_text']}66; }}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentSuccess"]) {{ background: {p['success_fill']}; border: 1px solid {p['success_text']}66; }}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentInfo"]) {{ background: {p['neutral_fill']}; border: 1px solid {p['neutral_text']}66; }}
[data-testid="stDataFrame"] {{ border: 1px solid var(--mn-border); border-radius: 12px; overflow: hidden; }}
hr {{ border-color: var(--mn-border); }}

/* Lectura en texto bajo cada gráfico o tabla (el .kpi-interpretacion del sistema) */
.mn-lectura {{ font-size: 0.8125rem; line-height: 1.55; color: var(--mn-muted); margin-top: 0.75rem;
  padding-top: 0.75rem; border-top: 1px solid var(--mn-border); }}

/* El bloque <style> inyectado no debe dejar un hueco al inicio de la página. */
[data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"] style),
[data-testid="stElementContainer"]:has(style) {{ display: none; }}
"""
