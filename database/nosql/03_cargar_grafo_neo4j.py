"""
UNIVERSIDAD DE EL SALVADOR - FACULTAD MULTIDISCIPLINARIA ORIENTAL
ESPECIALIZACIÓN EN BD & BI 2026
FASE 1 - PUNTO 1.3: AUTOMATIZACIÓN DE CARGA EN NEO4J

Carga la malla curricular de Ingeniería de Sistemas Informáticos (el plan completo, 45
asignaturas en 10 ciclos) como grafo: un nodo por asignatura y una relación
(A)-[:REQUIERE_APROBADA]->(B) cuando para cursar A hay que haber aprobado B. Los datos
salen de scripts/generator/catalogo_ues.py, el mismo catálogo con el que el generador
llena la base relacional, así que ambos coinciden.

    python database/nosql/03_cargar_grafo_neo4j.py              # agrega o actualiza
    python database/nosql/03_cargar_grafo_neo4j.py --reiniciar  # deja el grafo igual al plan

--reiniciar borra del grafo las asignaturas y relaciones que no estén en el plan (por
ejemplo, las que alguien agregó desde «Malla curricular» en la aplicación).
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "generator"))
import catalogo_ues as cat  # noqa: E402

# Credenciales desde el archivo .env de la raíz del proyecto (ver .env.example)
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

MATERIAS_DATA = [
    {"codigo": m.codigo, "nombre": m.nombre, "uv": m.uv, "ciclo": m.ciclo, "area": m.area}
    for m in cat.ISI.materias
]

PRERREQUISITOS_DATA = [
    # (Materia_Destino, Materia_Prerrequisito)
    (m.codigo, requisito) for m in cat.ISI.materias for requisito in m.prerrequisitos
]


def cargar_grafo(reiniciar: bool = False) -> None:
    if not NEO4J_PASSWORD:
        sys.exit("ERROR: NEO4J_PASSWORD no está definida. Copia .env.example a .env y complétalo.")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    with driver.session() as session:
        print("[1/5] Creando restricciones...")
        session.run("""
            CREATE CONSTRAINT uq_materia_codigo IF NOT EXISTS
            FOR (m:Materia) REQUIRE m.codigo IS UNIQUE;
        """)

        if reiniciar:
            print("[2/5] Quitando lo que no está en el plan...")
            session.run("MATCH (m:Materia) WHERE NOT m.codigo IN $codigos DETACH DELETE m",
                        codigos=[m["codigo"] for m in MATERIAS_DATA])
            session.run("MATCH ()-[r:REQUIERE_APROBADA]->() DELETE r")
        else:
            print("[2/5] (sin --reiniciar: se conserva lo que ya había)")

        print("[3/5] Sembrando nodos de materias...")
        session.run("""
            UNWIND $materias AS m
            MERGE (mat:Materia {codigo: m.codigo})
            SET mat.nombre = m.nombre,
                mat.uv = m.uv,
                mat.ciclo = m.ciclo,
                mat.area = m.area;
        """, materias=MATERIAS_DATA)

        print("[4/5] Creando relaciones :REQUIERE_APROBADA...")
        session.run("""
            UNWIND $prerrequisitos AS p
            MATCH (origen:Materia {codigo: p[0]})
            MATCH (requisito:Materia {codigo: p[1]})
            MERGE (origen)-[:REQUIERE_APROBADA]->(requisito);
        """, prerrequisitos=[list(p) for p in PRERREQUISITOS_DATA])

        print("[5/5] Verificando métricas del grafo...")
        result = session.run("""
            MATCH (n:Materia)
            OPTIONAL MATCH (n)<-[r:REQUIERE_APROBADA]-()
            RETURN count(DISTINCT n) AS total_materias, count(r) AS total_dependencias;
        """).single()

        print("\nGrafo cargado exitosamente:")
        print(f" - Total Asignaturas (Nodos): {result['total_materias']}")
        print(f" - Total Relaciones de Dependencia: {result['total_dependencias']}")

    driver.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Carga la malla de Sistemas Informáticos en Neo4j.")
    parser.add_argument("--reiniciar", action="store_true",
                        help="deja el grafo igual al plan (borra lo que no esté en él)")
    argumentos = parser.parse_args()
    try:
        cargar_grafo(argumentos.reiniciar)
    except Exception as e:
        print(f"Error al conectar o ejecutar en Neo4j: {e}", file=sys.stderr)
        sys.exit(1)
