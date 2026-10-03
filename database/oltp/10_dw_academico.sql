-- =============================================================================
-- UNIVERSIDAD DE EL SALVADOR - FACULTAD MULTIDISCIPLINARIA ORIENTAL
-- CURSO DE ESPECIALIZACIÓN: ADMINISTRACIÓN DE BASES DE DATOS E INTELIGENCIA DE NEGOCIOS
-- FASE 3 - PUNTO 3.3: MODELO DIMENSIONAL (DATA WAREHOUSE)
-- =============================================================================
-- Esquema estrella dw_academico, cargado por el ETL (etl/carga.py) y leído
-- por la vista ejecutiva de la aplicación web (backend/app/dw.py). Vive en la misma instancia de PostgreSQL que
-- el OLTP pero en un esquema separado, con permisos separados.
--
-- Por qué está en database/oltp/ y no en database/dw/: docker-compose monta
-- este directorio como docker-entrypoint-initdb.d, y el DW debe crearse en el
-- primer arranque DESPUÉS de los roles del script 01. Un segundo directorio no
-- se puede montar en el mismo punto.
--
-- Grano de la tabla de hechos: una inscripción (un estudiante cursando una
-- sección en un período). Es el grano más fino que el análisis necesita y
-- permite sumar costos y contar reprobados por cualquier combinación de
-- dimensiones sin doble conteo.
--
-- En una base ya inicializada, este script no corre solo. Aplicarlo con:
--   docker exec -i academico_postgres psql -U postgres -d academico_db \
--       < database/oltp/10_dw_academico.sql
-- Es idempotente: se puede volver a ejecutar sin perder nada que no se
-- recupere con una nueva carga del ETL.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS dw_academico;

-- -----------------------------------------------------------------------------
-- 1. DIMENSIONES
-- -----------------------------------------------------------------------------
-- Las llaves *_key son sustitutas, asignadas por el ETL. Las *_id originales
-- del OLTP se guardan como atributo para poder rastrear un dato hasta su
-- fuente, pero el modelo nunca une por ellas.

CREATE TABLE IF NOT EXISTS dw_academico.dim_periodo (
    periodo_key     INT PRIMARY KEY,
    periodo_id      INT NOT NULL UNIQUE,
    codigo_periodo  VARCHAR(10) NOT NULL UNIQUE,
    anio            INT NOT NULL,
    ciclo_romano    VARCHAR(5) NOT NULL,
    fecha_inicio    DATE NOT NULL,
    fecha_fin       DATE NOT NULL,
    -- Posición cronológica (1 = el más antiguo). Permite comparar contra el
    -- período anterior sin depender de cómo se escriben los códigos.
    orden           INT NOT NULL UNIQUE,
    -- Costo institucional vigente en el período (academico_oltp.costos_uv).
    -- Va en la dimensión porque es un atributo del período, y su fuente debe
    -- viajar con él: el dashboard advierte si la cifra es un supuesto.
    costo_por_uv    NUMERIC(10, 2),
    moneda          CHAR(3),
    fuente_costo    VARCHAR(200)
);

-- Departamento desnormalizado dentro de carrera: estrella, no copo de nieve.
-- Un filtro por departamento es un WHERE sobre esta dimensión, sin otro JOIN.
CREATE TABLE IF NOT EXISTS dw_academico.dim_carrera (
    carrera_key          INT PRIMARY KEY,
    carrera_id           INT NOT NULL UNIQUE,
    codigo_carrera       VARCHAR(10) NOT NULL,
    nombre_carrera       VARCHAR(120) NOT NULL,
    departamento_id      INT NOT NULL,
    codigo_departamento  VARCHAR(10) NOT NULL,
    nombre_departamento  VARCHAR(100) NOT NULL
);

-- Incluye las métricas estructurales del grafo curricular (Neo4j): son
-- atributos de la materia, no medidas de un hecho. Las tasas de reprobación,
-- en cambio, NO van aquí: se agregan desde los hechos según el filtro activo.
CREATE TABLE IF NOT EXISTS dw_academico.dim_materia (
    materia_key              INT PRIMARY KEY,
    materia_id               INT NOT NULL UNIQUE,
    codigo_materia           VARCHAR(15) NOT NULL UNIQUE,
    nombre_materia           VARCHAR(150) NOT NULL,
    unidades_valorativas     INT NOT NULL,
    ciclo_plan               INT NOT NULL,
    carrera_key              INT NOT NULL REFERENCES dw_academico.dim_carrera (carrera_key),
    en_grafo                 BOOLEAN NOT NULL,
    dependientes_directos    INT NOT NULL,
    dependientes_indirectos  INT NOT NULL,
    dependientes_totales     INT NOT NULL,
    longitud_cascada         INT NOT NULL,
    indice_bloqueo           NUMERIC(6, 4) NOT NULL,
    es_cuello_botella        BOOLEAN NOT NULL
);

