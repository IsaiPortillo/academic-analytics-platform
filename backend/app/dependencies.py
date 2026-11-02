import hashlib
import time
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text

from .config import settings
from .database import engine


@dataclass
class UsuarioSesion:
    usuario_id: int
    username: str
    nombre_completo: str
    rol_db: str
    docente_id: Optional[int]
    carrera_id: Optional[int] = None

    @property
    def es_admin(self) -> bool:
        """Administrador institucional: sin recorte por carrera."""
        return self.rol_db == "rol_admin"

    @property
    def es_coordinador(self) -> bool:
        """Puede entrar a las pantallas de coordinación.

        Incluye al admin a propósito: es un superconjunto del coordinador, así
        que las pantallas operativas y el menú no necesitan distinguirlos. Lo
        que es exclusivo del admin se pide con `es_admin` o con
        requiere_rol("rol_admin").
        """
        return self.rol_db in ("rol_coordinador", "rol_admin")

    @property
    def rol_legible(self) -> str:
        return {"rol_admin": "Administrador",
                "rol_coordinador": "Coordinador"}.get(self.rol_db, "Docente")


CLAVE_ACTIVIDAD = "ultima_actividad"
CLAVE_HUELLA = "huella"
CLAVE_CAMBIO_OBLIGATORIO = "debe_cambiar_password"
# Rutas permitidas mientras la contraseña temporal no se haya cambiado.
RUTAS_SIN_CAMBIO = ("/cuenta", "/cuenta/contrasena", "/cuenta/perfil", "/logout")


def huella_password(password_hash: str) -> str:
    """Resumen corto del hash vigente. Va en la sesión: si la contraseña cambia
    (la cambia el usuario o la restablece el coordinador), las sesiones abiertas
    con la anterior dejan de valer. No permite recuperar la contraseña."""
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


def cuenta_vigente(datos: dict, huella: Optional[str]) -> bool:
    """¿La cuenta sigue activa, con el mismo rol y la misma contraseña que tenía
    al iniciar sesión?

    Se pregunta en cada petición: desactivar a un usuario, cambiarle el rol o
    restablecer su contraseña corta su sesión en el siguiente clic, sin esperar
    a que caduque la cookie. Corre con los permisos directos de rol_app, que
    solo puede leer usuarios.
    """
    with engine.connect() as conexion:
        fila = conexion.execute(
            text("SELECT rol_db, docente_id, carrera_id, password_hash FROM academico_oltp.usuarios "
                 "WHERE usuario_id = :id AND activo"),
            {"id": datos.get("usuario_id")},
        ).first()
    # La carrera entra en la comprobación: si el admin se la cambia, la sesión
    # abierta deja de valer y el coordinador vuelve a entrar con la nueva. De lo
    # contrario seguiría viendo la anterior hasta que caducara la cookie.
    return (fila is not None and fila.rol_db == datos.get("rol_db")
            and fila.docente_id == datos.get("docente_id")
            and fila.carrera_id == datos.get("carrera_id")
            and huella is not None and huella_password(fila.password_hash) == huella)


def iniciar_actividad(request: Request) -> None:
    request.session[CLAVE_ACTIVIDAD] = int(time.time())


def _usuario_de_sesion(request: Request) -> Optional[UsuarioSesion]:
    datos = request.session.get("usuario")
    if not datos:
        return None
    inactiva = time.time() - request.session.get(CLAVE_ACTIVIDAD, 0) > settings.sesion_inactividad_minutos * 60
    if inactiva or not cuenta_vigente(datos, request.session.get(CLAVE_HUELLA)):
        request.session.clear()
        return None
    iniciar_actividad(request)
    return UsuarioSesion(**datos)


def usuario_opcional(request: Request) -> Optional[UsuarioSesion]:
    """Devuelve el usuario de la sesión, o None si nadie ha iniciado sesión, si
    la sesión estuvo inactiva demasiado tiempo o si la cuenta ya no está vigente.
    Se resuelve una vez por petición (se guarda en request.state)."""
    estado = getattr(request, "state", None)
    if estado is not None and hasattr(estado, "usuario_sesion"):
        return estado.usuario_sesion
    usuario = _usuario_de_sesion(request)
    if estado is not None:
        estado.usuario_sesion = usuario
    return usuario


def usuario_actual(request: Request) -> UsuarioSesion:
    """Exige sesión activa. Si no la hay, redirige al login."""
    usuario = usuario_opcional(request)
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="Sesión requerida",
            headers={"Location": "/login"},
        )
    # Contraseña temporal (restablecida por el coordinador): hasta cambiarla no
    # se puede usar nada más.
    if request.session.get(CLAVE_CAMBIO_OBLIGATORIO) and request.url.path not in RUTAS_SIN_CAMBIO:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="Cambio de contraseña requerido",
            headers={"Location": "/cuenta"},
        )
    return usuario


def requiere_rol(*roles_permitidos: str):
    """Restringe una ruta a ciertos roles.

    Es una primera barrera de usabilidad (evita mostrar pantallas que fallarían),
    no la defensa principal: quien realmente niega las operaciones no permitidas
    es PostgreSQL, vía el SET LOCAL ROLE que aplica database.get_db().
    """

    def verificador(usuario: UsuarioSesion = Depends(usuario_actual)) -> UsuarioSesion:
        # rol_admin es un superconjunto de rol_coordinador: una ruta abierta al
        # coordinador también lo está para el admin, sin tener que enumerarlo en
        # los 56 puntos que ya existen. Lo exclusivo del admin se pide nombrándolo.
        permitidos = set(roles_permitidos)
        if "rol_coordinador" in permitidos:
            permitidos.add("rol_admin")
        if usuario.rol_db not in permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tu rol no tiene acceso a este módulo",
            )
        return usuario

    return verificador
