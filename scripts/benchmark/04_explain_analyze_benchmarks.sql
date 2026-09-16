/**Sentencia SQL de Prueba 1*/

EXPLAIN (ANALYZE, BUFFERS, COSTS, VERBOSE)
SELECT 
    i.estudiante_id,
    p.codigo_periodo,
    ROUND(SUM(c.nota * (e.porcentaje / 100.0)), 2) AS nota_final_curso
FROM academico_oltp.inscripciones i
JOIN academico_oltp.secciones s ON i.seccion_id = s.seccion_id
JOIN academico_oltp.periodos_academicos p ON s.periodo_id = p.periodo_id
JOIN academico_oltp.evaluaciones e ON s.seccion_id = e.seccion_id
JOIN academico_oltp.calificaciones c ON i.inscripcion_id = c.inscripcion_id 
                                     AND e.evaluacion_id = c.evaluacion_id
WHERE p.codigo_periodo = '2024-I' 
  AND i.estado_inscripcion = 'FINALIZADO'
GROUP BY i.estudiante_id, p.codigo_periodo, s.seccion_id;

/*Estrategia de Optimización (Índice Compuesto + Parcial)*/

-- 1. Índice parcial en inscripciones para filtrar rápidamente las cursadas finalizadas
CREATE INDEX idx_inscripciones_finalizadas 
ON academico_oltp.inscripciones (seccion_id, estudiante_id, inscripcion_id) 
WHERE estado_inscripcion = 'FINALIZADO';

-- 2. Índice compuesto en calificaciones para agilizar el doble JOIN evaluacion-inscripcion
CREATE INDEX idx_calificaciones_compuesto 
ON academico_oltp.calificaciones (inscripcion_id, evaluacion_id, nota);

/*Sentencia SQL de Prueba 2 */

EXPLAIN (ANALYZE, BUFFERS, COSTS, VERBOSE)
SELECT 
    s.seccion_id,
    m.codigo_materia,
    i.estudiante_id,
    COUNT(a.asistencia_id) AS total_sesiones,
    SUM(CASE WHEN a.estado_asistencia = 'AUSENTE' THEN 1 ELSE 0 END) AS total_faltas
FROM academico_oltp.secciones s
JOIN academico_oltp.materias m ON s.materia_id = m.materia_id
JOIN academico_oltp.inscripciones i ON s.seccion_id = i.seccion_id
JOIN academico_oltp.asistencias a ON i.inscripcion_id = a.inscripcion_id
WHERE s.periodo_id = 4
GROUP BY s.seccion_id, m.codigo_materia, i.estudiante_id
HAVING SUM(CASE WHEN a.estado_asistencia = 'AUSENTE' THEN 1 ELSE 0 END) >= 3;

/*Estrategia de Optimización (Índice B-Tree en Llave Externa y Estado)*/

-- Índice B-Tree para optimizar la agregación por inscripción y estado de asistencia
CREATE INDEX idx_asistencias_inscripcion_estado 
ON academico_oltp.asistencias (inscripcion_id, estado_asistencia);

-- Índice en secciones por periodo para acelerar el primer filtro del WHERE
CREATE INDEX idx_secciones_periodo 
ON academico_oltp.secciones (periodo_id, seccion_id);