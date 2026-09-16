//A. Identificación de Asignaturas "Cuello de Botella" (Bloqueo Directo e Indirecto en Cascada)

MATCH (base:Materia)<-[:REQUIERE_APROBADA*1..5]-(bloqueadas:Materia)
RETURN base.codigo AS Asignatura,
       base.nombre AS Nombre,
       base.ciclo AS CicloPensum,
       count(DISTINCT bloqueadas) AS MateriasBloqueadasEnCascada
ORDER BY MateriasBloqueadasEnCascada DESC;

//B. Ruta Crítica hacia la Graduación (Camino más largo de prerrequisitos)
Cypher
MATCH p = (meta:Materia {codigo: 'BIN115'})-[:REQUIERE_APROBADA*]->(raiz:Materia)
WHERE NOT (raiz)-[:REQUIERE_APROBADA]->()
RETURN [n in nodes(p) | n.codigo] AS CadenaDependencia, length(p) AS ProfundidadRuta
ORDER BY ProfundidadRuta DESC;