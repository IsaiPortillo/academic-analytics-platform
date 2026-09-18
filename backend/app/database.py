from fastapi import HTTPException, Request, status
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

# Únicos roles a los que la aplicación puede cambiar. SET ROLE no admite
# parámetros ligados, así que el nombre del rol se interpola en el SQL: esta
# lista blanca es lo que impide que ese punto sea una inyección.
ROLES_VALIDOS = frozenset({"rol_coordinador", "rol_docente"})

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db(request: Request):
    """Sesión de base de datos que adopta el rol PostgreSQL del usuario logueado.

    Se usa SET LOCAL (no SET): el rol se revierte al cerrar la transacción, de
    modo que la conexión vuelve limpia al pool. Con SET a secas, el rol quedaría
    pegado a la conexión y la siguiente petición heredaría el rol de otro usuario.
    """
    db = SessionLocal()
    try:
        rol = request.session.get("rol_db")
        if rol is not None:
            if rol not in ROLES_VALIDOS:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Rol de sesión no reconocido",
                )
            db.execute(text(f"SET LOCAL ROLE {rol}"))
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
