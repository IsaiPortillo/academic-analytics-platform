from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .csrf import verificar_csrf
from .database import get_db
from .dependencies import UsuarioSesion, usuario_actual, usuario_opcional
from .models import Estudiante, Inscripcion, Seccion
from .routers import (
    administracion,
    analisis_diagnostico,
    asistencia,
    auditoria,
    auth,
    calificaciones,
    costos,
    cubo_olap,
    dashboard_estrategico,
    almacen,
    malla,
    matricula,
    metas,
    red_curricular,
    reporte_personalizado,
    reportes,
    usuarios,
    vista_ejecutiva,
)
from .templating import DIRECTORIO_APP, templates

app = FastAPI(
    title="Plataforma de Gestión Académica",
    description="Sistema transaccional operacional (Fase 2)",
    docs_url="/api/docs",
    # Todo POST debe traer el token CSRF de la sesión (app/csrf.py).
    dependencies=[Depends(verificar_csrf)],
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.app_secret_key,
    same_site="lax",
    https_only=settings.cookie_secure,  # COOKIE_SECURE=true detrás de HTTPS (ver .env.example)
    # Antes 14 días (el valor por defecto). La inactividad se controla aparte, en
    # dependencies.usuario_opcional.
    max_age=settings.sesion_duracion_horas * 3600,
)


class SinParametrosVacios:
    """Quita de la URL los parámetros vacíos («periodo_id=&desde=»).

    Un formulario GET envía todos sus campos, también los que quedan en «Todos» o
    sin fecha. Para FastAPI, «desde=» no es una fecha ni «periodo_id=» un entero,
    y respondería 422 con JSON. Un filtro vacío es un filtro ausente.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("query_string"):
            partes = [p for p in scope["query_string"].split(b"&") if p and not p.endswith(b"=")]
            scope = dict(scope, query_string=b"&".join(partes))
        await self.app(scope, receive, send)


app.add_middleware(SinParametrosVacios)

app.mount("/static", StaticFiles(directory=DIRECTORIO_APP / "static"), name="static")

app.include_router(auth.router)
app.include_router(matricula.router)
app.include_router(calificaciones.router)
app.include_router(asistencia.router)
# Antes que reportes: «/reportes/{slug}» también casaría con «/reportes/personalizado».
app.include_router(reporte_personalizado.router)
app.include_router(reportes.router)
app.include_router(costos.router)
app.include_router(vista_ejecutiva.router)
app.include_router(analisis_diagnostico.router)
app.include_router(red_curricular.router)
app.include_router(dashboard_estrategico.router)
app.include_router(cubo_olap.router)
app.include_router(auditoria.router)
app.include_router(usuarios.router)
# malla antes que administracion: «/admin/{slug}» también casaría con «/admin/malla».
app.include_router(malla.router)
app.include_router(metas.router)
app.include_router(almacen.router)
app.include_router(administracion.router)


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


@app.exception_handler(RequestValidationError)
async def manejar_parametros_invalidos(request: Request, exc: RequestValidationError):
    # Un filtro mal escrito en la URL (desde=abc, periodo_id=x): página en español,
    # no el JSON de FastAPI. La API (/api) conserva su respuesta 422.
    if request.url.path.startswith("/api"):
        return await request_validation_exception_handler(request, exc)
    campos = sorted({str(e["loc"][-1]) for e in exc.errors() if e.get("loc")})
    return templates.TemplateResponse(
        request,
        "error.html",
        {"codigo": 400,
         "mensaje": "Algún filtro tiene un valor no válido" + (f" ({', '.join(campos)})" if campos else "")
                    + ". Vuelve a la pantalla anterior y revísalo.",
         "usuario": usuario_opcional(request)},
        status_code=400,
    )


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
