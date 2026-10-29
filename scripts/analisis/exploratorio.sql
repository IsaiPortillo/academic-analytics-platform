-- =============================================================================
-- UNIVERSIDAD DE EL SALVADOR - FACULTAD MULTIDISCIPLINARIA ORIENTAL
-- ANÁLISIS DESCRIPTIVO Y EXPLORATORIO DEL COSTO DE REPROBACIÓN
-- =============================================================================
-- Cinco análisis sobre el Data Warehouse, en el orden en que conviene leerlos:
--
--   1. Resumen de cinco números del costo por estudiante
--   2. Histograma de esa misma distribución
--   3. Valores atípicos por el criterio del rango intercuartílico
--   4. Análisis de Pareto por asignatura
--   5. Comparación temporal con media móvil de tres ciclos
--
-- Todo se calcula EN PostgreSQL. No es una preferencia de estilo: el motor tiene
-- percentile_cont, width_bucket y funciones de ventana, de modo que traer 36.704
-- filas a Python para recorrerlas en un bucle sería más lento y además alejaría
-- el cálculo de los datos.
--
-- Sobre la variable elegida. El resumen, el histograma y los atípicos se hacen
-- sobre el COSTO ACUMULADO POR ESTUDIANTE y no sobre la nota, por dos razones:
-- es la variable del problema de negocio, y tiene una distribución asimétrica
-- que es justo donde el promedio engaña y el análisis exploratorio aporta.
--
--   docker exec -i -e PGPASSWORD="$POSTGRES_PASSWORD" academico_postgres \
--       psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" < scripts/analisis/exploratorio.sql
--
-- Los datos son sintéticos y el costo por unidad valorativa es un supuesto
-- paramétrico: lo que se demuestra es el método, no la magnitud.
-- =============================================================================

\pset border 2
\timing off

-- -----------------------------------------------------------------------------
-- 1. RESUMEN DE CINCO NÚMEROS
-- -----------------------------------------------------------------------------
-- Mínimo, primer cuartil, mediana, tercer cuartil y máximo. Se acompañan de la
-- media y la desviación estándar precisamente para poder compararlas: cuando la
-- media supera con holgura a la mediana, la distribución está sesgada a la
-- derecha y resumirla con el promedio es engañoso.
\echo '== 1. Resumen de cinco números: costo de reprobación acumulado por estudiante =='

WITH por_estudiante AS (
    SELECT f.estudiante_key,
           SUM(f.costo_reprobacion) AS costo
    FROM dw_academico.fact_inscripcion f
    GROUP BY f.estudiante_key
    HAVING SUM(f.costo_reprobacion) > 0   -- solo quienes reprobaron algo
)
SELECT
    count(*)                                                             AS estudiantes,
    MIN(costo)                                                           AS minimo,
    percentile_cont(0.25) WITHIN GROUP (ORDER BY costo)::numeric(12,2)   AS q1,
    percentile_cont(0.50) WITHIN GROUP (ORDER BY costo)::numeric(12,2)   AS mediana,
    percentile_cont(0.75) WITHIN GROUP (ORDER BY costo)::numeric(12,2)   AS q3,
    MAX(costo)                                                           AS maximo,
    AVG(costo)::numeric(12,2)                                            AS media,
    STDDEV_SAMP(costo)::numeric(12,2)                                    AS desviacion
FROM por_estudiante;

-- -----------------------------------------------------------------------------
-- 2. HISTOGRAMA
-- -----------------------------------------------------------------------------
-- width_bucket reparte cada valor en uno de diez tramos de igual amplitud entre
-- el mínimo y el máximo. La barra de bloques hace visible la forma sin salir de
-- la terminal, que es donde se demuestra.
\echo ''
\echo '== 2. Histograma del costo por estudiante (10 tramos de igual amplitud) =='

