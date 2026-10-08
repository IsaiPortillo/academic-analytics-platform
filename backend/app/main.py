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
from .routers import (
    analisis_diagnostico,
    asistencia,
    auth,
    calificaciones,
    matricula,
    reportes,
    vista_ejecutiva,
)
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
    https_only=settings.cookie_secure,  # COOKIE_SECURE=true detrás de HTTPS (ver .env.example)
)

app.mount("/static", StaticFiles(directory=DIRECTORIO_APP / "static"), name="static")

app.include_router(auth.router)
app.include_router(matricula.router)
app.include_router(calificaciones.router)
app.include_router(asistencia.router)
app.include_router(reportes.router)
app.include_router(vista_ejecutiva.router)
app.include_router(analisis_diagnostico.router)


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


@app.get("/dashboard")
def dashboard(
    request: Request,
    usuario: UsuarioSesion = Depends(usuario_actual),
):
    # Vista previa ilustrativa: el motor de grafo curricular en Neo4j (DAG de
    # prerrequisitos, centralidad de intermediación) y la capa OLAP son Fases
    # 3-4 del roadmap (ver PRODUCT.md) — todavía no implementadas. Esta
    # pantalla muestra la visión del sistema con datos de ejemplo, marcados
    # como tales, nunca como un resultado real de una consulta.
    return templates.TemplateResponse(request, "dashboard.html", {"usuario": usuario})


@app.get("/analitica-olap")
def analitica_olap(
    request: Request,
    usuario: UsuarioSesion = Depends(usuario_actual),
):
    # Misma nota que /dashboard: maqueta ilustrativa de la capa OLAP/BI
    # (Fase 4, pendiente), no una consulta real contra fact_rendimiento_academico.
    return templates.TemplateResponse(request, "analitica_olap.html", {"usuario": usuario})


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
