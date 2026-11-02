-- =============================================================================
-- UNIVERSIDAD DE EL SALVADOR - FACULTAD MULTIDISCIPLINARIA ORIENTAL
-- ROL ADMIN Y COORDINADOR ACOTADO A UNA CARRERA
-- =============================================================================
-- Hasta aquí había un solo rol institucional: rol_coordinador veía y escribía
-- todo —las 12 carreras, los 8 departamentos, los 2.303 estudiantes— porque el
-- alcance del proyecto era institucional. Ahora se separan dos
-- responsabilidades que antes estaban juntas:
--
--   rol_admin        administra la institución: usuarios, períodos, carreras,
--                    departamentos, docentes, costos por UV y metas. Sin
--                    recorte: ve todo.
--   rol_coordinador  lleva UNA carrera. Opera matrícula, notas, asistencia y
--                    los catálogos de su carrera, y ve los tableros de su
--                    carrera. No administra la institución ni crea usuarios.
--
-- ¿Cómo sabe el motor qué carrera? Igual que con el docente (script 16): todos
-- los coordinadores comparten rol_coordinador, así que la aplicación declara la
-- carrera de la sesión en cada transacción, junto al SET LOCAL ROLE
-- (app/database.py):
--
--     SELECT set_config('app.carrera_id', '<id>', true);   -- true = solo esta transacción
--
-- Si no se declara, carrera_sesion() devuelve NULL y rol_coordinador no ve ni
-- escribe NINGUNA fila: falla cerrado, igual que el docente y que el NOINHERIT
-- de rol_app.
--
-- Las políticas se escriben EN LÍNEA y no con funciones auxiliares, por la
-- misma razón anotada en el script 16: una función con SET search_path no se
-- puede «inlinear» y PostgreSQL la ejecuta por cada fila (un conteo de notas
-- pasó de 4 ms a 26 s). En línea, el planificador las convierte en semi-joins.
--
-- Alcance honesto: protege contra errores de la aplicación. No protege contra
-- quien controle la conexión de rol_app, que puede declarar cualquier carrera;
-- esa credencial ya equivale a la aplicación entera y vive solo en el .env.
--
-- Idempotente.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. El rol y la carrera asignada
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rol_admin') THEN
        CREATE ROLE rol_admin NOLOGIN;
    END IF;
END $$;

-- rol_app (la aplicación) necesita poder adoptarlo, como ya adopta los otros dos.
GRANT rol_admin TO rol_app;

ALTER TABLE academico_oltp.usuarios
    ADD COLUMN IF NOT EXISTS carrera_id INT REFERENCES academico_oltp.carreras (carrera_id);

COMMENT ON COLUMN academico_oltp.usuarios.carrera_id IS
    'Carrera que lleva un rol_coordinador. NULL para rol_admin y rol_docente. '
    'El departamento no se guarda: se deriva de la carrera (carreras.departamento_id).';

-- Las dos restricciones que ya existían solo conocían dos roles: hay que
-- rehacerlas para que admitan el tercero.
--   usuarios_rol_db_check  enumeraba los roles válidos.
--   chk_docente_vinculado  exigía «docente => docente_id» y «coordinador =>
--                          sin docente_id»; con un tercer rol ninguna de las dos
--                          ramas se cumplía. Se reescribe en términos de «solo
--                          el docente lleva docente_id», que es la regla real.
ALTER TABLE academico_oltp.usuarios DROP CONSTRAINT IF EXISTS usuarios_rol_db_check;
ALTER TABLE academico_oltp.usuarios
    ADD CONSTRAINT usuarios_rol_db_check CHECK (
        rol_db IN ('rol_admin', 'rol_coordinador', 'rol_docente'));

ALTER TABLE academico_oltp.usuarios DROP CONSTRAINT IF EXISTS chk_docente_vinculado;
ALTER TABLE academico_oltp.usuarios
    ADD CONSTRAINT chk_docente_vinculado CHECK (
        (rol_db = 'rol_docente' AND docente_id IS NOT NULL)
        OR (rol_db <> 'rol_docente' AND docente_id IS NULL));

-- Un coordinador sin carrera no vería nada (falla cerrado), así que la regla se
-- declara en la base y no solo en la aplicación.
ALTER TABLE academico_oltp.usuarios
    DROP CONSTRAINT IF EXISTS chk_coordinador_con_carrera;
ALTER TABLE academico_oltp.usuarios
    ADD CONSTRAINT chk_coordinador_con_carrera CHECK (
        (rol_db = 'rol_coordinador' AND carrera_id IS NOT NULL)
        OR (rol_db <> 'rol_coordinador' AND carrera_id IS NULL)
    ) NOT VALID;

