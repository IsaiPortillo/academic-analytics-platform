-- =============================================================================
-- UNIVERSIDAD DE EL SALVADOR - FACULTAD MULTIDISCIPLINARIA ORIENTAL
-- BITÁCORA COMPLETA DE NOTAS Y CIERRE DE ACTAS
-- =============================================================================
-- 1. La bitácora de notas registra también QUIÉN en la aplicación hizo el
--    cambio (no solo el rol del motor, que todos los docentes comparten), las
--    notas nuevas y las eliminadas, y a qué estudiante y evaluación pertenecían.
-- 2. Cerrar el acta de una sección finaliza sus inscripciones y bloquea, desde
--    el motor, cualquier cambio en sus evaluaciones, notas y asistencia. Solo el
--    coordinador puede reabrirla, con un motivo que queda registrado.
-- 3. El docente puede eliminar evaluaciones, notas y sesiones de asistencia de
--    sus secciones (las políticas de fila del script 16 ya lo limitan a ellas).
--
-- Idempotente: se puede volver a ejecutar (scripts/aplicar_ddl_pendiente.sh).
-- =============================================================================

SET search_path TO academico_oltp, public;

-- -----------------------------------------------------------------------------
-- 1. BITÁCORA DE NOTAS
-- -----------------------------------------------------------------------------
ALTER TABLE auditoria.log_cambios_notas
    ADD COLUMN IF NOT EXISTS operacion CHAR(1) NOT NULL DEFAULT 'U'
        CHECK (operacion IN ('I', 'U', 'D')),
    ADD COLUMN IF NOT EXISTS usuario_app VARCHAR(50),
    ADD COLUMN IF NOT EXISTS inscripcion_id BIGINT,
    ADD COLUMN IF NOT EXISTS evaluacion_id INT,
    -- Copia del nombre: si la evaluación se elimina, la bitácora sigue diciendo cuál era.
    ADD COLUMN IF NOT EXISTS evaluacion_nombre VARCHAR(100);

-- Filas anteriores a este script: se completan con lo que todavía existe.
UPDATE auditoria.log_cambios_notas l
SET inscripcion_id = c.inscripcion_id,
    evaluacion_id = c.evaluacion_id,
    evaluacion_nombre = e.nombre_evaluacion
FROM academico_oltp.calificaciones c
JOIN academico_oltp.evaluaciones e ON e.evaluacion_id = c.evaluacion_id
WHERE l.calificacion_id = c.calificacion_id AND l.inscripcion_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_log_notas_fecha ON auditoria.log_cambios_notas (fecha_modificacion DESC);

CREATE OR REPLACE FUNCTION auditoria.fn_auditoria_cambio_nota()
RETURNS TRIGGER AS $$
DECLARE
    v_fila academico_oltp.calificaciones;
    v_anterior NUMERIC(4,2);
    v_nueva NUMERIC(4,2);
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_fila := NEW; v_nueva := NEW.nota;
    ELSIF TG_OP = 'DELETE' THEN
        v_fila := OLD; v_anterior := OLD.nota;
    ELSE
        IF OLD.nota IS NOT DISTINCT FROM NEW.nota THEN
            RETURN NEW;
        END IF;
        v_fila := NEW; v_anterior := OLD.nota; v_nueva := NEW.nota;
    END IF;

    INSERT INTO auditoria.log_cambios_notas (
        calificacion_id, nota_anterior, nota_nueva, usuario_db, operacion,
        usuario_app, inscripcion_id, evaluacion_id, evaluacion_nombre
    )
    VALUES (
        v_fila.calificacion_id,
        v_anterior,
        v_nueva,
        -- Dentro de SECURITY DEFINER, CURRENT_USER es el dueño de la función:
        -- el rol real del que llama está en el GUC 'role' (ver script 09).
        COALESCE(NULLIF(current_setting('role', true), 'none'), session_user),
        left(TG_OP, 1),   -- I, U o D
        -- Lo declara la aplicación en cada transacción (app/database.py). NULL
        -- si el cambio no vino de la aplicación (mantenimiento directo).
        NULLIF(current_setting('app.usuario', true), ''),
        v_fila.inscripcion_id,
        v_fila.evaluacion_id,
        (SELECT e.nombre_evaluacion FROM academico_oltp.evaluaciones e
         WHERE e.evaluacion_id = v_fila.evaluacion_id)
    );
    RETURN v_fila;
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, auditoria;

-- Antes solo AFTER UPDATE: ahora también las notas nuevas y las eliminadas.
DROP TRIGGER IF EXISTS trg_auditoria_cambio_nota ON academico_oltp.calificaciones;
CREATE TRIGGER trg_auditoria_cambio_nota
    AFTER INSERT OR UPDATE OF nota OR DELETE ON academico_oltp.calificaciones
    FOR EACH ROW
    EXECUTE FUNCTION auditoria.fn_auditoria_cambio_nota();

