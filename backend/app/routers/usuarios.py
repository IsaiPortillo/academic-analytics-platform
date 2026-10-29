"""Usuarios de la aplicación: alta, rol, activación y restablecimiento (coordinador)
y cambio de la propia contraseña (cualquier usuario).

Reglas que protegen de quedarse sin administración:
  - el coordinador no puede desactivarse ni quitarse el rol a sí mismo;
  - no se puede dejar al sistema sin ningún coordinador activo.

Las contraseñas temporales se muestran UNA vez, en la respuesta del POST, y no se
guardan en ningún lado (tampoco en la sesión ni en el aviso). Al restablecer, la
cuenta queda obligada a cambiarla en su siguiente inicio de sesión y las
sesiones abiertas se cortan (dependencies.cuenta_vigente compara la huella).
"""

import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from ..avisos import redirigir, tomar_aviso
from ..config import settings
from ..database import ROLES_VALIDOS, get_db
from ..dependencies import (CLAVE_CAMBIO_OBLIGATORIO, CLAVE_HUELLA, UsuarioSesion, huella_password,
                            requiere_rol, usuario_actual)
from ..models import Docente, Usuario
from ..security import hashear_password, verificar_password
from ..templating import templates

router = APIRouter(tags=["usuarios"])

PATRON_USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{2,49}$")
LONGITUD_MINIMA = 10
LARGO_NOMBRE = (3, 120)   # los mismos límites que actualizar_perfil_propio() (script 21)
# El Salvador no tiene horario de verano: un desfase fijo es exacto y no exige tzdata.
ZONA_LOCAL = timezone(timedelta(hours=-6))
ROLES = {"rol_coordinador": "Coordinador", "rol_docente": "Docente"}


def _mensaje_bd(exc: DBAPIError) -> str:
    diag = getattr(exc.orig, "diag", None)
    if diag is not None and diag.constraint_name == "usuarios_username_key":
        return "Ese nombre de usuario ya existe."
    if diag is not None and diag.constraint_name == "chk_docente_vinculado":
        return "Un docente debe estar vinculado a su registro de docente; un coordinador, a ninguno."
    return (diag.message_primary if diag is not None and diag.message_primary
            else "La base de datos rechazó la operación.")


def problema_password(nueva: str, username: str) -> Optional[str]:
    """None si la contraseña es aceptable; si no, el motivo."""
    if len(nueva) < LONGITUD_MINIMA:
        return f"La contraseña debe tener al menos {LONGITUD_MINIMA} caracteres."
    if not re.search(r"[A-Za-z]", nueva) or not re.search(r"\d", nueva):
        return "La contraseña debe combinar letras y números."
    if username.lower() in nueva.lower():
        return "La contraseña no puede contener el nombre de usuario."
    return None


def normalizar_nombre(nombre: str) -> str:
    """Espacios sobrantes fuera, como lo hace la función del motor."""
    return re.sub(r"\s+", " ", nombre or "").strip()


def hora_local(momento: Optional[datetime]) -> Optional[str]:
    """«29/10/2026 11:55» en hora de El Salvador; None si nunca ocurrió."""
    if momento is None:
        return None
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(ZONA_LOCAL).strftime("%d/%m/%Y %H:%M")


def password_temporal() -> str:
    # Sin caracteres que se confundan al dictarla (0/O, 1/l/I).
    alfabeto = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"
    while True:
        clave = "".join(secrets.choice(alfabeto) for _ in range(14))
        if re.search(r"\d", clave) and re.search(r"[A-Za-z]", clave):
            return clave


def _coordinadores_activos(db: Session, excepto: Optional[int] = None) -> int:
    consulta = select(func.count()).select_from(Usuario).where(
        Usuario.rol_db == "rol_coordinador", Usuario.activo.is_(True))
    if excepto is not None:
        consulta = consulta.where(Usuario.usuario_id != excepto)
    return db.scalar(consulta)


def _docentes(db: Session):
    return db.scalars(select(Docente).order_by(Docente.codigo_docente)).all()