-- Carrera declarada para la transacción en curso (NULL si no hay).
CREATE OR REPLACE FUNCTION academico_oltp.carrera_sesion()
RETURNS INT LANGUAGE sql STABLE AS $$
    SELECT NULLIF(current_setting('app.carrera_id', true), '')::INT
$$ SET search_path = pg_catalog;

REVOKE ALL ON FUNCTION academico_oltp.carrera_sesion() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION academico_oltp.carrera_sesion() TO rol_coordinador, rol_admin;

-- -----------------------------------------------------------------------------
-- 2. Privilegios: rol_admin hereda lo que rol_coordinador tenía
-- -----------------------------------------------------------------------------
GRANT USAGE ON SCHEMA academico_oltp, auditoria TO rol_admin;
GRANT ALL ON ALL TABLES IN SCHEMA academico_oltp TO rol_admin;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA academico_oltp TO rol_admin;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA academico_oltp TO rol_admin;

-- Sobre la bitácora, SOLO lectura: también para el admin. La escriben las
-- funciones SECURITY DEFINER y ningún rol de la aplicación puede alterarla.
-- Es la garantía del sistema y no admite excepciones por jerarquía.
GRANT SELECT ON ALL TABLES IN SCHEMA auditoria TO rol_admin;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA auditoria FROM rol_admin;

-- -----------------------------------------------------------------------------
-- 3. Lo institucional deja de ser del coordinador
-- -----------------------------------------------------------------------------
-- Conserva SELECT (necesita leer períodos, carreras y departamentos para
-- trabajar) y pierde la escritura: eso ahora es del admin.
REVOKE ALL ON academico_oltp.usuarios FROM rol_coordinador;
GRANT SELECT ON academico_oltp.usuarios TO rol_coordinador;

REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON
    academico_oltp.periodos_academicos,
    academico_oltp.departamentos,
    academico_oltp.carreras,
    academico_oltp.docentes,
    academico_oltp.costos_uv,
    academico_oltp.indicadores,
    academico_oltp.metas_indicador
FROM rol_coordinador;

-- UPDATE por columna sobre indicadores (script 20): también pasa al admin.
REVOKE UPDATE (perspectiva, responsable_cargo) ON academico_oltp.indicadores FROM rol_coordinador;
GRANT UPDATE (perspectiva, responsable_cargo) ON academico_oltp.indicadores TO rol_admin;

-- Cerrar y reabrir actas: el admin también puede (es quien resuelve los casos
-- que el coordinador de carrera no debería resolver solo).
GRANT EXECUTE ON FUNCTION academico_oltp.cerrar_acta(INT) TO rol_admin;
GRANT EXECUTE ON FUNCTION academico_oltp.reabrir_acta(INT, TEXT) TO rol_admin;
GRANT EXECUTE ON FUNCTION academico_oltp.cambiar_password_propio(TEXT) TO rol_admin;
GRANT EXECUTE ON FUNCTION academico_oltp.actualizar_perfil_propio(TEXT) TO rol_admin;
GRANT EXECUTE ON FUNCTION academico_oltp.docente_sesion() TO rol_admin;

-- -----------------------------------------------------------------------------
-- 4. Seguridad por fila: el coordinador solo ve su carrera
-- -----------------------------------------------------------------------------
-- Criterio de las políticas:
--   rol_admin        USING (true)  -- sin recorte
--   rol_coordinador  la cadena carrera -> materia -> sección -> inscripción
--   rol_docente      USING (true)  -- su recorte real son las políticas del
--                                  -- script 16 sobre notas y asistencia; aquí
--                                  -- se deja como estaba para no cambiarle el
--                                  -- comportamiento con este script
--   rol_etl          FOR SELECT USING (true)  -- extrae todo; sin política leería
--                                             -- cero filas y cargaría un almacén
--                                             -- vacío sin un solo error
--
-- Al activar RLS, un rol sin política no ve ninguna fila. Por eso TODAS las
-- tablas de abajo llevan las cuatro.

ALTER TABLE academico_oltp.carreras      ENABLE ROW LEVEL SECURITY;
ALTER TABLE academico_oltp.materias      ENABLE ROW LEVEL SECURITY;
ALTER TABLE academico_oltp.estudiantes   ENABLE ROW LEVEL SECURITY;
ALTER TABLE academico_oltp.secciones     ENABLE ROW LEVEL SECURITY;
ALTER TABLE academico_oltp.inscripciones ENABLE ROW LEVEL SECURITY;