-- Sin nombre, sin carnet en claro: la identidad es carnet_hash (SHA-256).
CREATE TABLE IF NOT EXISTS dw_academico.dim_estudiante (
    estudiante_key       INT PRIMARY KEY,
    estudiante_id        INT NOT NULL UNIQUE,
    carnet_hash          CHAR(64) NOT NULL UNIQUE,
    anio_ingreso         INT NOT NULL,
    carrera_key          INT NOT NULL REFERENCES dw_academico.dim_carrera (carrera_key),
    trabaja              BOOLEAN,
    condicion_academica  VARCHAR(20)
);

-- -----------------------------------------------------------------------------
-- 2. TABLA DE HECHOS
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dw_academico.fact_inscripcion (
    inscripcion_id         BIGINT PRIMARY KEY,  -- dimensión degenerada
    periodo_key            INT NOT NULL REFERENCES dw_academico.dim_periodo (periodo_key),
    materia_key            INT NOT NULL REFERENCES dw_academico.dim_materia (materia_key),
    estudiante_key         INT NOT NULL REFERENCES dw_academico.dim_estudiante (estudiante_key),
    -- Carrera que OFERTA la materia (la que paga su costo), no la del estudiante.
    carrera_key            INT NOT NULL REFERENCES dw_academico.dim_carrera (carrera_key),

    numero_intento         INT NOT NULL,
    es_repeticion          BOOLEAN NOT NULL,      -- numero_intento > 1
    resultado              VARCHAR(20) NOT NULL,  -- clasificación de SCRUM-34
    cerrada                BOOLEAN NOT NULL,      -- APROBADO o REPROBADO
    reprobado              BOOLEAN NOT NULL,
    retirado               BOOLEAN NOT NULL,
    nota_final             NUMERIC(4, 2),         -- nula si no está cerrada

    unidades_valorativas   INT NOT NULL,
    -- Lo que la institución invirtió en esta inscripción: UV × costo por UV.
    costo_inscripcion      NUMERIC(12, 2),
    -- costo_inscripcion si terminó REPROBADO, 0 en cualquier otro caso. Es
    -- aditiva: SUM() da el costo de reprobación de cualquier corte.
    costo_reprobacion      NUMERIC(12, 2) NOT NULL DEFAULT 0,

    sesiones               INT NOT NULL,
    presentes              INT NOT NULL,
    ausentes               INT NOT NULL,
    porcentaje_asistencia  NUMERIC(5, 2),

    CONSTRAINT chk_costo_reprobacion CHECK (
        costo_reprobacion = 0 OR (reprobado AND costo_reprobacion = costo_inscripcion)
    )
);

CREATE INDEX IF NOT EXISTS idx_fact_periodo  ON dw_academico.fact_inscripcion (periodo_key);
CREATE INDEX IF NOT EXISTS idx_fact_carrera  ON dw_academico.fact_inscripcion (carrera_key);
CREATE INDEX IF NOT EXISTS idx_fact_materia  ON dw_academico.fact_inscripcion (materia_key);

-- -----------------------------------------------------------------------------
-- 3. CONTROL DE CARGAS
-- -----------------------------------------------------------------------------
-- Una fila por carga exitosa: cuándo, con qué fecha de corte y con qué
-- reporte de calidad. El dashboard muestra la fecha de la última carga.
CREATE TABLE IF NOT EXISTS dw_academico.carga_control (
    carga_id           SERIAL PRIMARY KEY,
    ejecutada_en       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_corte        DATE NOT NULL,
    filas_hechos       INT NOT NULL,
    calidad            JSONB NOT NULL
);

-- -----------------------------------------------------------------------------
-- 4. PERMISOS
-- -----------------------------------------------------------------------------
-- rol_etl: lee el OLTP (script 01) y es el único que escribe el DW. TRUNCATE
-- porque la carga es una recarga completa dentro de una transacción.
GRANT USAGE ON SCHEMA dw_academico TO rol_etl;
GRANT SELECT, INSERT, TRUNCATE ON ALL TABLES IN SCHEMA dw_academico TO rol_etl;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA dw_academico TO rol_etl;

-- rol_dashboard: SOLO lectura, y SOLO del DW. No se le concede nada sobre
-- academico_oltp ni auditoria: que el dashboard nunca consulte las tablas
-- transaccionales no depende del código de la aplicación, lo impone PostgreSQL.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'rol_dashboard') THEN
        CREATE ROLE rol_dashboard;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA dw_academico TO rol_dashboard;
GRANT SELECT ON ALL TABLES IN SCHEMA dw_academico TO rol_dashboard;
