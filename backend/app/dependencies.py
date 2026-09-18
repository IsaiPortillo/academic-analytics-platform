from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, Request, status


@dataclass
class UsuarioSesion:
    usuario_id: int
    username: str
    nombre_completo: str
    rol_db: str
    docente_id: Optional[int]

    @property
    def es_coordinador(self) -> bool:
        return self.rol_db == "rol_coordinador"

    @property
    def rol_legible(self) -> str:
        return "Coordinador" if self.es_coordinador else "Docente"


def usuario_opcional(request: Request) -> Optional[UsuarioSesion]:
    """Devuelve el usuario de la sesión, o None si nadie ha iniciado sesión."""
    datos = request.session.get("usuario")
    if not datos:
        return None
    return UsuarioSesion(**datos)


def usuario_actual(request: Request) -> UsuarioSesion:
    """Exige sesión activa. Si no la hay, redirige al login."""
    usuario = usuario_opcional(request)
    if usuario is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            detail="Sesión requerida",
            headers={"Location": "/login"},
        )
    return usuario


def requiere_rol(*roles_permitidos: str):
    """Restringe una ruta a ciertos roles.

    Es una primera barrera de usabilidad (evita mostrar pantallas que fallarían),
    no la defensa principal: quien realmente niega las operaciones no permitidas
    es PostgreSQL, vía el SET LOCAL ROLE que aplica database.get_db().
    """

    def verificador(usuario: UsuarioSesion = Depends(usuario_actual)) -> UsuarioSesion:
        if usuario.rol_db not in roles_permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tu rol no tiene acceso a este módulo",
            )
        return usuario

    return verificador
