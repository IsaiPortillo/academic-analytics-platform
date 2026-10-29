"""Mensajes de éxito y error tras un POST, guardados en la sesión.

Antes viajaban en la URL (?ok=… / &error=…): cualquiera podía armar un enlace al
sistema real con un mensaje inventado («Tu cuenta fue suspendida, escribe a…»).
Ahora solo el servidor escribe el mensaje, y se muestra una sola vez: la página
que lo lee lo retira de la sesión.
"""

from typing import Optional

from fastapi import Request
from fastapi.responses import RedirectResponse

CLAVE_SESION = "aviso"


def redirigir(request: Request, url: str, *, ok: Optional[str] = None,
              error: Optional[str] = None) -> RedirectResponse:
    aviso = {clave: valor for clave, valor in (("ok", ok), ("error", error)) if valor}
    if aviso:
        request.session[CLAVE_SESION] = aviso
    return RedirectResponse(url, status_code=303)


def tomar_aviso(request: Request) -> tuple[Optional[str], Optional[str]]:
    aviso = request.session.pop(CLAVE_SESION, None) or {}
    return aviso.get("ok"), aviso.get("error")
