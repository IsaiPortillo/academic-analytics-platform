import hashlib
from pathlib import Path

from fastapi.templating import Jinja2Templates
from jinja2 import pass_context
from markupsafe import Markup

DIRECTORIO_APP = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=DIRECTORIO_APP / "templates")

_huellas: dict[tuple[str, int], str] = {}


def static_v(ruta: str) -> str:
    """URL de un archivo estático con una huella de su contenido (?v=…).

    Detrás de Cloudflare o de cualquier caché, `/static/app.css` con la misma URL
    sigue sirviendo la versión vieja horas después de desplegar (max-age) y la
    pantalla queda con HTML nuevo y CSS viejo. Con la huella en la URL, un archivo
    que cambia es una URL nueva y no hace falta purgar nada. Relativa a propósito:
    `url_for` arma una URL absoluta con el esquema que ve el servidor, que detrás de
    un proxy puede ser http dentro de una página https.
    """
    limpia = ruta.lstrip("/")
    archivo = DIRECTORIO_APP / "static" / limpia
    try:
        clave = (limpia, archivo.stat().st_mtime_ns)
    except OSError:
        return f"/static/{limpia}"
    if clave not in _huellas:
        _huellas[clave] = hashlib.sha256(archivo.read_bytes()).hexdigest()[:10]
    return f"/static/{limpia}?v={_huellas[clave]}"


templates.env.globals["static_v"] = static_v


def escudo_ues() -> str | None:
    """URL del escudo de la UES para la marca (macro marca en _macros.html), o None.

    Es una imagen monocroma con transparencia: se pinta como máscara con el color
    del tema (claro en modo oscuro, oscuro en modo claro). Para cambiarlo por la
    versión oficial basta con reemplazar static/escudo-ues.svg o .png.
    """
    for nombre in ("escudo-ues.svg", "escudo-ues.png"):
        if (DIRECTORIO_APP / "static" / nombre).is_file():
            return static_v(nombre)
    return None


templates.env.globals["escudo_ues"] = escudo_ues


def url_dashboard_streamlit() -> str | None:
    """Enlace del menú al dashboard de Streamlit; None si no está publicado.
    Import diferido para no exigir el .env completo al importar este módulo."""
    from .config import settings
    return settings.dashboard_streamlit_url or None


templates.env.globals["url_dashboard_streamlit"] = url_dashboard_streamlit


@pass_context
def csrf_campo(contexto) -> Markup:
    """Campo oculto con el token CSRF; va dentro de cada <form method="post">."""
    from .csrf import CAMPO, token_csrf
    return Markup(f'<input type="hidden" name="{CAMPO}" value="{token_csrf(contexto["request"])}">')


templates.env.globals["csrf_campo"] = csrf_campo
