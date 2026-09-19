"""Alta de usuarios de la aplicación.

Se conecta con el rol de servicio (rol_app) y cambia a rol_coordinador, que es
quien tiene permiso de INSERT sobre academico_oltp.usuarios. No requiere el
superusuario de PostgreSQL.

Ejemplos:
    # Crear los dos usuarios de demostración para entorno local
    python backend/scripts/crear_usuario.py --demo --password demo1234

    # Crear un usuario concreto (pide la contraseña de forma interactiva)
    python backend/scripts/crear_usuario.py --username jperez \\
        --nombre "Jose Perez" --rol rol_docente --docente-id 3
"""

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, text  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import Docente, Usuario  # noqa: E402
from app.security import hashear_password  # noqa: E402


def crear_usuario(db, username, nombre, rol, password, docente_id=None):
    if db.scalar(select(Usuario).where(Usuario.username == username)):
        print(f"  - '{username}' ya existe, se omite.")
        return False

    db.add(
        Usuario(
            username=username,
            password_hash=hashear_password(password),
            nombre_completo=nombre,
            rol_db=rol,
            docente_id=docente_id,
        )
    )
    db.flush()
    print(f"  + '{username}' creado ({rol}).")
    return True


def main():
    parser = argparse.ArgumentParser(description="Crea usuarios de la aplicación.")
    parser.add_argument("--demo", action="store_true", help="crear usuarios de demostración")
    parser.add_argument("--username")
    parser.add_argument("--nombre")
    parser.add_argument("--rol", choices=["rol_coordinador", "rol_docente"])
    parser.add_argument("--docente-id", type=int, help="requerido si el rol es rol_docente")
    parser.add_argument("--password", help="si se omite, se pide de forma interactiva")
    args = parser.parse_args()

    if not args.demo and not (args.username and args.nombre and args.rol):
        parser.error("indica --demo, o bien --username, --nombre y --rol")

    password = args.password or getpass.getpass("Contraseña: ")
    if not password:
        parser.error("la contraseña no puede estar vacía")

    db = SessionLocal()
    try:
        # rol_app no puede escribir en usuarios; rol_coordinador sí.
        db.execute(text("SET LOCAL ROLE rol_coordinador"))

        if args.demo:
            print("Creando usuarios de demostración:")
            crear_usuario(
                db, "coordinador", "Coordinador Académico", "rol_coordinador", password
            )

            primer_docente = db.scalar(select(Docente).order_by(Docente.docente_id).limit(1))
            if primer_docente is None:
                print(
                    "  ! No hay docentes en la base: omito el usuario docente.\n"
                    "    Ejecuta antes el generador de datos sintéticos."
                )
            else:
                crear_usuario(
                    db,
                    "docente",
                    f"Docente {primer_docente.codigo_docente}",
                    "rol_docente",
                    password,
                    docente_id=primer_docente.docente_id,
                )
        else:
            if args.rol == "rol_docente" and args.docente_id is None:
                parser.error("--docente-id es obligatorio para rol_docente")
            crear_usuario(
                db, args.username, args.nombre, args.rol, password, args.docente_id
            )

        db.commit()
        print("Listo.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
