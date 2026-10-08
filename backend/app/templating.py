import hashlib
from pathlib import Path

from fastapi.templating import Jinja2Templates

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
