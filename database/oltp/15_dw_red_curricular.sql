
-- =============================================================================
-- UNIVERSIDAD DE EL SALVADOR - FACULTAD MULTIDISCIPLINARIA ORIENTAL
-- CURSO DE ESPECIALIZACIÓN: ADMINISTRACIÓN DE BASES DE DATOS E INTELIGENCIA DE NEGOCIOS
-- FASE 4 - PUNTO 4.3 (SCRUM-46): RED CURRICULAR EN EL DATA WAREHOUSE
-- =============================================================================
-- dim_materia ya guarda, desde SCRUM-35, las MÉTRICAS del grafo de Neo4j
-- (dependientes directos, indirectos, índice de bloqueo, cuello de botella).
-- Faltaba la ESTRUCTURA: qué materia exige a cuál. Sin ella no se puede dibujar
-- la red ni recalcular las métricas para comprobarlas.
--
-- Por qué en el DW y no consultando Neo4j desde la web: el dashboard solo puede
-- leer dw_academico (rol_dashboard) y Neo4j Community no tiene roles de solo
-- lectura. La red entra al DW por el mismo camino que el resto, el ETL, y la
-- pantalla no necesita ninguna credencial del grafo.
--
-- Es una migración aparte para poder aplicarla sobre un DW que ya existe sin
-- recrearlo, y es idempotente. Después de aplicarla hay que recargar el DW
-- (`python -m etl.carga`) para que la tabla se llene desde Neo4j.
--
-- En una base ya inicializada:
--   docker exec -i academico_postgres psql -U postgres -d academico_db \
--       < database/oltp/15_dw_red_curricular.sql
--   python -m etl.carga
-- =============================================================================

-- Una fila por relación (A)-[:REQUIERE_APROBADA]->(B) del grafo: "para cursar A
-- hay que haber aprobado B". Es un puente entre dim_materia y ella misma.
CREATE TABLE IF NOT EXISTS dw_academico.bridge_prerrequisito (
    materia_key        INT NOT NULL REFERENCES dw_academico.dim_materia (materia_key),
    prerrequisito_key  INT NOT NULL REFERENCES dw_academico.dim_materia (materia_key),
    PRIMARY KEY (materia_key, prerrequisito_key),
    CONSTRAINT ck_bridge_prerrequisito_distintas CHECK (materia_key <> prerrequisito_key)
);

-- La cascada de dependientes se recorre al revés: dado un prerrequisito, ¿quién
-- lo exige?
CREATE INDEX IF NOT EXISTS idx_bridge_prerrequisito_requisito
    ON dw_academico.bridge_prerrequisito (prerrequisito_key);

COMMENT ON TABLE dw_academico.bridge_prerrequisito IS
    'Relaciones de prerrequisito de la malla, cargadas desde Neo4j por el ETL. '
    '(materia_key, prerrequisito_key): para cursar materia hay que aprobar prerrequisito.';

-- -----------------------------------------------------------------------------
-- Permisos: los mismos que el resto de las tablas del DW (scripts 10 y 13). Los
-- GRANT ... ON ALL TABLES de esos scripts no alcanzan a una tabla creada después.
-- -----------------------------------------------------------------------------
GRANT SELECT ON dw_academico.bridge_prerrequisito TO rol_etl;
GRANT SELECT ON dw_academico.bridge_prerrequisito TO rol_dashboard;
GRANT INSERT, TRUNCATE ON dw_academico.bridge_prerrequisito TO rol_dw_carga;
