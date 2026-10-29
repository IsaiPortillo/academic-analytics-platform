-- =============================================================================
-- UNIVERSIDAD DE EL SALVADOR - FACULTAD MULTIDISCIPLINARIA ORIENTAL
-- ADMINISTRACIÓN DE USUARIOS DESDE LA APLICACIÓN
-- =============================================================================
-- El coordinador ya tenía todos los permisos sobre academico_oltp.usuarios
-- (script 05). Faltaba lo que necesita cualquier usuario sobre SU cuenta:
--   - cambiar su propia contraseña, sin dar al docente UPDATE sobre la tabla
--     (podría cambiar la de otros o su propio rol);
--   - que un restablecimiento obligue a cambiar la contraseña temporal;
--   - registrar el último acceso, que escribe rol_app al iniciar sesión.
-- Idempotente.
-- =============================================================================

SET search_path TO academico_oltp, public;

ALTER TABLE academico_oltp.usuarios
    ADD COLUMN IF NOT EXISTS debe_cambiar_password BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS ultimo_acceso TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS password_cambiado_en TIMESTAMP WITH TIME ZONE;

-- Cambiar la propia contraseña. La aplicación verifica antes la contraseña
-- actual y declara quién es (app.usuario_id, igual que app.docente_id en el
-- script 16). La función solo toca la fila de ese usuario y solo esas columnas.
CREATE OR REPLACE FUNCTION academico_oltp.cambiar_password_propio(p_hash TEXT)
RETURNS VOID AS $$
DECLARE
    v_usuario INT := NULLIF(current_setting('app.usuario_id', true), '')::INT;
BEGIN
    IF v_usuario IS NULL THEN
        RAISE EXCEPTION 'Sesión sin usuario declarado';
    END IF;
    IF p_hash IS NULL OR p_hash !~ '^\$2[aby]\$\d\d\$.{53}$' THEN
        RAISE EXCEPTION 'Hash de contraseña no válido';   -- solo bcrypt
    END IF;
    UPDATE academico_oltp.usuarios
    SET password_hash = p_hash, debe_cambiar_password = FALSE, password_cambiado_en = now()
    WHERE usuario_id = v_usuario AND activo;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Cuenta no encontrada o desactivada';
    END IF;
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, academico_oltp;

-- Último acceso: lo llama rol_app justo después de un inicio de sesión válido,
-- antes de cambiar de rol. Solo escribe esa columna.
CREATE OR REPLACE FUNCTION academico_oltp.registrar_acceso(p_usuario_id INT)
RETURNS VOID AS $$
    UPDATE academico_oltp.usuarios SET ultimo_acceso = now()
    WHERE usuario_id = p_usuario_id AND activo;
$$ LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, academico_oltp;

REVOKE ALL ON FUNCTION academico_oltp.cambiar_password_propio(TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION academico_oltp.registrar_acceso(INT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION academico_oltp.cambiar_password_propio(TEXT) TO rol_docente, rol_coordinador;

DO $$
DECLARE
    v_app TEXT;
BEGIN
    -- rol_app puede llamarse distinto (APP_DB_USER); se busca el miembro LOGIN
    -- de rol_coordinador con NOINHERIT, que es como lo crea el script 06.
    FOR v_app IN
        SELECT r.rolname FROM pg_roles r
        JOIN pg_auth_members m ON m.member = r.oid
        JOIN pg_roles g ON g.oid = m.roleid AND g.rolname = 'rol_coordinador'
        WHERE r.rolcanlogin AND NOT r.rolinherit
    LOOP
        EXECUTE format('GRANT EXECUTE ON FUNCTION academico_oltp.registrar_acceso(INT) TO %I', v_app);
    END LOOP;
END
$$;
