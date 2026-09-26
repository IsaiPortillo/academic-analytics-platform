"""Capa de conexión híbrida a PostgreSQL y Neo4j — SCRUM-33.

Punto único de entrada a ambos motores para todo el pipeline, de modo que
SCRUM-34 (extracción) y SCRUM-35 (carga) no repitan configuración ni abran
conexiones por su cuenta.

Sobre los modelos: el esquema operacional ya está mapeado en
backend/app/models.py y no se duplica aquí — dos mapeos del mismo esquema se
desincronizan tarde o temprano. Como `backend/` no es un paquete instalable,
se agrega al sys.path para poder importarlo (ver `modelos_oltp`). Lo correcto a
futuro sería extraer los modelos a un paquete compartido, pero eso toca código
de toda la Fase 2 y queda fuera del alcance de este ticket.
"""

import sys
from contextlib import contextmanager
from pathlib import Path

from neo4j import Driver, GraphDatabase
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import RAIZ_PROYECTO, settings

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SesionOLTP = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def modelos_oltp():
    """Devuelve el módulo de modelos SQLAlchemy del backend.

    Import perezoso y con ajuste de sys.path: así el ETL reutiliza el mapeo del
    esquema sin que importar este módulo obligue a tener el backend disponible.
    """
    ruta_backend = str(RAIZ_PROYECTO / "backend")
    if ruta_backend not in sys.path:
        sys.path.insert(0, ruta_backend)
    from app import models  # noqa: PLC0415  (import diferido a propósito)

    return models


@contextmanager
def sesion_oltp() -> Session:
    """Sesión de solo lectura sobre el esquema operacional.

    No se expone commit: si algo intentara escribir, PostgreSQL lo rechazaría
    de todos modos por los permisos de rol_etl. El rollback al salir deja la
    conexión limpia para el pool.
    """
    sesion = SesionOLTP()
    try:
        yield sesion
    finally:
        sesion.rollback()
        sesion.close()


def crear_driver_neo4j() -> Driver:
    return GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )


@contextmanager
def sesion_grafo():
    """Sesión contra el grafo curricular de Neo4j."""
    driver = crear_driver_neo4j()
    try:
        with driver.session() as sesion:
            yield sesion
    finally:
        driver.close()
