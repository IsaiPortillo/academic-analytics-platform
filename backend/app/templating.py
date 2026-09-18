from pathlib import Path

from fastapi.templating import Jinja2Templates

DIRECTORIO_APP = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=DIRECTORIO_APP / "templates")
