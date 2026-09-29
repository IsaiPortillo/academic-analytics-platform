"""Métricas de grafo de la malla curricular — SCRUM-34.

Alimentan el análisis de asignaturas cuello de botella de la Fase 4.3.

Semántica de la relación (ver database/nosql/03_malla_curricular.cql):
    (A)-[:REQUIERE_APROBADA]->(B)   "para cursar A hay que haber aprobado B"

Por lo tanto los *dependientes* de una materia B son las materias que apuntan
hacia ella: reprobar B las bloquea. Se calculan en Cypher y no en Python
porque el recorrido de caminos de longitud variable es justamente lo que un
motor de grafos resuelve de forma nativa, y es el argumento de por qué la
malla vive en Neo4j y no en una tabla de prerrequisitos en PostgreSQL (donde
el mismo cálculo exigiría un WITH RECURSIVE por materia).
"""

import pandas as pd
from neo4j import Session

# Una materia es cuello de botella si reprobarla bloquea, directa o
# indirectamente, al menos a un cuarto del resto del pensum. Se usa una
# proporción y no un número absoluto para que el criterio siga teniendo sentido
# si la malla crece más allá de las 16 materias del tronco actual.
UMBRAL_CUELLO_BOTELLA = 0.25

# Un solo recorrido por materia para cada métrica. Los caminos de longitud
# variable en Cypher no repiten relaciones, así que la consulta termina aunque
# alguien introdujera por error un ciclo en la malla.
CONSULTA_METRICAS = """
MATCH (m:Materia)
OPTIONAL MATCH (m)<-[:REQUIERE_APROBADA]-(directo:Materia)
WITH m, count(DISTINCT directo) AS dependientes_directos
OPTIONAL MATCH (m)<-[:REQUIERE_APROBADA*1..]-(cascada:Materia)
WITH m, dependientes_directos, count(DISTINCT cascada) AS dependientes_totales
OPTIONAL MATCH (m)-[:REQUIERE_APROBADA]->(requisito:Materia)
WITH m, dependientes_directos, dependientes_totales,
     count(DISTINCT requisito) AS prerrequisitos_directos
OPTIONAL MATCH abajo = (m)<-[:REQUIERE_APROBADA*1..]-(:Materia)
WITH m, dependientes_directos, dependientes_totales, prerrequisitos_directos,
     coalesce(max(length(abajo)), 0) AS longitud_cascada
OPTIONAL MATCH arriba = (m)-[:REQUIERE_APROBADA*1..]->(:Materia)
RETURN m.codigo AS codigo_materia,
       dependientes_directos,
       dependientes_totales - dependientes_directos AS dependientes_indirectos,
       dependientes_totales,
       prerrequisitos_directos,
       longitud_cascada,
       coalesce(max(length(arriba)), 0) AS profundidad_prerrequisitos
ORDER BY dependientes_totales DESC, codigo_materia
"""

COLUMNAS_METRICAS = [
    "codigo_materia",
    "dependientes_directos",
    "dependientes_indirectos",
    "dependientes_totales",
    "prerrequisitos_directos",
    "longitud_cascada",
    "profundidad_prerrequisitos",
]


def extraer_metricas_grafo(sesion: Session) -> pd.DataFrame:
    """Métricas estructurales de cada materia de la malla.

    - dependientes_directos: materias que la tienen como prerrequisito inmediato.
    - dependientes_indirectos: materias bloqueadas en cascada, sin contar las directas.
    - longitud_cascada: cuántos ciclos de la cadena posterior se retrasan si se reprueba.
    - profundidad_prerrequisitos: cuántas materias encadenadas hay que aprobar antes.
    """
    registros = [dict(r) for r in sesion.run(CONSULTA_METRICAS)]
    return pd.DataFrame(registros, columns=COLUMNAS_METRICAS)


def clasificar_cuellos_de_botella(metricas: pd.DataFrame) -> pd.DataFrame:
    """Agrega indice_bloqueo (fracción del resto del pensum que la materia
    bloquea) y la marca es_cuello_botella según UMBRAL_CUELLO_BOTELLA."""
    resultado = metricas.copy()
    otras_materias = max(len(resultado) - 1, 1)
    resultado["indice_bloqueo"] = (resultado["dependientes_totales"] / otras_materias).round(4)
    resultado["es_cuello_botella"] = resultado["indice_bloqueo"] >= UMBRAL_CUELLO_BOTELLA
    return resultado