-- Admin, docente y ETL: las mismas tres políticas en las cinco tablas.
DO $$
DECLARE t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['carreras', 'materias', 'estudiantes', 'secciones', 'inscripciones']
    LOOP
        EXECUTE format('DROP POLICY IF EXISTS admin_todo ON academico_oltp.%I', t);
        EXECUTE format('CREATE POLICY admin_todo ON academico_oltp.%I FOR ALL TO rol_admin '
                       'USING (true) WITH CHECK (true)', t);
        EXECUTE format('DROP POLICY IF EXISTS docente_lectura ON academico_oltp.%I', t);
        EXECUTE format('CREATE POLICY docente_lectura ON academico_oltp.%I FOR ALL TO rol_docente '
                       'USING (true) WITH CHECK (true)', t);
        EXECUTE format('DROP POLICY IF EXISTS etl_lectura ON academico_oltp.%I', t);
        EXECUTE format('CREATE POLICY etl_lectura ON academico_oltp.%I FOR SELECT TO rol_etl '
                       'USING (true)', t);
    END LOOP;
END $$;

-- Coordinador: una política por tabla, con la cadena escrita en línea.
DROP POLICY IF EXISTS coordinador_todo ON academico_oltp.carreras;
DROP POLICY IF EXISTS coordinador_carrera ON academico_oltp.carreras;
CREATE POLICY coordinador_carrera ON academico_oltp.carreras FOR ALL TO rol_coordinador
    USING (carrera_id = academico_oltp.carrera_sesion())
    WITH CHECK (carrera_id = academico_oltp.carrera_sesion());

DROP POLICY IF EXISTS coordinador_carrera ON academico_oltp.materias;
CREATE POLICY coordinador_carrera ON academico_oltp.materias FOR ALL TO rol_coordinador
    USING (carrera_id = academico_oltp.carrera_sesion())
    WITH CHECK (carrera_id = academico_oltp.carrera_sesion());

DROP POLICY IF EXISTS coordinador_carrera ON academico_oltp.estudiantes;
CREATE POLICY coordinador_carrera ON academico_oltp.estudiantes FOR ALL TO rol_coordinador
    USING (carrera_id = academico_oltp.carrera_sesion())
    WITH CHECK (carrera_id = academico_oltp.carrera_sesion());

DROP POLICY IF EXISTS coordinador_carrera ON academico_oltp.secciones;
CREATE POLICY coordinador_carrera ON academico_oltp.secciones FOR ALL TO rol_coordinador
    USING (materia_id IN (SELECT m.materia_id FROM academico_oltp.materias m
                          WHERE m.carrera_id = academico_oltp.carrera_sesion()))
    WITH CHECK (materia_id IN (SELECT m.materia_id FROM academico_oltp.materias m
                               WHERE m.carrera_id = academico_oltp.carrera_sesion()));

DROP POLICY IF EXISTS coordinador_carrera ON academico_oltp.inscripciones;
CREATE POLICY coordinador_carrera ON academico_oltp.inscripciones FOR ALL TO rol_coordinador
    USING (seccion_id IN (SELECT s.seccion_id FROM academico_oltp.secciones s
                          JOIN academico_oltp.materias m ON m.materia_id = s.materia_id
                          WHERE m.carrera_id = academico_oltp.carrera_sesion()))
    WITH CHECK (seccion_id IN (SELECT s.seccion_id FROM academico_oltp.secciones s
                               JOIN academico_oltp.materias m ON m.materia_id = s.materia_id
                               WHERE m.carrera_id = academico_oltp.carrera_sesion()));

-- Las tres tablas que ya tenían RLS (script 16): el coordinador deja de verlas
-- enteras y pasa a ver las de su carrera. El admin toma el acceso completo.
DROP POLICY IF EXISTS coordinador_todo ON academico_oltp.evaluaciones;
DROP POLICY IF EXISTS admin_todo ON academico_oltp.evaluaciones;
DROP POLICY IF EXISTS coordinador_carrera ON academico_oltp.evaluaciones;
CREATE POLICY admin_todo ON academico_oltp.evaluaciones FOR ALL TO rol_admin
    USING (true) WITH CHECK (true);
CREATE POLICY coordinador_carrera ON academico_oltp.evaluaciones FOR ALL TO rol_coordinador
    USING (seccion_id IN (SELECT s.seccion_id FROM academico_oltp.secciones s
                          JOIN academico_oltp.materias m ON m.materia_id = s.materia_id
                          WHERE m.carrera_id = academico_oltp.carrera_sesion()))
    WITH CHECK (seccion_id IN (SELECT s.seccion_id FROM academico_oltp.secciones s
                               JOIN academico_oltp.materias m ON m.materia_id = s.materia_id
                               WHERE m.carrera_id = academico_oltp.carrera_sesion()));

