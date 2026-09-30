-- =============================================================================
-- UNIVERSIDAD DE EL SALVADOR - FACULTAD MULTIDISCIPLINARIA ORIENTAL
-- CURSO DE ESPECIALIZACIÓN: ADMINISTRACIÓN DE BASES DE DATOS E INTELIGENCIA DE NEGOCIOS
-- FASE 3 - PUNTO 3.0: COSTOS INSTITUCIONALES
-- =============================================================================
-- Registra cuánto le cuesta a la institución impartir una unidad valorativa en
-- cada período académico. De aquí sale la medida monetaria del Data Warehouse:
-- lo que la universidad invierte en una materia que el estudiante reprueba.
--
-- Por qué esta tabla vive en el esquema OPERACIONAL y no directamente en el
-- Data Warehouse: es dato institucional de referencia que alguien mantiene en
-- el tiempo, el OLTP es la fuente de la verdad de la que el ETL lee todo lo
-- demás, y el coordinador tiene razón legítima para consultarlo desde el
-- sistema transaccional.
-- =============================================================================

SET search_path TO academico_oltp, public;

-- -----------------------------------------------------------------------------
-- 1. COSTO POR UNIDAD VALORATIVA, POR PERÍODO
-- -----------------------------------------------------------------------------
-- El costo se asocia al período y no a la materia porque el presupuesto cambia
-- cada año: una misma materia cuesta distinto en 2026-I que en 2027-I. La
-- diferencia entre materias ya la aporta `materias.unidades_valorativas`.
CREATE TABLE academico_oltp.costos_uv (
    costo_uv_id SERIAL PRIMARY KEY,
    periodo_id INT NOT NULL,
    costo_por_uv NUMERIC(10, 2) NOT NULL CHECK (costo_por_uv > 0),
    moneda CHAR(3) NOT NULL DEFAULT 'USD',
    -- De dónde sale la cifra. No es documentación decorativa: es lo que permite
    -- sustentarla ante el jurado. Una cifra sin fuente verificable se declara
    -- como supuesto y se dice que lo es; no se presenta como dato oficial.
    fuente VARCHAR(200) NOT NULL,
    registrado_en TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- Un solo costo vigente por período: evita ambigüedad al calcular la medida.
    CONSTRAINT uq_costo_periodo UNIQUE (periodo_id),
    CONSTRAINT fk_costo_periodo FOREIGN KEY (periodo_id)
        REFERENCES academico_oltp.periodos_academicos (periodo_id) ON DELETE RESTRICT
);

COMMENT ON TABLE academico_oltp.costos_uv IS
    'Costo institucional por unidad valorativa en cada período académico. Base del cálculo de costo de reprobación (Fase 3).';
COMMENT ON COLUMN academico_oltp.costos_uv.fuente IS
    'Origen de la cifra. Si no procede de un documento oficial, debe indicar explícitamente que es un supuesto paramétrico.';

-- -----------------------------------------------------------------------------
-- 2. VISTA DEL COSTO BASE POR MATERIA Y PERÍODO
-- -----------------------------------------------------------------------------
-- El cálculo base en un solo lugar, para que el ETL (SCRUM-34) y la aplicación
-- no escriban cada uno su versión de la misma multiplicación.
--
-- Deliberadamente NO incluye la condición de aprobación: determinar si una
-- inscripción está reprobada exige la nota final ponderada por
-- `evaluaciones.porcentaje`, lógica que ya vive en el backend
-- (backend/app/routers/reportes.py). Duplicarla aquí en SQL abriría la puerta a
-- que las dos versiones se separen y el dashboard reporte reprobados distintos
-- a los del sistema transaccional.
CREATE VIEW academico_oltp.v_costo_materia_periodo AS
SELECT
    m.materia_id,
    m.codigo_materia,
    p.periodo_id,
    p.codigo_periodo,
    m.unidades_valorativas,
    c.costo_por_uv,
    c.moneda,
    (m.unidades_valorativas * c.costo_por_uv)::NUMERIC(12, 2) AS costo_materia
FROM academico_oltp.materias m
CROSS JOIN academico_oltp.periodos_academicos p
JOIN academico_oltp.costos_uv c ON c.periodo_id = p.periodo_id;

COMMENT ON VIEW academico_oltp.v_costo_materia_periodo IS
    'Costo de impartir cada materia en cada período: unidades valorativas x costo por UV.';

-- -----------------------------------------------------------------------------
-- 3. PERMISOS
-- -----------------------------------------------------------------------------
-- El GRANT ... ON ALL TABLES IN SCHEMA del script 01 solo afectó a las tablas
-- que existían en ese momento, así que hay que conceder los de esta tabla aquí.
-- El coordinador administra las cifras; docente y ETL solo las leen.
GRANT SELECT, INSERT, UPDATE, DELETE ON academico_oltp.costos_uv TO rol_coordinador;
GRANT USAGE, SELECT ON SEQUENCE academico_oltp.costos_uv_costo_uv_id_seq TO rol_coordinador;

GRANT SELECT ON academico_oltp.costos_uv TO rol_docente;
GRANT SELECT ON academico_oltp.costos_uv TO rol_etl;

GRANT SELECT ON academico_oltp.v_costo_materia_periodo TO rol_coordinador;
GRANT SELECT ON academico_oltp.v_costo_materia_periodo TO rol_docente;
GRANT SELECT ON academico_oltp.v_costo_materia_periodo TO rol_etl;

-- -----------------------------------------------------------------------------
-- 4. SIEMBRA DE DATOS
-- -----------------------------------------------------------------------------
-- ⚠️ SUPUESTO PARAMÉTRICO, NO CIFRA OFICIAL.
--
-- El valor de abajo es un marcador de posición para que el modelo sea
-- ejecutable de extremo a extremo. NO procede de un documento presupuestario de
-- la UES. Antes de la defensa hay dos caminos, y ambos son defendibles:
--
--   a) Sustituirlo por la cifra oficial y citarla en la columna `fuente`.
--   b) Mantenerlo y declararlo como supuesto paramétrico en la memoria,
--      explicando el criterio con que se eligió.
--
-- Lo que no es defendible es presentar este número como dato institucional.
-- Cambiar el valor no obliga a rehacer nada: el modelo dimensional y los KPIs
-- se recalculan solos.
--
-- Idempotente: se puede re-ejecutar y cubre los períodos que se agreguen luego.
INSERT INTO academico_oltp.costos_uv (periodo_id, costo_por_uv, moneda, fuente)
SELECT
    p.periodo_id,
    25.00,
    'USD',
    'SUPUESTO PARAMETRICO - pendiente de sustituir por cifra presupuestaria oficial'
FROM academico_oltp.periodos_academicos p
ON CONFLICT (periodo_id) DO NOTHING;
