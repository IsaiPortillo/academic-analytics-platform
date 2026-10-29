"""Malla curricular en Neo4j: lectura y edición de prerrequisitos desde la app.

Neo4j sigue siendo la fuente única de la malla: (A)-[:REQUIERE_APROBADA]->(B)
significa «para cursar A hay que haber aprobado B». El ETL la lleva al DW
(bridge_prerrequisito) y desde ahí la ven la red curricular y la matrícula, así
que después de editar hay que recargar el DW.

Regla que el grafo no impone por sí solo: la malla es acíclica. Si A exige B,
B no puede exigir (directa o indirectamente) a A; un ciclo dejaría materias
imposibles de cursar. Se comprueba antes de crear cada arista.

Credenciales: Neo4j Community no tiene roles por base ni por operación (eso es
de la edición Enterprise), así que la aplicación usa las mismas del ETL
(NEO4J_* en el .env). Si no están, la pantalla lo dice y no ofrece editar.
"""

from dataclasses import dataclass
from typing import Optional

from .config import settings

AREA_SIN_DEFINIR = "Sin área"

_driver = None


class MallaNoDisponible(RuntimeError):
    pass


class ReglaMalla(ValueError):
    """La operación violaría una regla de la malla (ciclo, duplicado)."""


def _sesion():
    global _driver
    if not settings.neo4j_password:
        raise MallaNoDisponible("Neo4j no está configurado (NEO4J_PASSWORD en el .env).")
    if _driver is None:
        from neo4j import GraphDatabase  # noqa: PLC0415 (solo si se usa la malla)
        _driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
    try:
        return _driver.session()
    except Exception as exc:  # noqa: BLE001
        raise MallaNoDisponible(f"No se pudo conectar con Neo4j: {exc}") from exc


@dataclass(frozen=True)
class Arista:
    materia: str
    requisito: str


def leer() -> tuple[dict[str, dict], list[Arista]]:
    """(nodos por código, aristas)."""
    try:
        with _sesion() as s:
            nodos = {r["codigo"]: dict(r) for r in s.run(
                "MATCH (m:Materia) RETURN m.codigo AS codigo, m.nombre AS nombre, m.ciclo AS ciclo, "
                "m.uv AS uv, coalesce(m.area, $sin) AS area ORDER BY m.ciclo, m.codigo", sin=AREA_SIN_DEFINIR)}
            aristas = [Arista(r["a"], r["b"]) for r in s.run(
                "MATCH (a:Materia)-[:REQUIERE_APROBADA]->(b:Materia) RETURN a.codigo AS a, b.codigo AS b "
                "ORDER BY a.codigo, b.codigo")]
    except MallaNoDisponible:
        raise
    except Exception as exc:  # noqa: BLE001 - conexión rechazada, credenciales, etc.
        raise MallaNoDisponible(f"No se pudo leer la malla en Neo4j: {exc}") from exc
    return nodos, aristas


def _asegurar_nodo(tx, materia: dict, area: Optional[str] = None):
    """Crea o actualiza el nodo con los datos del catálogo (PostgreSQL). El área
    solo existe en el grafo: se conserva salvo que se indique otra."""
    tx.run("MERGE (m:Materia {codigo: $codigo}) "
           "SET m.nombre = $nombre, m.uv = $uv, m.ciclo = $ciclo, "
           "    m.area = coalesce($area, m.area, $sin)",
           codigo=materia["codigo"], nombre=materia["nombre"], uv=materia["uv"], ciclo=materia["ciclo"],
           area=area, sin=AREA_SIN_DEFINIR)


def agregar(materia: dict, requisito: dict) -> None:
    if materia["codigo"] == requisito["codigo"]:
        raise ReglaMalla("Una materia no puede ser prerrequisito de sí misma.")
    with _sesion() as s:
        def tx(t):
            if t.run("MATCH (:Materia {codigo: $a})-[r:REQUIERE_APROBADA]->(:Materia {codigo: $b}) RETURN r",
                     a=materia["codigo"], b=requisito["codigo"]).single():
                raise ReglaMalla(f"{materia['codigo']} ya exige {requisito['codigo']}.")
            camino = t.run(
                "MATCH p = (:Materia {codigo: $b})-[:REQUIERE_APROBADA*1..]->(:Materia {codigo: $a}) "
                "RETURN [n IN nodes(p) | n.codigo] AS ruta LIMIT 1",
                a=materia["codigo"], b=requisito["codigo"]).single()
            if camino:
                ruta = " → ".join(camino["ruta"])
                raise ReglaMalla(f"Se formaría un ciclo: {requisito['codigo']} ya depende de "
                                 f"{materia['codigo']} ({ruta}). La malla no puede tener ciclos.")
            _asegurar_nodo(t, materia)
            _asegurar_nodo(t, requisito)
            t.run("MATCH (a:Materia {codigo: $a}), (b:Materia {codigo: $b}) "
                  "MERGE (a)-[:REQUIERE_APROBADA]->(b)", a=materia["codigo"], b=requisito["codigo"])
        s.execute_write(tx)


def quitar(materia: str, requisito: str) -> bool:
    with _sesion() as s:
        resultado = s.execute_write(lambda t: t.run(
            "MATCH (:Materia {codigo: $a})-[r:REQUIERE_APROBADA]->(:Materia {codigo: $b}) "
            "DELETE r RETURN count(r) AS n", a=materia, b=requisito).single()["n"])
    return resultado > 0


def sincronizar(materias: list[dict], areas: dict[str, str]) -> int:
    """Crea o actualiza un nodo por cada materia del catálogo. Devuelve cuántos."""
    with _sesion() as s:
        def tx(t):
            for m in materias:
                _asegurar_nodo(t, m, areas.get(m["codigo"]) or None)
        s.execute_write(tx)
    return len(materias)