DROP POLICY IF EXISTS coordinador_todo ON academico_oltp.calificaciones;
DROP POLICY IF EXISTS admin_todo ON academico_oltp.calificaciones;
DROP POLICY IF EXISTS coordinador_carrera ON academico_oltp.calificaciones;
CREATE POLICY admin_todo ON academico_oltp.calificaciones FOR ALL TO rol_admin
    USING (true) WITH CHECK (true);
CREATE POLICY coordinador_carrera ON academico_oltp.calificaciones FOR ALL TO rol_coordinador
    USING (inscripcion_id IN (SELECT i.inscripcion_id FROM academico_oltp.inscripciones i
                              JOIN academico_oltp.secciones s ON s.seccion_id = i.seccion_id
                              JOIN academico_oltp.materias m ON m.materia_id = s.materia_id
                              WHERE m.carrera_id = academico_oltp.carrera_sesion()))
    WITH CHECK (inscripcion_id IN (SELECT i.inscripcion_id FROM academico_oltp.inscripciones i
                                   JOIN academico_oltp.secciones s ON s.seccion_id = i.seccion_id
                                   JOIN academico_oltp.materias m ON m.materia_id = s.materia_id
                                   WHERE m.carrera_id = academico_oltp.carrera_sesion()));

DROP POLICY IF EXISTS coordinador_todo ON academico_oltp.asistencias;
DROP POLICY IF EXISTS admin_todo ON academico_oltp.asistencias;
DROP POLICY IF EXISTS coordinador_carrera ON academico_oltp.asistencias;
CREATE POLICY admin_todo ON academico_oltp.asistencias FOR ALL TO rol_admin
    USING (true) WITH CHECK (true);
CREATE POLICY coordinador_carrera ON academico_oltp.asistencias FOR ALL TO rol_coordinador
    USING (inscripcion_id IN (SELECT i.inscripcion_id FROM academico_oltp.inscripciones i
                              JOIN academico_oltp.secciones s ON s.seccion_id = i.seccion_id
                              JOIN academico_oltp.materias m ON m.materia_id = s.materia_id
                              WHERE m.carrera_id = academico_oltp.carrera_sesion()))
    WITH CHECK (inscripcion_id IN (SELECT i.inscripcion_id FROM academico_oltp.inscripciones i
                                   JOIN academico_oltp.secciones s ON s.seccion_id = i.seccion_id
                                   JOIN academico_oltp.materias m ON m.materia_id = s.materia_id
                                   WHERE m.carrera_id = academico_oltp.carrera_sesion()));

-- -----------------------------------------------------------------------------
-- 5. Migración de las cuentas que ya existen
-- -----------------------------------------------------------------------------
-- Los coordinadores actuales son institucionales: pasan a rol_admin. Si se
-- quedaran como rol_coordinador sin carrera no verían nada (falla cerrado) y
-- nadie podría volver a entrar a administrar.
UPDATE academico_oltp.usuarios
   SET rol_db = 'rol_admin'
 WHERE rol_db = 'rol_coordinador' AND carrera_id IS NULL;

ALTER TABLE academico_oltp.usuarios VALIDATE CONSTRAINT chk_coordinador_con_carrera;

-- -----------------------------------------------------------------------------
-- 6. Las funciones de actas admiten al admin
-- -----------------------------------------------------------------------------
-- cerrar_acta() y reabrir_acta() (script 17) comprueban el rol DENTRO de la
-- función, y su lista no conocía rol_admin: con solo dar EXECUTE, el admin
-- recibía «Rol sin permiso para cerrar actas». Se repiten enteras porque
-- PostgreSQL no permite modificar el cuerpo de una función por partes; es el
-- mismo proceder del script 09 con la función de auditoría. El script 17 queda
-- igualmente corregido, para que una instalación nueva nazca bien.

CREATE OR REPLACE FUNCTION academico_oltp.cerrar_acta(p_seccion_id INT)
RETURNS INT AS $$
DECLARE
    v_rol TEXT := COALESCE(NULLIF(current_setting('role', true), 'none'), session_user);
    v_docente INT;
    v_cerrada BOOLEAN;
    v_ponderacion NUMERIC(6,2);
    v_faltan INT;
    v_ids BIGINT[];
