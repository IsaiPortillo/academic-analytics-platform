"""Marco del dashboard: marca, barra superior y enlaces de vuelta al sistema.

Genera HTML puro (se prueba sin Streamlit). La app web y el dashboard comparten
sesión cuando se publican juntos detrás de nginx (deploy/): nginx le pasa al
dashboard QUIÉN es el usuario en dos cabeceras, que aquí solo se muestran. No
autorizan nada: quien deja pasar o no es nginx con la sesión de la app web, y el
dashboard lee con un rol de solo lectura de todos modos.
"""

from __future__ import annotations

from html import escape
from urllib.parse import unquote

MARCA_SVG = (
    '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l8 4-8 4-8-4 8-4z"/>'
    '<path d="M6 9.5V16c0 1.5 2.5 3 6 3s6-1.5 6-3V9.5"/></svg>'
)

# Pantallas de la app web a las que se puede volver (ruta, etiqueta).
ENLACES_APP = [
    ("/", "Inicio"),
    ("/vista-ejecutiva", "Vista ejecutiva"),
    ("/analisis-diagnostico", "Análisis diagnóstico"),
    ("/red-curricular", "Red curricular"),
    ("/dashboard", "Dashboard estratégico"),
    ("/analitica-olap", "Cubo OLAP"),
    ("/matricula", "Matrícula"),
    ("/calificaciones", "Calificaciones"),
    ("/asistencia", "Asistencia"),
    ("/reportes", "Reportes"),
]


def usuario_de_cabeceras(cabeceras) -> dict | None:
    """Nombre y rol que nginx pasó (URL-encoded). None si no vienen: p. ej. al abrir
    Streamlit directo en local, sin nginx."""
    nombre = cabeceras.get("X-Minerva-Usuario") if cabeceras else None
    if not nombre:
        return None
    return {"nombre": unquote(nombre)[:80], "rol": unquote(cabeceras.get("X-Minerva-Rol") or "")[:40]}


def _url(base: str, ruta: str) -> str:
    return base.rstrip("/") + ruta if ruta != "/" else (base.rstrip("/") or "") + "/"


def marca_html() -> str:
    return f'<div class="mn-brand"><span class="mn-mark">{MARCA_SVG}</span>EduMetrics</div>'


def enlaces_html(app_url: str) -> str:
    """Bloque «Volver al sistema» para la barra lateral; vacío si no hay URL de la app."""
    if not app_url:
        return ""
    filas = "".join(f'<a class="mn-enlace" href="{escape(_url(app_url, ruta))}" target="_self">{escape(etiqueta)}</a>'
                    for ruta, etiqueta in ENLACES_APP)
    return f'<div class="mn-seccion">Volver al sistema</div>{filas}'


def barra_superior_html(usuario: dict | None, app_url: str, rotulo: str) -> str:
    """Misma barra que el sistema: rótulo de la fuente de datos, usuario y salida."""
    derecha = ""
    if usuario:
        rol = f'<span class="mn-rol">{escape(usuario["rol"])}</span>' if usuario.get("rol") else ""
        derecha += f'<span class="mn-usuario">{escape(usuario["nombre"])}{rol}</span>'
    if app_url:
        derecha += f'<a class="mn-salir" href="{escape(_url(app_url, "/logout"))}" target="_self">Salir</a>'
    return (f'<div class="mn-topbar"><span class="mn-badge"><span class="mn-punto"></span>{escape(rotulo)}</span>'
            f'<span class="mn-espacio"></span>{derecha}</div>')


def lectura_html(texto: str) -> str:
    """Párrafo de lectura en texto bajo un gráfico o tabla. Escapa el HTML y los $."""
    return f'<div class="mn-lectura">{escape(texto)}</div>'
