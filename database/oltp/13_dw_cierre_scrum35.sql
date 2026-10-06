-- =============================================================================
-- UNIVERSIDAD DE EL SALVADOR - FACULTAD MULTIDISCIPLINARIA ORIENTAL
-- CURSO DE ESPECIALIZACIÓN: ADMINISTRACIÓN DE BASES DE DATOS E INTELIGENCIA DE NEGOCIOS
-- FASE 3 - PUNTO 3.3 (SCRUM-35): CIERRE DEL MODELO DIMENSIONAL
-- =============================================================================
-- Cierra lo que el esquema estrella de los scripts 10 y 12 dejaba fuera de los
-- criterios de aceptación de SCRUM-35. Es una migración aparte para poder
-- aplicarla sobre un DW que ya existe sin recrearlo, y es idempotente.
--
--   1. dim_docente y dim_seccion, con sus llaves en la tabla de hechos.
--   2. costo_repeticion, la tercera medida de costo (UV × costo por UV cuando
--      numero_intento > 1).
--   3. v_mart_departamento: el corte por departamento (data mart) con las
--      medidas de costo ya agregadas.
--   4. Rol de ESCRITURA propio del DW (rol_dw_carga) y retiro de los permisos de
--      escritura que el script 10 le había dado a rol_etl.
--
-- Por qué está en database/oltp/ y no en database/dw/: ver la nota del script 10
-- (un solo directorio se monta como docker-entrypoint-initdb.d).
--
-- En una base ya inicializada:
--   docker exec -i academico_postgres psql -U postgres -d academico_db \
--       < database/oltp/13_dw_cierre_scrum35.sql
--   docker exec -i -e DW_CARGA_DB_USER -e DW_CARGA_DB_PASSWORD \
--       academico_postgres bash -s < database/oltp/14_bootstrap_rol_dw_carga.sh
-- y luego recargar con `python -m etl.carga`. Después de esa primera recarga,
-- volver a ejecutar ESTE script fija las llaves nuevas como NOT NULL (ver §2).
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. DIMENSIONES NUEVAS
-- -----------------------------------------------------------------------------
-- Sin codigo_docente: es un identificador institucional y la extracción nunca
-- lo trae (etl/extraccion.py). El departamento viaja desnormalizado, como en
-- dim_carrera: es el departamento DEL DOCENTE, que puede diferir del de la
-- carrera que oferta la materia.
CREATE TABLE IF NOT EXISTS dw_academico.dim_docente (
    docente_key          INT PRIMARY KEY,
    docente_id           INT NOT NULL UNIQUE,
    escalafon            VARCHAR(50) NOT NULL,
    departamento_id      INT NOT NULL,
    codigo_departamento  VARCHAR(10) NOT NULL,
    nombre_departamento  VARCHAR(100) NOT NULL,
    -- Nulo si el OLTP no lo informa: el ETL no inventa un valor (igual que
    -- dim_estudiante.trabaja).
    activo               BOOLEAN
);

-- Solo atributos propios de la sección. Materia y período se alcanzan por la
-- tabla de hechos (no se encadena dimensión con dimensión: estrella, no copo de
-- nieve); sus códigos van repetidos como texto únicamente para que una sección
-- sea legible por sí sola.
CREATE TABLE IF NOT EXISTS dw_academico.dim_seccion (
    seccion_key     INT PRIMARY KEY,
    seccion_id      INT NOT NULL UNIQUE,
    numero_seccion  INT NOT NULL,
    turno           VARCHAR(15) NOT NULL,
    cupo_maximo     INT NOT NULL,
    codigo_materia  VARCHAR(15) NOT NULL,
    codigo_periodo  VARCHAR(10) NOT NULL
);

-- -----------------------------------------------------------------------------
-- 2. TABLA DE HECHOS: LLAVES Y MEDIDA NUEVAS
-- -----------------------------------------------------------------------------
ALTER TABLE dw_academico.fact_inscripcion
    ADD COLUMN IF NOT EXISTS seccion_key  INT REFERENCES dw_academico.dim_seccion (seccion_key),
    ADD COLUMN IF NOT EXISTS docente_key  INT REFERENCES dw_academico.dim_docente (docente_key),
    -- costo_inscripcion si numero_intento > 1, 0 en cualquier otro caso.
    ADD COLUMN IF NOT EXISTS costo_repeticion NUMERIC(12, 2) NOT NULL DEFAULT 0;

-- costo_reprobacion y costo_repeticion NO son excluyentes (una repetición
-- reprobada cuenta en las dos), así que no deben sumarse entre sí.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_costo_repeticion') THEN
        ALTER TABLE dw_academico.fact_inscripcion
            ADD CONSTRAINT chk_costo_repeticion CHECK (
                costo_repeticion = 0 OR (es_repeticion AND costo_repeticion = costo_inscripcion)
            );
    END IF;
END
$$;

