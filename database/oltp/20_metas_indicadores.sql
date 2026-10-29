-- =============================================================================
-- UNIVERSIDAD DE EL SALVADOR - FACULTAD MULTIDISCIPLINARIA ORIENTAL
-- INDICADORES, METAS Y SEMÁFORO (actividad evaluada de la Unidad 7, punto e)
-- =============================================================================
-- Recorrido, igual que el costo por UV (script 08):
--   1. academico_oltp.indicadores        catálogo de los cinco KPIs (sentido,
--      academico_oltp.metas_indicador    perspectiva del CMI, responsable por
--                                        cargo) y su meta con banda de tolerancia.
--                                        La edita el coordinador en la app.
--   2. El ETL la lleva a dw_academico.dim_indicador en cada carga.
--   3. dw_academico.v_indicador_calculo  vista de cálculo: el valor de cada KPI
--                                        por período, desde fact_inscripcion.
--   4. dw_academico.fact_indicador_periodo  resultados guardados; la carga los
--                                        mantiene con un MERGE idempotente
--                                        (correrla dos veces deja lo mismo).
--   5. dw_academico.v_semaforo_indicador estado frente a la meta:
--        favorable        el valor cumple la meta
--        en_observacion   no la cumple, pero está dentro de la tolerancia
--        desfavorable     fuera de la tolerancia
--
-- Las metas iniciales son una PROPUESTA calculada sobre los datos sintéticos
-- (valores 2022-I a 2025-II); se reemplazan por las definidas en la memoria.
-- Idempotente.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. OLTP: catálogo y metas
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS academico_oltp.indicadores (
    codigo VARCHAR(40) PRIMARY KEY,
    nombre VARCHAR(120) NOT NULL,
    definicion VARCHAR(300) NOT NULL,
    unidad VARCHAR(12) NOT NULL CHECK (unidad IN ('porcentaje', 'dinero')),
    sentido VARCHAR(12) NOT NULL CHECK (sentido IN ('menor_mejor', 'mayor_mejor')),
    perspectiva VARCHAR(40) NOT NULL CHECK (perspectiva IN
        ('Financiera', 'Estudiantes', 'Procesos internos', 'Aprendizaje y crecimiento')),
    responsable_cargo VARCHAR(80) NOT NULL,
    -- La meta de un indicador en dinero es por período; sumar períodos no se
    -- compara contra ella.
    meta_por_periodo BOOLEAN NOT NULL DEFAULT FALSE,
    orden INT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS academico_oltp.metas_indicador (
    codigo VARCHAR(40) PRIMARY KEY REFERENCES academico_oltp.indicadores (codigo) ON DELETE CASCADE,
    meta NUMERIC(14,4) NOT NULL CHECK (meta >= 0),
    tolerancia NUMERIC(14,4) NOT NULL CHECK (tolerancia >= 0),
    justificacion VARCHAR(400) NOT NULL CHECK (length(btrim(justificacion)) >= 10),
    actualizado_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actualizado_por VARCHAR(50)
);

INSERT INTO academico_oltp.indicadores
    (codigo, nombre, definicion, unidad, sentido, perspectiva, responsable_cargo, meta_por_periodo, orden)
VALUES
    ('costo_reprobacion', 'Costo de reprobación',
     'Suma de UV × costo por UV de las inscripciones que terminaron reprobadas.',
     'dinero', 'menor_mejor', 'Financiera', 'Jefatura de Administración Financiera', TRUE, 1),
    ('costo_por_estudiante', 'Costo por estudiante que reprobó',
     'Costo de reprobación ÷ estudiantes que reprobaron al menos una materia.',
     'dinero', 'menor_mejor', 'Financiera', 'Jefatura de Administración Financiera', FALSE, 2),
    ('tasa_reprobacion', 'Tasa de reprobación',
     'Inscripciones reprobadas ÷ inscripciones con nota final.',
     'porcentaje', 'menor_mejor', 'Estudiantes', 'Coordinación de carrera', FALSE, 3),
    ('tasa_retiro', 'Tasa de retiro',
     'Retiros ÷ inscripciones con desenlace definitivo (con nota final + retiradas).',
     'porcentaje', 'menor_mejor', 'Estudiantes', 'Coordinación de carrera', FALSE, 4),
    ('proporcion_repeticion', 'Costo atribuible a repetición',
     'Costo de reprobación en segundo intento o más ÷ costo de reprobación total.',
     'porcentaje', 'menor_mejor', 'Procesos internos', 'Coordinación académica', FALSE, 5)
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO academico_oltp.metas_indicador (codigo, meta, tolerancia, justificacion, actualizado_por)
VALUES
    ('costo_reprobacion', 90000, 10000,
     'Propuesta inicial: 10 % por debajo del promedio por período (≈ USD 100 000); tolerancia hasta el promedio actual.', 'script 20'),
    ('costo_por_estudiante', 130, 15,
     'Propuesta inicial: por debajo del promedio observado (≈ USD 141); tolerancia de USD 15.', 'script 20'),
    ('tasa_reprobacion', 0.22, 0.03,
     'Propuesta inicial: 2 puntos por debajo de la tasa histórica (24 %); tolerancia de 3 puntos.', 'script 20'),
    ('tasa_retiro', 0.05, 0.01,
     'Propuesta inicial: 5 %, cerca del promedio histórico (5,3 %); tolerancia de 1 punto.', 'script 20'),
    ('proporcion_repeticion', 0.20, 0.03,
     'Propuesta inicial: reducir el peso de la repetición desde ≈ 22,6 %; tolerancia de 3 puntos.', 'script 20')
ON CONFLICT (codigo) DO NOTHING;

GRANT SELECT ON academico_oltp.indicadores TO rol_coordinador, rol_etl;
-- El coordinador ajusta a quién se le asigna y en qué perspectiva va; no las fórmulas.
GRANT UPDATE (perspectiva, responsable_cargo) ON academico_oltp.indicadores TO rol_coordinador;
GRANT SELECT, INSERT, UPDATE ON academico_oltp.metas_indicador TO rol_coordinador;
GRANT SELECT ON academico_oltp.metas_indicador TO rol_etl;

-- -----------------------------------------------------------------------------
-- 2. DW: dimensión de indicadores (la recarga completa del ETL la vacía y la llena)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dw_academico.dim_indicador (
    codigo VARCHAR(40) PRIMARY KEY,
    nombre VARCHAR(120) NOT NULL,
    definicion VARCHAR(300) NOT NULL,
    unidad VARCHAR(12) NOT NULL,
    sentido VARCHAR(12) NOT NULL,
    perspectiva VARCHAR(40) NOT NULL,
    responsable_cargo VARCHAR(80) NOT NULL,
    meta_por_periodo BOOLEAN NOT NULL,
    orden INT NOT NULL,
    meta NUMERIC(14,4),
    tolerancia NUMERIC(14,4),
    justificacion VARCHAR(400),
    meta_actualizada_en TIMESTAMP WITH TIME ZONE
);

-- -----------------------------------------------------------------------------
-- 3. Vista de cálculo: las mismas fórmulas que app/indicadores.py
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW dw_academico.v_indicador_calculo AS
WITH t AS (
    SELECT p.codigo_periodo, p.orden AS orden_periodo,
           COALESCE(SUM(f.costo_reprobacion), 0)                               AS costo_reprobacion,
           COALESCE(SUM(f.costo_reprobacion) FILTER (WHERE f.es_repeticion), 0) AS costo_repeticion,
           COUNT(*) FILTER (WHERE f.cerrada)                                    AS cerradas,
           COUNT(*) FILTER (WHERE f.reprobado)                                  AS reprobadas,
           COUNT(*) FILTER (WHERE f.retirado)                                   AS retiradas,
           COUNT(DISTINCT f.estudiante_key) FILTER (WHERE f.reprobado)          AS estudiantes_reprobados
    FROM dw_academico.fact_inscripcion f
    JOIN dw_academico.dim_periodo p ON p.periodo_key = f.periodo_key
    GROUP BY p.codigo_periodo, p.orden
)
SELECT codigo_periodo, orden_periodo, x.codigo, x.numerador, x.denominador,
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
-- 4. Resultados por período, mantenidos con MERGE. Clave natural (código del
--    período), no periodo_key: las llaves sustitutas se regeneran en cada carga.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dw_academico.fact_indicador_periodo (
    codigo VARCHAR(40) NOT NULL,
    codigo_periodo VARCHAR(10) NOT NULL,
    orden_periodo INT NOT NULL,
    numerador NUMERIC(18,4),
    denominador NUMERIC(18,4),
    valor NUMERIC(18,6),
    calculado_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (codigo, codigo_periodo)
);

-- La carga llama a esta función al final de su transacción. Correrla dos veces
-- seguidas no cambia nada (salvo calculado_en de las filas cuyo valor cambió).
CREATE OR REPLACE FUNCTION dw_academico.actualizar_resultados_indicadores()
RETURNS INT AS $$
DECLARE
    v_filas INT;
BEGIN
    MERGE INTO dw_academico.fact_indicador_periodo AS destino
    USING dw_academico.v_indicador_calculo AS origen
       ON destino.codigo = origen.codigo AND destino.codigo_periodo = origen.codigo_periodo
    WHEN MATCHED AND (destino.valor IS DISTINCT FROM origen.valor
                      OR destino.numerador IS DISTINCT FROM origen.numerador
                      OR destino.denominador IS DISTINCT FROM origen.denominador
                      OR destino.orden_periodo IS DISTINCT FROM origen.orden_periodo) THEN
        UPDATE SET numerador = origen.numerador, denominador = origen.denominador,
                   valor = origen.valor, orden_periodo = origen.orden_periodo, calculado_en = now()
    WHEN NOT MATCHED BY TARGET THEN
        INSERT (codigo, codigo_periodo, orden_periodo, numerador, denominador, valor)
        VALUES (origen.codigo, origen.codigo_periodo, origen.orden_periodo,
                origen.numerador, origen.denominador, origen.valor)
    WHEN NOT MATCHED BY SOURCE THEN
        DELETE;
    GET DIAGNOSTICS v_filas = ROW_COUNT;
    RETURN v_filas;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, dw_academico;

-- -----------------------------------------------------------------------------
-- 5. Semáforo
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW dw_academico.v_semaforo_indicador AS
SELECT r.codigo, d.nombre, d.unidad, d.sentido, d.perspectiva, d.responsable_cargo,
       r.codigo_periodo, r.orden_periodo, r.valor, d.meta, d.tolerancia,
       CASE
           WHEN r.valor IS NULL OR d.meta IS NULL THEN 'sin_dato'
           WHEN d.sentido = 'menor_mejor' AND r.valor <= d.meta THEN 'favorable'
           WHEN d.sentido = 'menor_mejor' AND r.valor <= d.meta + d.tolerancia THEN 'en_observacion'
           WHEN d.sentido = 'mayor_mejor' AND r.valor >= d.meta THEN 'favorable'
           WHEN d.sentido = 'mayor_mejor' AND r.valor >= d.meta - d.tolerancia THEN 'en_observacion'
           ELSE 'desfavorable'
       END AS estado
FROM dw_academico.fact_indicador_periodo r
JOIN dw_academico.dim_indicador d ON d.codigo = r.codigo;

-- -----------------------------------------------------------------------------
-- Permisos: la carga escribe; el tablero solo lee.
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rol_dw_carga') THEN
        GRANT INSERT, TRUNCATE ON dw_academico.dim_indicador TO rol_dw_carga;
        -- MERGE necesita leer el destino para emparejar filas.
        GRANT SELECT, INSERT, UPDATE, DELETE ON dw_academico.fact_indicador_periodo TO rol_dw_carga;
        GRANT EXECUTE ON FUNCTION dw_academico.actualizar_resultados_indicadores() TO rol_dw_carga;
        GRANT SELECT ON dw_academico.v_indicador_calculo TO rol_dw_carga;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rol_dashboard') THEN
        GRANT SELECT ON dw_academico.dim_indicador, dw_academico.fact_indicador_periodo,
                        dw_academico.v_indicador_calculo, dw_academico.v_semaforo_indicador TO rol_dashboard;
    END IF;
END
$$;
REVOKE ALL ON FUNCTION dw_academico.actualizar_resultados_indicadores() FROM PUBLIC;
