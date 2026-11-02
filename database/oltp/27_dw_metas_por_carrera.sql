-- =============================================================================
-- UNIVERSIDAD DE EL SALVADOR - FACULTAD MULTIDISCIPLINARIA ORIENTAL
-- EL ALMACÉN CALCULA Y COMPARA LOS INDICADORES POR CARRERA
-- =============================================================================
-- Continuación del script 26, que permitió metas por carrera en el OLTP. Aquí
-- el almacén aprende a calcular el valor de cada indicador POR CARRERA, además
-- del institucional, y a compararlo contra la meta que corresponda.
--
-- Tres cambios de grano, todos con el mismo criterio: `carrera_id` nulo
-- significa «institucional».
--
--   dw_academico.meta_indicador        NUEVA. Todas las metas (la general y las
--                                      de carrera). dim_indicador conserva la
--                                      institucional en sus columnas `meta` y
--                                      `tolerancia`, que es lo que ya tenía.
--   v_indicador_calculo                pasa a (indicador, período, carrera) con
--                                      GROUPING SETS: una fila por carrera y una
--                                      institucional, en la misma pasada.
--   fact_indicador_periodo             mismo grano. La clave primaria no admite
--                                      nulos, así que se cambia por una única
--                                      con NULLS NOT DISTINCT.
--
-- Trampa que esto evita: el MERGE emparejaba con `=`, y NULL = NULL es NULL, así
-- que las filas institucionales nunca habrían coincidido — el MERGE las habría
-- borrado e insertado en cada carga, para siempre. Se empareja con
-- IS NOT DISTINCT FROM.
--
-- La regla del semáforo: vale la meta de la carrera si existe; si no, la
-- institucional. Así ninguna carrera queda sin meta.
--
-- Idempotente.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Todas las metas en el almacén
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dw_academico.meta_indicador (
    codigo VARCHAR(40) NOT NULL,
    carrera_id INT,                       -- NULL = institucional
    meta NUMERIC(14,4) NOT NULL,
    tolerancia NUMERIC(14,4) NOT NULL,
    justificacion VARCHAR(400) NOT NULL,
    actualizado_en TIMESTAMP WITH TIME ZONE,
    CONSTRAINT uq_dw_meta_indicador UNIQUE NULLS NOT DISTINCT (codigo, carrera_id)
);

COMMENT ON TABLE dw_academico.meta_indicador IS
    'Metas de los indicadores, institucionales (carrera_id NULL) y por carrera. '
    'La recarga completa del ETL la vacía y la vuelve a llenar desde el OLTP.';

-- -----------------------------------------------------------------------------
-- 2. El cálculo, por carrera y total, en una sola pasada
-- -----------------------------------------------------------------------------
-- Se recrean en vez de REPLACE: cambia el orden de las columnas, y
-- CREATE OR REPLACE VIEW solo admite agregarlas al final. El DROP se lleva los
-- permisos, que se vuelven a otorgar en la sección 5.
DROP VIEW IF EXISTS dw_academico.v_indicador_calculo;
CREATE VIEW dw_academico.v_indicador_calculo AS
WITH t AS (
    SELECT p.codigo_periodo, p.orden AS orden_periodo, c.carrera_id,
           COALESCE(SUM(f.costo_reprobacion), 0)                                AS costo_reprobacion,
           COALESCE(SUM(f.costo_reprobacion) FILTER (WHERE f.es_repeticion), 0)  AS costo_repeticion,
           COUNT(*) FILTER (WHERE f.cerrada)                                     AS cerradas,
           COUNT(*) FILTER (WHERE f.reprobado)                                   AS reprobadas,
           COUNT(*) FILTER (WHERE f.retirado)                                    AS retiradas,
           COUNT(DISTINCT f.estudiante_key) FILTER (WHERE f.reprobado)           AS estudiantes_reprobados
    FROM dw_academico.fact_inscripcion f
    JOIN dw_academico.dim_periodo p ON p.periodo_key = f.periodo_key
    JOIN dw_academico.dim_carrera c ON c.carrera_key = f.carrera_key
    -- Una fila por (período, carrera) y otra por período con carrera_id nulo:
    -- la institucional sale del mismo recorrido, no de una segunda consulta.
    GROUP BY GROUPING SETS ((p.codigo_periodo, p.orden, c.carrera_id),
                            (p.codigo_periodo, p.orden))
)
SELECT codigo_periodo, orden_periodo, carrera_id, x.codigo, x.numerador, x.denominador,
       -- Con la misma escala que fact_indicador_periodo.valor: si no, el MERGE
       -- vería distinto un cociente idéntico y reescribiría la fila en cada carga.
       round(CASE WHEN x.denominador IS NULL THEN x.numerador
                  ELSE x.numerador / NULLIF(x.denominador, 0) END, 6) AS valor
FROM t
CROSS JOIN LATERAL (VALUES
    ('costo_reprobacion',     t.costo_reprobacion::numeric,  NULL::numeric),
    ('costo_por_estudiante',  t.costo_reprobacion::numeric,  t.estudiantes_reprobados::numeric),
    ('tasa_reprobacion',      t.reprobadas::numeric,         t.cerradas::numeric),
    ('tasa_retiro',           t.retiradas::numeric,          (t.cerradas + t.retiradas)::numeric),
    ('proporcion_repeticion', t.costo_repeticion::numeric,   t.costo_reprobacion::numeric)
) AS x (codigo, numerador, denominador);