BEGIN
    IF v_rol NOT IN ('rol_admin', 'rol_docente', 'rol_coordinador') THEN
        RAISE EXCEPTION 'Rol sin permiso para cerrar actas';
    END IF;

    SELECT docente_id, acta_cerrada INTO v_docente, v_cerrada
    FROM academico_oltp.secciones WHERE seccion_id = p_seccion_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Sección no encontrada';
    END IF;
    IF v_rol = 'rol_docente' AND v_docente IS DISTINCT FROM academico_oltp.docente_sesion() THEN
        RAISE EXCEPTION 'Solo el docente de la sección o el coordinador pueden cerrar su acta';
    END IF;
    IF v_cerrada THEN
        RAISE EXCEPTION 'El acta de esta sección ya está cerrada';
    END IF;

    SELECT COALESCE(SUM(porcentaje), 0) INTO v_ponderacion
    FROM academico_oltp.evaluaciones WHERE seccion_id = p_seccion_id;
    IF v_ponderacion <> 100 THEN
        RAISE EXCEPTION 'Las evaluaciones suman % %% y deben sumar 100 %% para cerrar el acta', v_ponderacion;
    END IF;

    SELECT count(*) INTO v_faltan
    FROM academico_oltp.inscripciones i
    JOIN academico_oltp.evaluaciones e ON e.seccion_id = i.seccion_id
    WHERE i.seccion_id = p_seccion_id AND i.estado_inscripcion = 'INSCRITO'
      AND NOT EXISTS (SELECT 1 FROM academico_oltp.calificaciones c
                      WHERE c.inscripcion_id = i.inscripcion_id AND c.evaluacion_id = e.evaluacion_id);
    IF v_faltan > 0 THEN
        RAISE EXCEPTION 'Faltan % nota(s) por registrar: el acta solo se cierra con todas las notas', v_faltan;
    END IF;

    WITH finalizadas AS (
        UPDATE academico_oltp.inscripciones SET estado_inscripcion = 'FINALIZADO'
        WHERE seccion_id = p_seccion_id AND estado_inscripcion = 'INSCRITO'
        RETURNING inscripcion_id
    )
    SELECT COALESCE(array_agg(inscripcion_id), '{}') INTO v_ids FROM finalizadas;

    UPDATE academico_oltp.secciones SET acta_cerrada = TRUE WHERE seccion_id = p_seccion_id;
    INSERT INTO auditoria.log_actas (seccion_id, accion, usuario_app, usuario_db, inscripciones)
    VALUES (p_seccion_id, 'CERRADA', NULLIF(current_setting('app.usuario', true), ''), v_rol, v_ids);
    RETURN cardinality(v_ids);
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, academico_oltp, auditoria;

CREATE OR REPLACE FUNCTION academico_oltp.reabrir_acta(p_seccion_id INT, p_motivo TEXT)
RETURNS INT AS $$
DECLARE
    v_rol TEXT := COALESCE(NULLIF(current_setting('role', true), 'none'), session_user);
    v_ids BIGINT[];
BEGIN
    IF v_rol NOT IN ('rol_admin', 'rol_coordinador') THEN
        RAISE EXCEPTION 'Solo el coordinador de la carrera o el administrador pueden reabrir un acta';
    END IF;
    IF length(btrim(COALESCE(p_motivo, ''))) < 5 THEN
        RAISE EXCEPTION 'Indica el motivo de la reapertura (al menos 5 caracteres)';
    END IF;
    PERFORM 1 FROM academico_oltp.secciones
    WHERE seccion_id = p_seccion_id AND acta_cerrada FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'El acta de esta sección no está cerrada';
    END IF;

    SELECT inscripciones INTO v_ids FROM auditoria.log_actas
    WHERE seccion_id = p_seccion_id AND accion = 'CERRADA'
    ORDER BY fecha DESC, log_id DESC LIMIT 1;

    UPDATE academico_oltp.inscripciones SET estado_inscripcion = 'INSCRITO'
    WHERE inscripcion_id = ANY (COALESCE(v_ids, '{}')) AND estado_inscripcion = 'FINALIZADO';
    UPDATE academico_oltp.secciones SET acta_cerrada = FALSE WHERE seccion_id = p_seccion_id;
    INSERT INTO auditoria.log_actas (seccion_id, accion, usuario_app, usuario_db, motivo, inscripciones)
    VALUES (p_seccion_id, 'REABIERTA', NULLIF(current_setting('app.usuario', true), ''), v_rol,
            left(btrim(p_motivo), 300), COALESCE(v_ids, '{}'));
    RETURN cardinality(COALESCE(v_ids, '{}'));
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, academico_oltp, auditoria;