def _credencial(request, usuario, cuenta: Usuario, clave: str, accion: str):
    return templates.TemplateResponse(request, "modulos/usuario_credencial.html", {
        "usuario": usuario, "cuenta": cuenta, "clave": clave, "accion": accion,
    }, headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------------------
# Administración (coordinador)
# ---------------------------------------------------------------------------

@router.get("/usuarios")
def listar(
    request: Request,
    buscar: Optional[str] = Query(None),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    ok, error = tomar_aviso(request)
    consulta = select(Usuario, Docente).outerjoin(Docente, Docente.docente_id == Usuario.docente_id)
    if buscar:
        patron = f"%{buscar.strip()}%"
        consulta = consulta.where(or_(Usuario.username.ilike(patron), Usuario.nombre_completo.ilike(patron)))
    cuentas = db.execute(consulta.order_by(Usuario.activo.desc(), Usuario.username)).all()
    return templates.TemplateResponse(request, "modulos/usuarios.html", {
        "usuario": usuario, "cuentas": cuentas, "docentes": _docentes(db), "roles": ROLES,
        "buscar": buscar or "", "ok": ok, "error": error, "longitud_minima": LONGITUD_MINIMA,
    })


@router.post("/usuarios")
def crear(
    request: Request,
    username: str = Form(...),
    nombre_completo: str = Form(...),
    rol_db: str = Form(...),
    docente_id: Optional[str] = Form(None),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    username = username.strip().lower()
    nombre_completo = nombre_completo.strip()
    if not PATRON_USERNAME.match(username):
        return redirigir(request, "/usuarios", error="El usuario debe tener de 3 a 50 caracteres: minúsculas, "
                                                     "números, punto, guion o guion bajo.")
    if not nombre_completo:
        return redirigir(request, "/usuarios", error="El nombre completo es obligatorio.")
    if rol_db not in ROLES_VALIDOS:
        return redirigir(request, "/usuarios", error="Rol no reconocido.")
    docente = int(docente_id) if rol_db == "rol_docente" and (docente_id or "").isdigit() else None
    if rol_db == "rol_docente" and docente is None:
        return redirigir(request, "/usuarios", error="Elige el docente al que corresponde la cuenta.")
    clave = password_temporal()
    cuenta = Usuario(username=username, nombre_completo=nombre_completo, rol_db=rol_db, docente_id=docente,
                     password_hash=hashear_password(clave), debe_cambiar_password=True)
    try:
        db.add(cuenta)
        db.flush()
    except DBAPIError as exc:
        db.rollback()
        return redirigir(request, "/usuarios", error=_mensaje_bd(exc))
    return _credencial(request, usuario, cuenta, clave, "creada")


def _cuenta(db: Session, usuario_id: int) -> Optional[Usuario]:
    return db.get(Usuario, usuario_id)


@router.post("/usuarios/{usuario_id}/editar")
def editar(
    request: Request,
    usuario_id: int,
    nombre_completo: str = Form(...),
    rol_db: str = Form(...),
    docente_id: Optional[str] = Form(None),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    cuenta = _cuenta(db, usuario_id)
    if cuenta is None:
        return redirigir(request, "/usuarios", error="Usuario no encontrado.")
    if rol_db not in ROLES_VALIDOS:
        return redirigir(request, "/usuarios", error="Rol no reconocido.")
    if cuenta.usuario_id == usuario.usuario_id and rol_db != cuenta.rol_db:
        return redirigir(request, "/usuarios", error="No puedes cambiar tu propio rol.")
    if (cuenta.rol_db == "rol_coordinador" and rol_db != "rol_coordinador" and cuenta.activo
            and _coordinadores_activos(db, excepto=cuenta.usuario_id) == 0):
        return redirigir(request, "/usuarios", error="Debe quedar al menos un coordinador activo.")
    docente = int(docente_id) if rol_db == "rol_docente" and (docente_id or "").isdigit() else None
    if rol_db == "rol_docente" and docente is None:
        return redirigir(request, "/usuarios", error="Elige el docente al que corresponde la cuenta.")
    try:
        cuenta.nombre_completo = nombre_completo.strip() or cuenta.nombre_completo
        cuenta.rol_db = rol_db
        cuenta.docente_id = docente
        db.flush()
    except DBAPIError as exc:
        db.rollback()
        return redirigir(request, "/usuarios", error=_mensaje_bd(exc))
    return redirigir(request, "/usuarios", ok=f"Cuenta «{cuenta.username}» actualizada. "
                                              "Si cambió el rol, su sesión abierta se cerró.")


@router.post("/usuarios/{usuario_id}/estado")
def cambiar_estado(
    request: Request,
    usuario_id: int,
    activo: bool = Form(...),
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    cuenta = _cuenta(db, usuario_id)
    if cuenta is None:
        return redirigir(request, "/usuarios", error="Usuario no encontrado.")
    if cuenta.usuario_id == usuario.usuario_id and not activo:
        return redirigir(request, "/usuarios", error="No puedes desactivar tu propia cuenta.")
    if (not activo and cuenta.rol_db == "rol_coordinador"
            and _coordinadores_activos(db, excepto=cuenta.usuario_id) == 0):
        return redirigir(request, "/usuarios", error="Debe quedar al menos un coordinador activo.")
    cuenta.activo = activo
    db.flush()
    return redirigir(request, "/usuarios", ok=f"Cuenta «{cuenta.username}» "
                                              + ("activada." if activo else "desactivada: su sesión se cerró."))


@router.post("/usuarios/{usuario_id}/restablecer")
def restablecer(
    request: Request,
    usuario_id: int,
    usuario: UsuarioSesion = Depends(requiere_rol("rol_coordinador")),
    db: Session = Depends(get_db),
):
    cuenta = _cuenta(db, usuario_id)
    if cuenta is None:
        return redirigir(request, "/usuarios", error="Usuario no encontrado.")
    if cuenta.usuario_id == usuario.usuario_id:
        return redirigir(request, "/usuarios", error="Para tu propia cuenta usa «Cambiar mi contraseña».")
    clave = password_temporal()
    cuenta.password_hash = hashear_password(clave)
    cuenta.debe_cambiar_password = True
    db.flush()
    return _credencial(request, usuario, cuenta, clave, "restablecida")


# ---------------------------------------------------------------------------
# Mi cuenta (cualquier usuario)
# ---------------------------------------------------------------------------

@router.get("/cuenta")
def ver_cuenta(
    request: Request,
    usuario: UsuarioSesion = Depends(usuario_actual),
    db: Session = Depends(get_db),
):
    ok, error = tomar_aviso(request)
    registro = db.scalar(select(Usuario).where(Usuario.usuario_id == usuario.usuario_id))
    docente = db.get(Docente, usuario.docente_id) if usuario.docente_id else None
    return templates.TemplateResponse(request, "modulos/cuenta.html", {
        "usuario": usuario, "ok": ok, "error": error, "longitud_minima": LONGITUD_MINIMA,
        "obligatorio": bool(request.session.get(CLAVE_CAMBIO_OBLIGATORIO)),
        "docente": docente, "largo_nombre": LARGO_NOMBRE,
        "ultimo_acceso": hora_local(getattr(registro, "ultimo_acceso", None)),
        "password_cambiado": hora_local(getattr(registro, "password_cambiado_en", None)),
        "creada": hora_local(getattr(registro, "creado_en", None)),
        "inactividad_minutos": settings.sesion_inactividad_minutos,
        "duracion_horas": settings.sesion_duracion_horas,
    })


@router.post("/cuenta/perfil")
def actualizar_perfil(
    request: Request,
    nombre_completo: str = Form(...),
    usuario: UsuarioSesion = Depends(usuario_actual),
    db: Session = Depends(get_db),
):
    nombre = normalizar_nombre(nombre_completo)
    minimo, maximo = LARGO_NOMBRE
    if not minimo <= len(nombre) <= maximo:
        return redirigir(request, "/cuenta", error=f"El nombre debe tener entre {minimo} y {maximo} caracteres.")
    if nombre == usuario.nombre_completo:
        return redirigir(request, "/cuenta", ok="No había cambios que guardar.")
    try:
        # El docente no tiene UPDATE sobre usuarios: la función del motor solo
        # cambia el nombre de la fila de quien está en la sesión (script 21).
        db.execute(text("SELECT academico_oltp.actualizar_perfil_propio(:n)"), {"n": nombre})
    except DBAPIError as exc:
        db.rollback()
        return redirigir(request, "/cuenta", error=_mensaje_bd(exc))
    # El nombre de la barra superior sale de la sesión: se actualiza ahí también.
    request.session["usuario"] = {**request.session["usuario"], "nombre_completo": nombre}
    return redirigir(request, "/cuenta", ok="Tus datos se actualizaron.")


@router.get("/cuenta/contrasena")
def ver_cambio():
    # Enlaces y marcadores anteriores: la contraseña ahora se cambia en Mi cuenta.
    return RedirectResponse("/cuenta", status_code=303)


@router.post("/cuenta/contrasena")
def cambiar(
    request: Request,
    actual: str = Form(...),
    nueva: str = Form(...),
    confirmar: str = Form(...),
    usuario: UsuarioSesion = Depends(usuario_actual),
    db: Session = Depends(get_db),
):
    destino = "/cuenta"
    registro = db.scalar(select(Usuario).where(Usuario.usuario_id == usuario.usuario_id))
    if registro is None or not verificar_password(actual, registro.password_hash):
        return redirigir(request, destino, error="La contraseña actual no es correcta.")
    if nueva != confirmar:
        return redirigir(request, destino, error="La nueva contraseña y su confirmación no coinciden.")
    if nueva == actual:
        return redirigir(request, destino, error="La nueva contraseña debe ser distinta de la actual.")
    problema = problema_password(nueva, usuario.username)
    if problema:
        return redirigir(request, destino, error=problema)
    nuevo_hash = hashear_password(nueva)
    try:
        # El docente no tiene UPDATE sobre usuarios: la función del motor solo
        # cambia la fila de quien está en la sesión (script 18).
        db.execute(text("SELECT academico_oltp.cambiar_password_propio(:h)"), {"h": nuevo_hash})
    except DBAPIError as exc:
        db.rollback()
        return redirigir(request, destino, error=_mensaje_bd(exc))
    # Esta sesión sigue valiendo con la nueva huella; las demás abiertas se cortan.
    request.session[CLAVE_HUELLA] = huella_password(nuevo_hash)
    request.session.pop(CLAVE_CAMBIO_OBLIGATORIO, None)
    return redirigir(request, destino, ok="Contraseña actualizada. Las demás sesiones abiertas con la anterior se cerraron.")