-- -----------------------------------------------------------------------------
-- 3. Los resultados guardados, al nuevo grano
-- -----------------------------------------------------------------------------
ALTER TABLE dw_academico.fact_indicador_periodo
    ADD COLUMN IF NOT EXISTS carrera_id INT;

ALTER TABLE dw_academico.fact_indicador_periodo DROP CONSTRAINT IF EXISTS fact_indicador_periodo_pkey;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conrelid = 'dw_academico.fact_indicador_periodo'::regclass
                     AND conname = 'uq_fact_indicador_periodo') THEN
        ALTER TABLE dw_academico.fact_indicador_periodo ADD CONSTRAINT uq_fact_indicador_periodo
            UNIQUE NULLS NOT DISTINCT (codigo, codigo_periodo, carrera_id);
    END IF;
END $$;

CREATE OR REPLACE FUNCTION dw_academico.actualizar_resultados_indicadores()
RETURNS INT AS $$
DECLARE
    v_filas INT;
BEGIN
    MERGE INTO dw_academico.fact_indicador_periodo AS destino
    USING dw_academico.v_indicador_calculo AS origen
       ON destino.codigo = origen.codigo
      AND destino.codigo_periodo = origen.codigo_periodo
      -- NULL = NULL es NULL: con «=», las filas institucionales no coincidirían
      -- nunca y el MERGE las borraría e insertaría en cada carga.
      AND destino.carrera_id IS NOT DISTINCT FROM origen.carrera_id
    WHEN MATCHED AND (destino.valor IS DISTINCT FROM origen.valor
                      OR destino.numerador IS DISTINCT FROM origen.numerador
                      OR destino.denominador IS DISTINCT FROM origen.denominador
                      OR destino.orden_periodo IS DISTINCT FROM origen.orden_periodo) THEN
        UPDATE SET numerador = origen.numerador, denominador = origen.denominador,
                   valor = origen.valor, orden_periodo = origen.orden_periodo, calculado_en = now()
    WHEN NOT MATCHED BY TARGET THEN
        INSERT (codigo, codigo_periodo, carrera_id, orden_periodo, numerador, denominador, valor)
        VALUES (origen.codigo, origen.codigo_periodo, origen.carrera_id, origen.orden_periodo,
                origen.numerador, origen.denominador, origen.valor)
    WHEN NOT MATCHED BY SOURCE THEN
        DELETE;
    GET DIAGNOSTICS v_filas = ROW_COUNT;
    RETURN v_filas;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, dw_academico;

-- -----------------------------------------------------------------------------
-- 4. El semáforo: la meta de la carrera si existe; si no, la institucional
-- -----------------------------------------------------------------------------
DROP VIEW IF EXISTS dw_academico.v_semaforo_indicador;
CREATE VIEW dw_academico.v_semaforo_indicador AS
SELECT r.codigo, d.nombre, d.unidad, d.sentido, d.perspectiva, d.responsable_cargo,
       r.codigo_periodo, r.orden_periodo, r.carrera_id, r.valor,
       m.meta, m.tolerancia, m.carrera_id IS NOT NULL AS meta_propia,
       CASE
           WHEN r.valor IS NULL OR m.meta IS NULL THEN 'sin_dato'
           WHEN d.sentido = 'menor_mejor' AND r.valor <= m.meta THEN 'favorable'
           WHEN d.sentido = 'menor_mejor' AND r.valor <= m.meta + m.tolerancia THEN 'en_observacion'
           WHEN d.sentido = 'mayor_mejor' AND r.valor >= m.meta THEN 'favorable'
           WHEN d.sentido = 'mayor_mejor' AND r.valor >= m.meta - m.tolerancia THEN 'en_observacion'
           ELSE 'desfavorable'
       END AS estado
FROM dw_academico.fact_indicador_periodo r
JOIN dw_academico.dim_indicador d ON d.codigo = r.codigo
-- La meta propia de la carrera se antepone a la institucional: se piden las dos
-- candidatas y se toma la primera, con las de carrera antes que la general.
LEFT JOIN LATERAL (
    SELECT mi.meta, mi.tolerancia, mi.carrera_id
    FROM dw_academico.meta_indicador mi
    WHERE mi.codigo = r.codigo
      AND (mi.carrera_id = r.carrera_id OR mi.carrera_id IS NULL)
    ORDER BY mi.carrera_id NULLS LAST
    LIMIT 1
) m ON TRUE;

-- -----------------------------------------------------------------------------
-- 5. Permisos: la carga escribe; los tableros solo leen
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rol_dw_carga') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON dw_academico.meta_indicador TO rol_dw_carga;
        GRANT SELECT ON dw_academico.v_indicador_calculo TO rol_dw_carga;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rol_dashboard') THEN
        GRANT SELECT ON dw_academico.meta_indicador TO rol_dashboard;
        GRANT SELECT ON dw_academico.v_indicador_calculo TO rol_dashboard;
        GRANT SELECT ON dw_academico.v_semaforo_indicador TO rol_dashboard;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rol_dw_carrera') THEN
        GRANT SELECT ON dw_academico.meta_indicador TO rol_dw_carrera;
        GRANT SELECT ON dw_academico.v_semaforo_indicador TO rol_dw_carrera;
    END IF;
END
$$;