WITH por_estudiante AS (
    SELECT f.estudiante_key, SUM(f.costo_reprobacion) AS costo
    FROM dw_academico.fact_inscripcion f
    GROUP BY f.estudiante_key
    HAVING SUM(f.costo_reprobacion) > 0
),
limites AS (
    SELECT MIN(costo) AS lo, MAX(costo) AS hi FROM por_estudiante
),
tramos AS (
    SELECT width_bucket(p.costo, l.lo, l.hi + 0.01, 10) AS tramo,
           count(*) AS estudiantes
    FROM por_estudiante p CROSS JOIN limites l
    GROUP BY 1
)
SELECT
    t.tramo,
    '[' || ROUND(l.lo + (t.tramo - 1) * (l.hi - l.lo) / 10.0)::text ||
    ' – ' || ROUND(l.lo + t.tramo * (l.hi - l.lo) / 10.0)::text || ')'        AS rango_usd,
    t.estudiantes,
    ROUND(100.0 * t.estudiantes / SUM(t.estudiantes) OVER (), 1)              AS pct,
    repeat('#', GREATEST(1, (60.0 * t.estudiantes
                             / MAX(t.estudiantes) OVER ())::int))             AS forma
FROM tramos t CROSS JOIN limites l
ORDER BY t.tramo;

-- -----------------------------------------------------------------------------
-- 3. VALORES ATÍPICOS POR EL RANGO INTERCUARTÍLICO
-- -----------------------------------------------------------------------------
-- Criterio de Tukey: es atípico lo que queda fuera de [Q1 - 1,5·RIC, Q3 + 1,5·RIC].
-- Se usa este criterio y no "más de dos desviaciones estándar" porque los
-- cuartiles no se dejan arrastrar por los propios valores extremos, que es
-- exactamente lo que se quiere detectar.
\echo ''
\echo '== 3. Valores atípicos (criterio del rango intercuartílico) =='

WITH por_estudiante AS (
    SELECT f.estudiante_key, SUM(f.costo_reprobacion) AS costo,
           count(*) FILTER (WHERE f.reprobado) AS materias_reprobadas
    FROM dw_academico.fact_inscripcion f
    GROUP BY f.estudiante_key
    HAVING SUM(f.costo_reprobacion) > 0
),
cuartiles AS (
    SELECT percentile_cont(0.25) WITHIN GROUP (ORDER BY costo) AS q1,
           percentile_cont(0.75) WITHIN GROUP (ORDER BY costo) AS q3
    FROM por_estudiante
),
cercos AS (
    SELECT q1, q3, (q3 - q1) AS ric,
           q1 - 1.5 * (q3 - q1) AS cerco_bajo,
           q3 + 1.5 * (q3 - q1) AS cerco_alto
    FROM cuartiles
)
SELECT
    c.ric::numeric(12,2)                                                  AS rango_intercuartilico,
    c.cerco_alto::numeric(12,2)                                           AS cerco_superior,
    count(*) FILTER (WHERE p.costo > c.cerco_alto)                        AS atipicos_altos,
    count(*) FILTER (WHERE p.costo < c.cerco_bajo)                        AS atipicos_bajos,
    ROUND(100.0 * count(*) FILTER (WHERE p.costo > c.cerco_alto) / count(*), 2)
                                                                          AS pct_atipicos_altos,
    SUM(p.costo) FILTER (WHERE p.costo > c.cerco_alto)::numeric(14,2)     AS costo_de_los_atipicos,
    ROUND(100.0 * COALESCE(SUM(p.costo) FILTER (WHERE p.costo > c.cerco_alto), 0)
          / SUM(p.costo), 1)                                              AS pct_del_costo_total
FROM por_estudiante p CROSS JOIN cercos c
GROUP BY c.ric, c.cerco_alto;

\echo ''
\echo '-- Los diez casos más extremos, para poder interpretarlos --'

WITH por_estudiante AS (
    SELECT f.estudiante_key, SUM(f.costo_reprobacion) AS costo,
           count(*) FILTER (WHERE f.reprobado)     AS materias_reprobadas,
           count(*) FILTER (WHERE f.es_repeticion) AS repeticiones
    FROM dw_academico.fact_inscripcion f
    GROUP BY f.estudiante_key
    HAVING SUM(f.costo_reprobacion) > 0
),
cercos AS (
    SELECT percentile_cont(0.75) WITHIN GROUP (ORDER BY costo)
           + 1.5 * (percentile_cont(0.75) WITHIN GROUP (ORDER BY costo)
                    - percentile_cont(0.25) WITHIN GROUP (ORDER BY costo)) AS cerco_alto
    FROM por_estudiante
)
SELECT e.carnet_hash                      AS estudiante_anonimizado,
       p.costo::numeric(12,2)             AS costo_usd,
       p.materias_reprobadas,
       p.repeticiones
FROM por_estudiante p
JOIN dw_academico.dim_estudiante e USING (estudiante_key)
CROSS JOIN cercos c
WHERE p.costo > c.cerco_alto
ORDER BY p.costo DESC
LIMIT 10;

