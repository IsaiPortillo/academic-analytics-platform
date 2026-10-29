"""Protección CSRF: cada POST debe traer el token guardado en la sesión.

SameSite=lax en la cookie ya impide que otro sitio envíe un POST con la sesión,
pero depende del navegador y de que nadie relaje esa bandera. El token es la
defensa propia de la aplicación: otro sitio puede hacer que el navegador envíe
el formulario, pero no puede leer el token que va dentro de la página.

El token es por sesión y se renueva al iniciar sesión. Viaja en el campo oculto
`csrf_token` de cada formulario ({{ csrf_campo() }}) o en la cabecera
X-CSRF-Token. Se aplica a toda la aplicación como dependencia global (main.py).
"""

import secrets

from fastapi import HTTPException, Request, status

CLAVE_SESION = "csrf"
CAMPO = "csrf_token"
CABECERA = "X-CSRF-Token"
METODOS_SEGUROS = frozenset({"GET", "HEAD", "OPTIONS"})
MENSAJE_RECHAZO = (
    "El formulario caducó o no proviene de esta aplicación. "
    "Vuelve a cargar la página e inténtalo de nuevo."
)


def token_csrf(request: Request) -> str:
    token = request.session.get(CLAVE_SESION)
    if not token:
        token = renovar_token(request)
    return token


def renovar_token(request: Request) -> str:
    token = secrets.token_urlsafe(32)
    request.session[CLAVE_SESION] = token
    return token


async def verificar_csrf(request: Request) -> None:
    if request.method in METODOS_SEGUROS:
        return

    enviado = request.headers.get(CABECERA)
    if enviado is None:
        tipo = request.headers.get("content-type", "")
        if tipo.startswith(("application/x-www-form-urlencoded", "multipart/form-data")):
            # Starlette guarda el formulario ya leído: FastAPI lo reutiliza después.
            enviado = (await request.form()).get(CAMPO)

    esperado = request.session.get(CLAVE_SESION)
    if not esperado or not isinstance(enviado, str) or not secrets.compare_digest(enviado, esperado):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=MENSAJE_RECHAZO)
