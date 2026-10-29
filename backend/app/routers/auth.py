from dataclasses import asdict
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..config import settings
from ..csrf import renovar_token
from ..database import ROLES_VALIDOS, get_db
from ..dependencies import (CLAVE_CAMBIO_OBLIGATORIO, CLAVE_HUELLA, UsuarioSesion, huella_password,
                            iniciar_actividad, usuario_opcional)
from ..limite_login import limite_login
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
    if usuario_opcional(request):
        return RedirectResponse(destino, status_code=303)
    # modo_demo controla si el login expone accesos rápidos con credenciales
    # reales precargadas — ver la nota en config.py. Apagado por defecto.
    # Sin caché: con «atrás» el navegador mostraba un formulario viejo, con un token
    # CSRF que la sesión nueva ya no reconoce (403 «el formulario caducó»).
    return templates.TemplateResponse(
        request, "login.html",
        {"error": None, "modo_demo": settings.modo_demo, "siguiente": destino},
        headers={"Cache-Control": "no-store"},
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
    # Con la contraseña temporal sin cambiar, tampoco entra al dashboard.
    if usuario is None or request.session.get(CLAVE_CAMBIO_OBLIGATORIO):
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
    # Detrás de nginx, uvicorn toma la IP real de X-Forwarded-For (--proxy-headers).
    ip = request.client.host if request.client else "desconocida"

    espera = limite_login.segundos_de_bloqueo(ip, username)
    if espera:
        minutos = -(-espera // 60)
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": f"Demasiados intentos fallidos. Espera {minutos} minuto(s) e inténtalo de nuevo.",
             "modo_demo": settings.modo_demo, "siguiente": destino},
            status_code=429,
            headers={"Retry-After": str(espera)},
        )

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
        limite_login.registrar_fallo(ip, username)
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
    limite_login.registrar_exito(ip, username)
    # Sesión nueva: se descarta todo lo anterior (incluido el token CSRF que vio la
    # página de login) para que nada de antes del inicio de sesión siga valiendo.
    request.session.clear()
    # De aquí lo lee get_db para aplicar el SET LOCAL ROLE de cada transacción.
    request.session["usuario"] = asdict(sesion)
    request.session[CLAVE_HUELLA] = huella_password(usuario.password_hash)
    iniciar_actividad(request)
    renovar_token(request)
    # Aún sin SET ROLE: lo registra rol_app con su función propia (script 18).
    db.execute(text("SELECT academico_oltp.registrar_acceso(:u)"), {"u": usuario.usuario_id})
    if usuario.debe_cambiar_password:
        request.session[CLAVE_CAMBIO_OBLIGATORIO] = True
        return RedirectResponse("/cuenta", status_code=303)

    return RedirectResponse(destino, status_code=303)


@router.post("/logout")
def cerrar_sesion(request: Request):
    # POST con token CSRF: con GET, cualquier página podía cerrar la sesión ajena
    # con solo incrustar <img src="/logout">.
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/logout")
def logout_sin_formulario():
    # Enlaces o marcadores antiguos: no cierran la sesión, solo vuelven al inicio.
    return RedirectResponse("/", status_code=303)