-- -----------------------------------------------------------------------------
-- 4. ANÁLISIS DE PARETO POR ASIGNATURA
-- -----------------------------------------------------------------------------
-- ¿Se concentra el costo en unas pocas asignaturas? La columna acumulada usa una
-- función de ventana; la última columna marca dónde se cruza el 80 %, que es la
-- lectura clásica del principio de Pareto.
\echo ''
\echo '== 4. Pareto: concentración del costo de reprobación por asignatura =='

WITH por_materia AS (
    SELECT m.codigo_materia,
           m.nombre_materia,
           m.es_cuello_botella,
           SUM(f.costo_reprobacion) AS costo
    FROM dw_academico.fact_inscripcion f
    JOIN dw_academico.dim_materia m USING (materia_key)
    GROUP BY m.codigo_materia, m.nombre_materia, m.es_cuello_botella
    HAVING SUM(f.costo_reprobacion) > 0
),
ordenado AS (
    SELECT *,
           SUM(costo) OVER ()                                   AS total,
           SUM(costo) OVER (ORDER BY costo DESC
                            ROWS BETWEEN UNBOUNDED PRECEDING
                                     AND CURRENT ROW)           AS acumulado,
           ROW_NUMBER() OVER (ORDER BY costo DESC)              AS puesto,
           count(*) OVER ()                                     AS materias
    FROM por_materia
)
SELECT puesto,
       codigo_materia,
       left(nombre_materia, 28)                        AS materia,
       CASE WHEN es_cuello_botella THEN 'sí' END       AS cuello_botella,
       costo::numeric(14,2)                            AS costo_usd,
       ROUND(100.0 * costo / total, 1)                 AS pct,
       ROUND(100.0 * acumulado / total, 1)             AS pct_acumulado,
       ROUND(100.0 * puesto / materias, 0)             AS pct_de_materias,
       CASE WHEN 100.0 * acumulado / total <= 80 THEN '<= 80 %' END AS dentro_del_80
FROM ordenado
ORDER BY puesto;

-- -----------------------------------------------------------------------------
-- 5. COMPARACIÓN TEMPORAL CON MEDIA MÓVIL
-- -----------------------------------------------------------------------------
-- La media móvil de tres ciclos suaviza el ruido y deja ver la tendencia.
--
-- OJO con la tasa: la media móvil del COSTO puede calcularse promediando los
-- costos, porque el costo es aditivo. La de la TASA no: promediar las tasas de
-- tres ciclos sería un promedio de promedios. Se calcula dividiendo la suma de
-- los numeradores entre la suma de los denominadores dentro de la ventana, que
-- es la forma correcta de agregar una razón.
\echo ''
\echo '== 5. Evolución por ciclo con media móvil de tres ciclos =='

WITH por_periodo AS (
    SELECT p.codigo_periodo,
           p.orden,
           SUM(f.costo_reprobacion)                   AS costo,
           count(*) FILTER (WHERE f.reprobado)        AS reprobadas,
           count(*) FILTER (WHERE f.cerrada)          AS cerradas
    FROM dw_academico.fact_inscripcion f
    JOIN dw_academico.dim_periodo p USING (periodo_key)
    GROUP BY p.codigo_periodo, p.orden
)
SELECT
    codigo_periodo                                              AS ciclo,
    costo::numeric(14,2)                                        AS costo_usd,
    AVG(costo) OVER (ORDER BY orden
                     ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)::numeric(14,2)
                                                                AS costo_media_movil_3,
    ROUND(100.0 * reprobadas / NULLIF(cerradas, 0), 1)           AS tasa_pct,
    -- Agregación correcta de una razón: suma de numeradores sobre suma de
    -- denominadores dentro de la ventana, nunca el promedio de las tasas.
    ROUND(100.0 * SUM(reprobadas) OVER (ORDER BY orden
                                        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)
          / NULLIF(SUM(cerradas) OVER (ORDER BY orden
                                       ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 0), 1)
                                                                AS tasa_media_movil_3,
    -- Variación contra el ciclo anterior, para leer el salto puntual.
    ROUND(100.0 * (costo - LAG(costo) OVER (ORDER BY orden))
          / NULLIF(LAG(costo) OVER (ORDER BY orden), 0), 1)      AS var_costo_pct
FROM por_periodo
ORDER BY orden;
