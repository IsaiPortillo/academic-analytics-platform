-- =============================================================================
-- UNIVERSIDAD DE EL SALVADOR - FACULTAD MULTIDISCIPLINARIA ORIENTAL
-- CURSO DE ESPECIALIZACIÓN: ADMINISTRACIÓN DE BASES DE DATOS E INTELIGENCIA DE NEGOCIOS
-- FASE 4 - PUNTO 4.2: ATRIBUTOS DEL ANÁLISIS DIAGNÓSTICO EN EL DATA WAREHOUSE
-- =============================================================================
-- Agrega al modelo dimensional (script 10) lo que el análisis diagnóstico
-- necesita para segmentar y para identificar el patrón de riesgo:
--
--   dim_materia.area              área de conocimiento. Solo existe en el grafo
--                                 curricular de Neo4j; el ETL la cruza.
--   fact_inscripcion.turno        turno de la sección (MATUTINO, VESPERTINO,
--                                 NOCTURNO). Atributo degenerado: una dimensión
--                                 de sección para un solo atributo no se justifica.
--   fact_inscripcion.patron_riesgo  nota final < 6.00 Y 3 o más ausencias: los
--                                 umbrales del sistema transaccional
--                                 (backend/app/calculos.py), calculados por el ETL.
--
-- Es una migración aparte, y no una edición del script 10, para que se pueda
-- aplicar sobre un DW que ya existe sin recrearlo. ADD COLUMN IF NOT EXISTS la
-- hace idempotente. En una base ya inicializada:
--   docker exec -i academico_postgres psql -U postgres -d academico_db \
--       < database/oltp/12_dw_diagnostico.sql
-- y luego recargar: python -m etl.carga
-- =============================================================================

ALTER TABLE dw_academico.dim_materia
    ADD COLUMN IF NOT EXISTS area VARCHAR(60);

ALTER TABLE dw_academico.fact_inscripcion
    ADD COLUMN IF NOT EXISTS turno VARCHAR(15),
    ADD COLUMN IF NOT EXISTS patron_riesgo BOOLEAN NOT NULL DEFAULT FALSE;

-- El patrón solo puede darse en una inscripción reprobada. Si el ETL marcara
-- otra cosa, la carga falla en vez de publicar un dato incoherente.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_patron_riesgo_reprobado'
    ) THEN
        ALTER TABLE dw_academico.fact_inscripcion
            ADD CONSTRAINT chk_patron_riesgo_reprobado
            CHECK (NOT patron_riesgo OR (reprobado AND ausentes >= 3));
    END IF;
END
$$;

-- Segmentaciones frecuentes del análisis diagnóstico.
CREATE INDEX IF NOT EXISTS idx_fact_patron_riesgo
    ON dw_academico.fact_inscripcion (estudiante_key) WHERE patron_riesgo;