-- Las llaves nuevas solo se pueden exigir cuando no hay filas anteriores sin
-- ellas. En una base nueva la tabla está vacía y quedan NOT NULL de inmediato;
-- en una ya cargada quedan NULL hasta la primera recarga, y volver a ejecutar
-- este script las endurece. Así la migración nunca borra ni inventa datos.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM dw_academico.fact_inscripcion
                   WHERE seccion_key IS NULL OR docente_key IS NULL) THEN
        ALTER TABLE dw_academico.fact_inscripcion
            ALTER COLUMN seccion_key SET NOT NULL,
            ALTER COLUMN docente_key SET NOT NULL;
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_fact_seccion ON dw_academico.fact_inscripcion (seccion_key);
CREATE INDEX IF NOT EXISTS idx_fact_docente ON dw_academico.fact_inscripcion (docente_key);

COMMENT ON COLUMN dw_academico.fact_inscripcion.costo_inscripcion IS
    'Costo de la matrícula de la materia: unidades valorativas × costo por UV del período (SCRUM-35: costo_matricula_materia).';
COMMENT ON COLUMN dw_academico.fact_inscripcion.costo_reprobacion IS
    'costo_inscripcion cuando la inscripción termina REPROBADA, 0 en otro caso. Medida central del proyecto (SCRUM-35).';
COMMENT ON COLUMN dw_academico.fact_inscripcion.costo_repeticion IS
    'costo_inscripcion cuando numero_intento > 1, 0 en otro caso (SCRUM-35). No excluyente con costo_reprobacion: no sumarlos.';

-- -----------------------------------------------------------------------------
-- 3. DATA MART POR DEPARTAMENTO
-- -----------------------------------------------------------------------------
-- El departamento ya está desnormalizado en dim_carrera, así que el corte sale
-- de un solo JOIN. La vista lo deja resuelto, con las tres medidas de costo, por
-- departamento (el de la carrera que OFERTA la materia, la que asume el costo),
-- período y materia. Cubre las preguntas de negocio del proyecto: costo de la
-- reprobación por ciclo, materia y departamento, y su cruce con las materias
-- cuello de botella del grafo.
CREATE OR REPLACE VIEW dw_academico.v_mart_departamento AS
SELECT
    c.codigo_departamento,
    c.nombre_departamento,
    p.codigo_periodo,
    p.anio,
    p.ciclo_romano,
    p.orden               AS periodo_orden,
    m.codigo_materia,
    m.nombre_materia,
    m.ciclo_plan,
    m.es_cuello_botella,
    COUNT(*)                                        AS inscripciones,
    COUNT(*) FILTER (WHERE f.cerrada)               AS cerradas,
    COUNT(*) FILTER (WHERE f.reprobado)             AS reprobadas,
    COUNT(*) FILTER (WHERE f.es_repeticion)         AS repeticiones,
    SUM(f.costo_inscripcion)                        AS costo_matricula_materia,
    SUM(f.costo_reprobacion)                        AS costo_reprobacion,
    SUM(f.costo_repeticion)                         AS costo_repeticion
FROM dw_academico.fact_inscripcion f
JOIN dw_academico.dim_carrera c ON c.carrera_key  = f.carrera_key
JOIN dw_academico.dim_periodo p ON p.periodo_key  = f.periodo_key
JOIN dw_academico.dim_materia m ON m.materia_key  = f.materia_key
GROUP BY c.codigo_departamento, c.nombre_departamento, p.codigo_periodo, p.anio,
         p.ciclo_romano, p.orden, m.codigo_materia, m.nombre_materia, m.ciclo_plan,
         m.es_cuello_botella;

-- -----------------------------------------------------------------------------
-- 4. PERMISOS: LEER Y ESCRIBIR EN ROLES DISTINTOS
-- -----------------------------------------------------------------------------
-- rol_etl es de SOLO LECTURA (script 07): lee el OLTP para extraer y puede leer
-- el DW para validarlo, pero ya no lo escribe. La escritura es de un rol propio,
-- rol_dw_carga, que NO tiene ningún permiso sobre academico_oltp: quien puede
-- cargar el DW no puede leer ni alterar el sistema transaccional, y quien lee el
-- OLTP no puede alterar el DW. El script 14 le habilita el inicio de sesión.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'rol_dw_carga') THEN
        CREATE ROLE rol_dw_carga;
    END IF;
END
$$;

-- El script 10 le había concedido INSERT y TRUNCATE a rol_etl.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA dw_academico FROM rol_etl;
REVOKE USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA dw_academico FROM rol_etl;

-- Mínimo privilegio: la recarga vacía (TRUNCATE) y vuelve a llenar (INSERT);
-- no necesita leer ni modificar filas sueltas. Las secuencias son las de
-- carga_control.
GRANT USAGE ON SCHEMA dw_academico TO rol_dw_carga;
GRANT INSERT, TRUNCATE ON ALL TABLES IN SCHEMA dw_academico TO rol_dw_carga;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA dw_academico TO rol_dw_carga;
-- Las vistas no se cargan: se calculan sobre las tablas.
REVOKE INSERT, TRUNCATE ON dw_academico.v_mart_departamento FROM rol_dw_carga;

-- Lo que se creó en este script (dimensiones y vista) es nuevo para los roles de
-- lectura: GRANT ... ON ALL TABLES del script 10 no los alcanzó.
GRANT USAGE ON SCHEMA dw_academico TO rol_etl;
GRANT SELECT ON ALL TABLES IN SCHEMA dw_academico TO rol_etl;
GRANT SELECT ON ALL TABLES IN SCHEMA dw_academico TO rol_dashboard;
