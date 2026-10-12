from dataclasses import asdict
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import ROLES_VALIDOS, get_db
from ..dependencies import UsuarioSesion, usuario_opcional
from ..models import Usuario
from ..security import verificar_password
from ..templating import templates

router = APIRouter(tags=["autenticación"])


def destino_seguro(valor: str | None) -> str:
    """A dónde volver tras iniciar sesión. Solo rutas de este mismo sitio: un
    valor como //otro.sitio o https://otro.sitio lo convertiría el login en un
    redirector abierto (phishing con la URL real del sistema)."""
    if (valor and valor.startswith("/") and not valor.startswith("//")
            and "\\" not in valor and "\n" not in valor and "\r" not in valor):
        return valor
    return "/"


@router.get("/login")
def mostrar_login(request: Request, siguiente: str | None = None):
    destino = destino_seguro(siguiente)
    if request.session.get("usuario"):
        return RedirectResponse(destino, status_code=303)
    # modo_demo controla si el login expone accesos rápidos con credenciales
    # reales precargadas — ver la nota en config.py. Apagado por defecto.
    return templates.TemplateResponse(
        request, "login.html",
        {"error": None, "modo_demo": settings.modo_demo, "siguiente": destino},
    )


@router.get("/auth/verificar")
def verificar_acceso_coordinador(request: Request):
    """Lo consulta nginx (auth_request) antes de servir el dashboard de Streamlit.

    El dashboard no tiene inicio de sesión propio: reutiliza esta sesión, la misma
    cookie y los mismos usuarios, y solo deja pasar al coordinador (igual que
    /vista-ejecutiva, que muestra lo mismo). 204 = pasa; 401 = sin sesión;
    403 = sesión de un rol sin acceso. Nunca devuelve datos.
    """
    usuario = usuario_opcional(request)
    cabeceras = {"Cache-Control": "no-store"}
    if usuario is None:
        estado = 401
    elif not usuario.es_coordinador:
        estado = 403
    else:
        estado = 204
        # Quién es, para que el dashboard lo muestre en su barra superior (nginx lo
        # reenvía). Solo informativo: no autoriza nada. Codificado: un nombre con tildes
        # no es un valor de cabecera HTTP válido tal cual.
        cabeceras["X-Minerva-Usuario"] = quote(usuario.nombre_completo)
        cabeceras["X-Minerva-Rol"] = quote(usuario.rol_legible)
    return Response(status_code=estado, headers=cabeceras)


@router.post("/login")
def procesar_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    siguiente: str = Form(""),
    db: Session = Depends(get_db),
):
    destino = destino_seguro(siguiente)
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
            {"error": "Usuario o contraseña incorrectos", "modo_demo": settings.modo_demo,
             "siguiente": destino},
            status_code=401,
        )

    if usuario.rol_db not in ROLES_VALIDOS:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": "El usuario tiene un rol no soportado. Contacta al coordinador.",
                "modo_demo": settings.modo_demo,
                "siguiente": destino,
            },
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

    return RedirectResponse(destino, status_code=303)


@router.get("/logout")
def cerrar_sesion(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
