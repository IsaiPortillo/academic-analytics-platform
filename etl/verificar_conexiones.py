"""Comprobación de las conexiones del ETL — SCRUM-33.

Verifica tres cosas y sale con código distinto de cero si alguna falla:

  1. Que se puede leer el esquema operacional con rol_etl.
  2. Que se puede leer el grafo curricular en Neo4j.
  3. Que el ETL NO puede escribir en el esquema operacional.

El punto 3 es el que importa: es el mismo modelo de seguridad de la Fase 2
aplicado a la capa analítica. Que el ETL sea de solo lectura no depende de la
disciplina de quien escriba el pipeline, sino de los GRANT de PostgreSQL. Este
script deja esa garantía demostrable en vivo, como el README hace con
rol_docente.

    python -m etl.verificar_conexiones
"""

import sys

from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from .conexiones import modelos_oltp, sesion_grafo, sesion_oltp


def verificar_lectura_oltp() -> int:
    modelos = modelos_oltp()
    with sesion_oltp() as sesion:
        estudiantes = sesion.scalar(select(func.count()).select_from(modelos.Estudiante))
        inscripciones = sesion.scalar(select(func.count()).select_from(modelos.Inscripcion))
        usuario = sesion.scalar(select(func.current_user()))
    print(f"  [OK] Lectura OLTP como '{usuario}': "
          f"{estudiantes:,} estudiantes, {inscripciones:,} inscripciones")
    return 0


def verificar_lectura_grafo() -> int:
    with sesion_grafo() as sesion:
        resultado = sesion.run(
            "MATCH (m:Materia) OPTIONAL MATCH (m)-[r:REQUIERE_APROBADA]->() "
            "RETURN count(DISTINCT m) AS materias, count(r) AS prerrequisitos"
        ).single()
    print(f"  [OK] Lectura Neo4j: {resultado['materias']} materias, "
          f"{resultado['prerrequisitos']} relaciones de prerrequisito")
    return 0


def verificar_solo_lectura() -> int:
    """Intenta escribir a propósito. Lo correcto es que PostgreSQL lo rechace."""
    modelos = modelos_oltp()
    with sesion_oltp() as sesion:
        try:
            sesion.execute(
                text("UPDATE academico_oltp.estudiantes SET activo = activo "
                     "WHERE estudiante_id = (SELECT min(estudiante_id) "
                     "FROM academico_oltp.estudiantes)")
            )
            sesion.flush()
        except DBAPIError as exc:
            diag = getattr(exc.orig, "diag", None)
            mensaje = diag.message_primary if diag is not None else str(exc.orig)
            print(f"  [OK] Escritura rechazada por PostgreSQL: {mensaje}")
            return 0

    print("  [FALLO] El ETL pudo escribir en academico_oltp. "
          "Revisa los permisos de rol_etl: deberia tener solo SELECT.", file=sys.stderr)
    return 1


def main() -> int:
    print("Verificando conexiones del ETL (SCRUM-33)\n")
    fallos = 0
    for verificacion in (verificar_lectura_oltp, verificar_lectura_grafo, verificar_solo_lectura):
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
