from dataclasses import asdict

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import ROLES_VALIDOS, get_db
from ..dependencies import UsuarioSesion
from ..models import Usuario
from ..security import verificar_password
from ..templating import templates

router = APIRouter(tags=["autenticación"])


@router.get("/login")
def mostrar_login(request: Request):
    if request.session.get("usuario"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
def procesar_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    # En este punto la sesión aún no tiene rol, así que get_db no aplica ningún
    # SET ROLE: la consulta corre con los permisos directos de rol_app, que solo
    # puede leer esta tabla. Es justo lo que necesita el login.
    usuario = db.scalar(
        select(Usuario).where(Usuario.username == username, Usuario.activo.is_(True))
    )

    credenciales_validas = usuario is not None and verificar_password(
        password, usuario.password_hash
    )

    if not credenciales_validas:
        # Mensaje genérico a propósito: no revela si el usuario existe.
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Usuario o contraseña incorrectos"},
            status_code=401,
        )

    if usuario.rol_db not in ROLES_VALIDOS:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "El usuario tiene un rol no soportado. Contacta al coordinador."},
            status_code=403,
        )

    sesion = UsuarioSesion(
        usuario_id=usuario.usuario_id,
        username=usuario.username,
        nombre_completo=usuario.nombre_completo,
        rol_db=usuario.rol_db,
        docente_id=usuario.docente_id,
    )
    # De aquí lo lee get_db para aplicar el SET LOCAL ROLE de cada transacción.
    request.session["usuario"] = asdict(sesion)

    return RedirectResponse("/", status_code=303)


@router.get("/logout")
def cerrar_sesion(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
