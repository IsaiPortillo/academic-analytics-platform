-- =============================================================================
-- UNIVERSIDAD DE EL SALVADOR - FACULTAD MULTIDISCIPLINARIA ORIENTAL
-- EL ALMACÉN TAMBIÉN RESPETA LA CARRERA DEL COORDINADOR
-- =============================================================================
-- El script 23 acotó al coordinador en el OLTP, pero los tableros no leen el
-- OLTP: leen dw_academico con una conexión propia como rol_dashboard
-- (app/dw.py). Sin este script, un coordinador de carrera operaría solo lo suyo
-- y seguiría viendo los indicadores de las 12 carreras.
--
-- No se puede acotar a rol_dashboard directamente: ese mismo rol lo usan el
-- tablero de Streamlit y la validación del almacén, que SÍ deben verlo todo.
-- Así que se agrega un rol de grupo:
--
--   rol_dashboard   (sin cambios)  ve todo el almacén: Streamlit, validación
--   rol_dw_carrera  nuevo          ve solo la carrera declarada en la sesión
--
-- rol_dashboard es miembro de rol_dw_carrera, y la aplicación web lo adopta con
-- SET LOCAL ROLE solo cuando quien pregunta es un coordinador de carrera
-- (app/dw.py). Si adopta el rol y no declara la carrera, no ve NINGUNA fila:
-- falla cerrado, igual que en el OLTP.
--
-- La carrera se lee con current_setting en línea y no con una función: las
-- funciones del OLTP viven en academico_oltp, y rol_dashboard no tiene acceso a
-- ese esquema a propósito —es una propiedad que la validación comprueba— así
-- que no puede llamarlas.
--
-- Idempotente.
-- =============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rol_dw_carrera') THEN
        CREATE ROLE rol_dw_carrera NOLOGIN;
    END IF;
END $$;

GRANT rol_dw_carrera TO rol_dashboard;
GRANT USAGE ON SCHEMA dw_academico TO rol_dw_carrera;
GRANT SELECT ON ALL TABLES IN SCHEMA dw_academico TO rol_dw_carrera;
ALTER DEFAULT PRIVILEGES IN SCHEMA dw_academico GRANT SELECT ON TABLES TO rol_dw_carrera;

-- -----------------------------------------------------------------------------
-- Las cuatro tablas que tienen carrera
-- -----------------------------------------------------------------------------
DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['fact_inscripcion', 'dim_estudiante', 'dim_materia', 'dim_carrera']
    LOOP
        EXECUTE format('ALTER TABLE dw_academico.%I ENABLE ROW LEVEL SECURITY', t);

        -- Quien carga y quien extrae: acceso completo. Sin política no verían ni
        -- escribirían ninguna fila y el almacén quedaría vacío sin un solo error.
        EXECUTE format('DROP POLICY IF EXISTS carga_todo ON dw_academico.%I', t);
        EXECUTE format('CREATE POLICY carga_todo ON dw_academico.%I FOR ALL '
                       'TO rol_dw_carga, rol_etl USING (true) WITH CHECK (true)', t);

        -- El tablero institucional: Streamlit y la validación del almacén.
        EXECUTE format('DROP POLICY IF EXISTS dashboard_todo ON dw_academico.%I', t);
        EXECUTE format('CREATE POLICY dashboard_todo ON dw_academico.%I FOR SELECT '
                       'TO rol_dashboard USING (true)', t);

        -- El coordinador de carrera. Sin app.carrera_id declarado: cero filas.
        EXECUTE format('DROP POLICY IF EXISTS carrera_declarada ON dw_academico.%I', t);
        -- Solo dim_carrera guarda el id natural; las demás llevan la llave
        -- sustituta, así que se traduce con una semi-consulta a dim_carrera (12
        -- filas: el costo es despreciable).
        IF t = 'dim_carrera' THEN
            EXECUTE 'CREATE POLICY carrera_declarada ON dw_academico.dim_carrera FOR SELECT '
                    'TO rol_dw_carrera '
                    'USING (carrera_id = NULLIF(current_setting(''app.carrera_id'', true), '''')::INT)';
        ELSE
            EXECUTE format('CREATE POLICY carrera_declarada ON dw_academico.%I FOR SELECT '
                           'TO rol_dw_carrera '
                           'USING (carrera_key IN (SELECT d.carrera_key FROM dw_academico.dim_carrera d '
                           'WHERE d.carrera_id = NULLIF(current_setting(''app.carrera_id'', true), '''')::INT))', t);
        END IF;
    END LOOP;
END $$;

-- -----------------------------------------------------------------------------
-- El data mart por departamento
-- -----------------------------------------------------------------------------
-- Una vista, por omisión, se evalúa con los permisos de SU DUEÑO, así que la
-- seguridad por fila de las tablas de abajo no se aplicaría y el recorte se
-- podría esquivar consultando la vista. security_invoker la evalúa con los
-- permisos de quien pregunta, que es lo que aquí se necesita.
ALTER VIEW dw_academico.v_mart_departamento SET (security_invoker = on);

-- Las vistas de indicadores NO se tocan a propósito: las metas son
-- institucionales (academico_oltp.metas_indicador), así que el semáforo también
-- lo es. Un coordinador de carrera ve el valor institucional frente a la meta
-- institucional; comparar su carrera contra una meta de toda la institución
-- sería engañoso. Si en el futuro hay metas por carrera, esto cambia.

COMMENT ON TABLE dw_academico.fact_inscripcion IS
    'Hechos de inscripción. Con seguridad por fila: rol_dw_carrera solo ve la '
    'carrera declarada en app.carrera_id (script 24).';
