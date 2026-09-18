"""
UNIVERSIDAD DE EL SALVADOR - FACULTAD MULTIDISCIPLINARIA ORIENTAL
ESPECIALIZACIÓN EN BD & BI 2026
FASE 1 - PUNTO 1.3: AUTOMATIZACIÓN DE CARGA EN NEO4J
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

# Credenciales desde el archivo .env de la raíz del proyecto (ver .env.example)
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

if not NEO4J_PASSWORD:
    sys.exit("ERROR: NEO4J_PASSWORD no está definida. Copia .env.example a .env y complétalo.")

MATERIAS_DATA = [
    {"codigo": "MAT115", "nombre": "Matemática I", "uv": 4, "ciclo": 1, "area": "Ciencias Básicas"},
    {"codigo": "PRG115", "nombre": "Programación I", "uv": 4, "ciclo": 1, "area": "Desarrollo de Software"},
    {"codigo": "ACA115", "nombre": "Álgebra Vectorial y Matrices", "uv": 4, "ciclo": 1, "area": "Ciencias Básicas"},
    {"codigo": "MAT215", "nombre": "Matemática II", "uv": 4, "ciclo": 2, "area": "Ciencias Básicas"},
    {"codigo": "PRG215", "nombre": "Programación II", "uv": 4, "ciclo": 2, "area": "Desarrollo de Software"},
    {"codigo": "BAD115", "nombre": "Bases de Datos I", "uv": 4, "ciclo": 3, "area": "Gestión de Datos"},
    {"codigo": "PRG315", "nombre": "Programación III", "uv": 4, "ciclo": 3, "area": "Desarrollo de Software"},
    {"codigo": "MAT315", "nombre": "Matemática III", "uv": 4, "ciclo": 3, "area": "Ciencias Básicas"},
    {"codigo": "BAD215", "nombre": "Bases de Datos II", "uv": 4, "ciclo": 4, "area": "Gestión de Datos"},
    {"codigo": "ADS115", "nombre": "Análisis y Diseño de Sistemas I", "uv": 4, "ciclo": 4, "area": "Ingeniería de Software"},
    {"codigo": "SIF115", "nombre": "Sistemas de Información", "uv": 4, "ciclo": 5, "area": "Ingeniería de Software"},
    {"codigo": "ADS215", "nombre": "Análisis y Diseño de Sistemas II", "uv": 4, "ciclo": 5, "area": "Ingeniería de Software"},
    {"codigo": "DWB115", "nombre": "Diseño Web y Aplicaciones", "uv": 4, "ciclo": 6, "area": "Desarrollo de Software"},
    {"codigo": "ARC115", "nombre": "Arquitectura de Computadoras", "uv": 4, "ciclo": 6, "area": "Hardware y Redes"},
    {"codigo": "IAI115", "nombre": "Inteligencia Artificial", "uv": 4, "ciclo": 7, "area": "Ciencia de Datos e IA"},
    {"codigo": "BIN115", "nombre": "Inteligencia de Negocios", "uv": 4, "ciclo": 8, "area": "Ciencia de Datos e IA"}
]

PRERREQUISITOS_DATA = [
    # (Materia_Destino, Materia_Prerrequisito)
    ("MAT215", "MAT115"),
    ("PRG215", "PRG115"),
    ("MAT315", "MAT215"),
    ("PRG315", "PRG215"),
    ("BAD115", "PRG115"),
    ("BAD215", "BAD115"),
    ("ADS115", "PRG215"),
    ("SIF115", "ADS115"),
    ("SIF115", "BAD115"),
    ("ADS215", "ADS115"),
    ("DWB115", "PRG315"),
    ("ARC115", "ACA115"),
    ("IAI115", "PRG315"),
    ("IAI115", "MAT315"),
    ("BIN115", "BAD215"),
    ("BIN115", "SIF115")
]

def cargar_grafo():
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    with driver.session() as session:
        print("[1/4] Creando restricciones...")
        session.run("""
            CREATE CONSTRAINT uq_materia_codigo IF NOT EXISTS
            FOR (m:Materia) REQUIRE m.codigo IS UNIQUE;
        """)

        print("[2/4] Sembrando nodos de materias...")
        session.run("""
            UNWIND $materias AS m
            MERGE (mat:Materia {codigo: m.codigo})
            SET mat.nombre = m.nombre,
                mat.uv = m.uv,
                mat.ciclo = m.ciclo,
                mat.area = m.area;
        """, materias=MATERIAS_DATA)

        print("[3/4] Creando relaciones :REQUIERE_APROBADA...")
        session.run("""
            UNWIND $prerrequisitos AS p
            MATCH (origen:Materia {codigo: p[0]})
            MATCH (requisito:Materia {codigo: p[1]})
            MERGE (origen)-[:REQUIERE_APROBADA]->(requisito);
        """, prerrequisitos=PRERREQUISITOS_DATA)

        print("[4/4] Verificando métricas del grafo...")
        result = session.run("""
            MATCH (n:Materia) 
            OPTIONAL MATCH (n)<-[r:REQUIERE_APROBADA]-() 
            RETURN count(DISTINCT n) AS total_materias, count(r) AS total_dependencias;
        """).single()
        
        print(f"\nGrafo cargado exitosamente:")
        print(f" - Total Asignaturas (Nodos): {result['total_materias']}")
        print(f" - Total Relaciones de Dependencia: {result['total_dependencias']}")

    driver.close()

if __name__ == "__main__":
    try:
        cargar_grafo()
    except Exception as e:
        print(f"Error al conectar o ejecutar en Neo4j: {e}", file=sys.stderr)