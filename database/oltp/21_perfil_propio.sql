-- =============================================================================
-- UNIVERSIDAD DE EL SALVADOR - FACULTAD MULTIDISCIPLINARIA ORIENTAL
-- ACTUALIZAR LOS DATOS DEL PROPIO PERFIL (pantalla «Mi cuenta»)
-- =============================================================================
-- Igual que cambiar_password_propio() (script 18): el docente no tiene UPDATE
-- sobre usuarios (podría cambiar el rol, la vinculación o la cuenta de otros),
-- así que lo único que puede editar de su cuenta pasa por una función del motor
-- que toca una sola fila (la de la sesión: app.usuario_id) y una sola columna.
-- Hoy esa columna es el nombre completo; el usuario, el rol y el docente
-- vinculado solo los cambia el coordinador desde Usuarios.
-- Idempotente.
-- =============================================================================

SET search_path TO academico_oltp, public;

CREATE OR REPLACE FUNCTION academico_oltp.actualizar_perfil_propio(p_nombre TEXT)
RETURNS VOID AS $$
DECLARE
    v_usuario INT := NULLIF(current_setting('app.usuario_id', true), '')::INT;
    v_nombre  TEXT := btrim(regexp_replace(COALESCE(p_nombre, ''), '\s+', ' ', 'g'));
BEGIN
    IF v_usuario IS NULL THEN
        RAISE EXCEPTION 'Sesión sin usuario declarado';
    END IF;
    IF char_length(v_nombre) < 3 OR char_length(v_nombre) > 120 THEN
        RAISE EXCEPTION 'El nombre debe tener entre 3 y 120 caracteres';
    END IF;
    UPDATE academico_oltp.usuarios
    SET nombre_completo = v_nombre
    WHERE usuario_id = v_usuario AND activo;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Cuenta no encontrada o desactivada';
    END IF;
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, academico_oltp;

REVOKE ALL ON FUNCTION academico_oltp.actualizar_perfil_propio(TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION academico_oltp.actualizar_perfil_propio(TEXT) TO rol_docente, rol_coordinador;
