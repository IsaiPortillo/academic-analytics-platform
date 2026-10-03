"""Comprobación del aislamiento de la vista ejecutiva — Fase 4.1.

Un dashboard sobre las tablas transaccionales es motivo explícito de rechazo
del proyecto. La vista ejecutiva lee el DW con su propia conexión
(app/dw.py), y este script demuestra contra PostgreSQL que esa conexión no
puede tocar el OLTP:

  1. rol_dashboard puede leer dw_academico.
  2. rol_dashboard NO puede leer academico_oltp (permiso denegado).
  3. rol_dashboard NO puede escribir en dw_academico (permiso denegado).

Sale con código distinto de cero si alguna falla.

    cd backend && python -m app.verificar_dw
"""

import sys

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from .dw import engine

# SQLSTATE insufficient_privilege: lo que devuelve PostgreSQL al negar un GRANT.
PERMISO_DENEGADO = "42501"


def _debe_ser_rechazado(sql: str, descripcion: str) -> int:
    with engine().connect() as conexion:
        try:
            conexion.execute(text(sql))
        except DBAPIError as exc:
            # Solo el rechazo por permisos demuestra algo; cualquier otro error
            # (p. ej. la base apagada) se propaga y cuenta como fallo.
            if getattr(exc.orig, "pgcode", None) != PERMISO_DENEGADO:
                raise
            print(f"  [OK] {descripcion}: {exc.orig.diag.message_primary}")
            return 0
        finally:
            conexion.rollback()
    print(f"  [FALLO] {descripcion}: PostgreSQL lo permitió. Revisa los GRANT de rol_dashboard.",
          file=sys.stderr)
    return 1


def verificar_lectura_dw() -> int:
    with engine().connect() as conexion:
        usuario = conexion.scalar(text("SELECT current_user"))
        hechos = conexion.scalar(text("SELECT count(*) FROM dw_academico.fact_inscripcion"))
    print(f"  [OK] Lectura del DW como '{usuario}': {hechos:,} hechos de inscripción")
    return 0


def verificar_sin_acceso_oltp() -> int:
    return _debe_ser_rechazado(
        "SELECT 1 FROM academico_oltp.estudiantes LIMIT 1",
        "Lectura de academico_oltp rechazada",
    )


def verificar_solo_lectura_dw() -> int:
    return _debe_ser_rechazado(
        "DELETE FROM dw_academico.carga_control WHERE false",
        "Escritura en dw_academico rechazada",
    )


def main() -> int:
    print("Verificando el aislamiento de la vista ejecutiva (Fase 4.1)\n")
    fallos = 0
    for verificacion in (verificar_lectura_dw, verificar_sin_acceso_oltp, verificar_solo_lectura_dw):
        try:
            fallos += verificacion()
        except Exception as exc:  # noqa: BLE001 - se reporta y se sigue con las demas
            print(f"  [FALLO] {verificacion.__name__}: {exc}", file=sys.stderr)
            fallos += 1

    print()
    if fallos:
        print(f"{fallos} verificacion(es) fallaron.", file=sys.stderr)
        return 1
    print("Todas las verificaciones pasaron.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
