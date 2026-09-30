-- =============================================================================
-- UNIVERSIDAD DE EL SALVADOR - FACULTAD MULTIDISCIPLINARIA ORIENTAL
-- COSTO INSTITUCIONAL DE LA REPROBACIÓN, POR MATERIA
-- =============================================================================
-- Responde la pregunta de negocio central del proyecto: cuánto le costó a la
-- institución que los estudiantes reprobaran, en un período dado.
--
-- Junta las tres piezas del sistema: las notas del esquema operacional, la
-- ponderación de cada evaluación, y el catálogo de costos (08_costos_institucionales).
--
-- Es una consulta de demostración para la defensa y para validar la cadena de
-- extremo a extremo ANTES de que exista el Data Warehouse. Cuando el DW esté
-- cargado (SCRUM-35), esta misma pregunta se responde leyendo la tabla de
-- hechos, sin recalcular la nota final aquí.
--
--   docker exec -i -e PGPASSWORD="$POSTGRES_PASSWORD" academico_postgres \
--       psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < scripts/analisis/costo_reprobacion.sql
--
-- Para cambiar de período, edita el valor de :periodo en el WHERE (1 = 2022-I).
-- Ojo: solo los períodos 1 a 3 tienen datos de asistencia, pero las notas
-- existen en todos.
-- =============================================================================

\set periodo 1

-- Nota final ponderada por inscripción.
-- El criterio es el mismo que usa el sistema transaccional en
-- backend/app/routers/reportes.py: suma de (nota x porcentaje) sobre la suma de
-- los porcentajes evaluados. Si las dos versiones se separan, el análisis
-- reportaría reprobados distintos a los que muestra la aplicación.
WITH nota_final AS (
    SELECT
        i.inscripcion_id,
        s.materia_id,
        s.periodo_id,
        ROUND(SUM(c.nota * e.porcentaje) / NULLIF(SUM(e.porcentaje), 0), 2) AS nota
    FROM academico_oltp.inscripciones i
    JOIN academico_oltp.secciones s      ON s.seccion_id = i.seccion_id
    JOIN academico_oltp.evaluaciones e   ON e.seccion_id = s.seccion_id
    JOIN academico_oltp.calificaciones c ON c.inscripcion_id = i.inscripcion_id
                                        AND c.evaluacion_id = e.evaluacion_id
    -- Solo inscripciones cerradas: las que siguen en curso no tienen nota final,
    -- y las retiradas no cuentan como reprobación.
    WHERE i.estado_inscripcion = 'FINALIZADO'
      AND s.periodo_id = :periodo
    GROUP BY i.inscripcion_id, s.materia_id, s.periodo_id
),
reprobadas AS (
    SELECT * FROM nota_final WHERE nota < 6.00
)
SELECT
    v.codigo_materia                                  AS materia,
    count(*)                                          AS reprobados,
    v.unidades_valorativas                            AS uv,
    v.costo_materia                                   AS costo_unitario,
    (count(*) * v.costo_materia)::NUMERIC(12, 2)      AS costo_total_usd
FROM reprobadas r
JOIN academico_oltp.v_costo_materia_periodo v
  ON v.materia_id = r.materia_id
 AND v.periodo_id = r.periodo_id
GROUP BY v.codigo_materia, v.unidades_valorativas, v.costo_materia
ORDER BY costo_total_usd DESC;

-- Resumen del período: tasa de reprobación y costo total.
WITH nota_final AS (
    SELECT
        i.inscripcion_id,
        s.materia_id,
        s.periodo_id,
        ROUND(SUM(c.nota * e.porcentaje) / NULLIF(SUM(e.porcentaje), 0), 2) AS nota
    FROM academico_oltp.inscripciones i
    JOIN academico_oltp.secciones s      ON s.seccion_id = i.seccion_id
    JOIN academico_oltp.evaluaciones e   ON e.seccion_id = s.seccion_id
    JOIN academico_oltp.calificaciones c ON c.inscripcion_id = i.inscripcion_id
                                        AND c.evaluacion_id = e.evaluacion_id
    WHERE i.estado_inscripcion = 'FINALIZADO'
      AND s.periodo_id = :periodo
    GROUP BY i.inscripcion_id, s.materia_id, s.periodo_id
)
SELECT
    p.codigo_periodo                                                          AS periodo,
    count(*)                                                                  AS inscripciones_cerradas,
    count(*) FILTER (WHERE nf.nota < 6.00)                                    AS reprobadas,
    ROUND(100.0 * count(*) FILTER (WHERE nf.nota < 6.00) / count(*), 1)       AS tasa_reprobacion_pct,
    SUM(CASE WHEN nf.nota < 6.00 THEN v.costo_materia ELSE 0 END)::NUMERIC(12, 2) AS costo_total_usd
FROM nota_final nf
JOIN academico_oltp.v_costo_materia_periodo v
  ON v.materia_id = nf.materia_id AND v.periodo_id = nf.periodo_id
JOIN academico_oltp.periodos_academicos p
  ON p.periodo_id = nf.periodo_id
GROUP BY p.codigo_periodo;