-- -----------------------------------------------------------------------------
-- 2. ACTAS
-- -----------------------------------------------------------------------------
ALTER TABLE academico_oltp.secciones
    ADD COLUMN IF NOT EXISTS acta_cerrada BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS auditoria.log_actas (
    log_id BIGSERIAL PRIMARY KEY,
    seccion_id INT NOT NULL REFERENCES academico_oltp.secciones (seccion_id),
    accion VARCHAR(10) NOT NULL CHECK (accion IN ('CERRADA', 'REABIERTA')),
    usuario_app VARCHAR(50),
    usuario_db VARCHAR(50) NOT NULL,
    motivo VARCHAR(300),
    -- Inscripciones que el cierre pasó a FINALIZADO: la reapertura devuelve
    -- exactamente esas a INSCRITO, sin tocar las que ya estaban finalizadas.
    inscripciones BIGINT[] NOT NULL DEFAULT '{}',
    fecha TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_log_actas_seccion ON auditoria.log_actas (seccion_id, fecha DESC);
GRANT SELECT ON auditoria.log_actas TO rol_coordinador;

-- Bloqueo: ninguna escritura sobre una sección con el acta cerrada, venga de
-- quien venga (también del coordinador: primero tiene que reabrirla).
CREATE OR REPLACE FUNCTION academico_oltp.fn_bloquear_acta_cerrada()
RETURNS TRIGGER AS $$
DECLARE
    v_secciones INT[] := '{}';
    v_inscripciones BIGINT[] := '{}';
BEGIN
    -- OLD no existe en un INSERT ni NEW en un DELETE: se leen por separado.
    IF TG_TABLE_NAME = 'evaluaciones' THEN
        IF TG_OP <> 'INSERT' THEN v_secciones := v_secciones || OLD.seccion_id; END IF;
        IF TG_OP <> 'DELETE' THEN v_secciones := v_secciones || NEW.seccion_id; END IF;
    ELSE
        IF TG_OP <> 'INSERT' THEN v_inscripciones := v_inscripciones || OLD.inscripcion_id; END IF;
        IF TG_OP <> 'DELETE' THEN v_inscripciones := v_inscripciones || NEW.inscripcion_id; END IF;
        SELECT COALESCE(array_agg(i.seccion_id), '{}') INTO v_secciones
        FROM academico_oltp.inscripciones i
        WHERE i.inscripcion_id = ANY (v_inscripciones);
    END IF;

    IF EXISTS (SELECT 1 FROM academico_oltp.secciones s
               WHERE s.seccion_id = ANY (v_secciones) AND s.acta_cerrada) THEN
        RAISE EXCEPTION 'El acta de esta sección está cerrada: no se pueden modificar sus evaluaciones, notas ni asistencia. El coordinador puede reabrirla.';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, academico_oltp;

DROP TRIGGER IF EXISTS trg_bloquear_acta ON academico_oltp.evaluaciones;
DROP TRIGGER IF EXISTS trg_bloquear_acta ON academico_oltp.calificaciones;
DROP TRIGGER IF EXISTS trg_bloquear_acta ON academico_oltp.asistencias;
CREATE TRIGGER trg_bloquear_acta BEFORE INSERT OR UPDATE OR DELETE ON academico_oltp.evaluaciones
    FOR EACH ROW EXECUTE FUNCTION academico_oltp.fn_bloquear_acta_cerrada();
CREATE TRIGGER trg_bloquear_acta BEFORE INSERT OR UPDATE OR DELETE ON academico_oltp.calificaciones
    FOR EACH ROW EXECUTE FUNCTION academico_oltp.fn_bloquear_acta_cerrada();
CREATE TRIGGER trg_bloquear_acta BEFORE INSERT OR UPDATE OR DELETE ON academico_oltp.asistencias
    FOR EACH ROW EXECUTE FUNCTION academico_oltp.fn_bloquear_acta_cerrada();

-- Cerrar: el docente de la sección o el coordinador. SECURITY DEFINER porque el
-- docente no puede escribir en inscripciones ni en secciones; por eso mismo la
-- función valida ella todo lo que el motor ya no validaría.
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
    IF v_rol NOT IN ('rol_docente', 'rol_coordinador') THEN
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

-- Reabrir: solo el coordinador, y con motivo.
CREATE OR REPLACE FUNCTION academico_oltp.reabrir_acta(p_seccion_id INT, p_motivo TEXT)
RETURNS INT AS $$
DECLARE
    v_rol TEXT := COALESCE(NULLIF(current_setting('role', true), 'none'), session_user);
    v_ids BIGINT[];
BEGIN
    IF v_rol <> 'rol_coordinador' THEN
        RAISE EXCEPTION 'Solo el coordinador puede reabrir un acta';
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

REVOKE ALL ON FUNCTION academico_oltp.cerrar_acta(INT) FROM PUBLIC;
REVOKE ALL ON FUNCTION academico_oltp.reabrir_acta(INT, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION academico_oltp.cerrar_acta(INT) TO rol_docente, rol_coordinador;
GRANT EXECUTE ON FUNCTION academico_oltp.reabrir_acta(INT, TEXT) TO rol_coordinador;

-- -----------------------------------------------------------------------------
-- 3. EL DOCENTE PUEDE ELIMINAR EN SUS SECCIONES
-- -----------------------------------------------------------------------------
-- Las políticas docente_propias (script 16) son FOR ALL: el DELETE también queda
-- limitado a sus secciones, y el bloqueo de acta también lo impide si está cerrada.
GRANT DELETE ON academico_oltp.evaluaciones,
                academico_oltp.calificaciones,
                academico_oltp.asistencias TO rol_docente;
