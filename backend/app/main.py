from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .database import get_db
from .dependencies import UsuarioSesion, usuario_actual, usuario_opcional
from .models import Estudiante, Inscripcion, Seccion
from .routers import asistencia, auth, calificaciones, matricula, reportes
from .templating import DIRECTORIO_APP, templates

app = FastAPI(
    title="Plataforma de Gestión Académica",
    description="Sistema transaccional operacional (Fase 2)",
    docs_url="/api/docs",
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.app_secret_key,
    same_site="lax",
    https_only=False,  # en despliegue real con HTTPS debe ser True
)

app.mount("/static", StaticFiles(directory=DIRECTORIO_APP / "static"), name="static")

app.include_router(auth.router)
app.include_router(matricula.router)
app.include_router(calificaciones.router)
app.include_router(asistencia.router)
app.include_router(reportes.router)


@app.exception_handler(StarletteHTTPException)
async def manejar_excepcion_http(request: Request, exc: StarletteHTTPException):
    # Las dependencias señalan "falta iniciar sesión" con un 303 + Location.
    destino = (exc.headers or {}).get("Location")
    if exc.status_code == 303 and destino:
        return RedirectResponse(destino, status_code=303)

    if exc.status_code == 403:
        return templates.TemplateResponse(
            request,
            "error.html",
            # Se pasa el usuario para conservar la barra de navegación.
            {"codigo": 403, "mensaje": exc.detail, "usuario": usuario_opcional(request)},
            status_code=403,
        )

    return await http_exception_handler(request, exc)


@app.get("/")
def inicio(
    request: Request,
    usuario: UsuarioSesion = Depends(usuario_actual),
    db: Session = Depends(get_db),
):
    resumen = {
        "estudiantes": db.scalar(select(func.count()).select_from(Estudiante)),
        "secciones": db.scalar(select(func.count()).select_from(Seccion)),
        "inscripciones": db.scalar(select(func.count()).select_from(Inscripcion)),
    }
    return templates.TemplateResponse(
        request, "inicio.html", {"usuario": usuario, "resumen": resumen}
    )
