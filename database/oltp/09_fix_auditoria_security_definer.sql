-- =============================================================================
-- UNIVERSIDAD DE EL SALVADOR - FACULTAD MULTIDISCIPLINARIA ORIENTAL
-- CORRECCIÓN: LA AUDITORÍA DE NOTAS IMPEDÍA CORREGIR UNA NOTA
-- =============================================================================
-- Defecto que corrige este script:
--
-- El trigger de auditoría de 01_init_oltp_academico.sql inserta en
-- auditoria.log_cambios_notas cada vez que cambia una nota. La función se creó
-- como SECURITY INVOKER (el valor por omisión), así que ese INSERT se ejecutaba
-- con los permisos del usuario que hacía el UPDATE. Ni rol_docente ni
-- rol_coordinador tienen permiso de escritura sobre la bitácora, de modo que
-- CUALQUIER corrección de nota fallaba:
--
--   rol_docente     -> ERROR: permission denied for schema auditoria
--   rol_coordinador -> ERROR: permission denied for table log_cambios_notas
--
-- Es decir, registrar una nota nueva funcionaba (el trigger es AFTER UPDATE),
-- pero corregir una ya registrada era imposible para los dos roles de la
-- aplicación. La función central del docente estaba rota.
--
-- Por qué la solución NO es conceder escritura sobre la bitácora:
-- si rol_docente pudiera insertar en log_cambios_notas, también podría
-- falsificar o completar el rastro a mano, que es precisamente lo que la
-- bitácora existe para impedir. La bitácora debe ser inescribible para quien es
-- auditado.
--
-- La solución es SECURITY DEFINER: la función se ejecuta con los permisos de su
-- dueño, así que puede escribir en la bitácora aunque quien dispara el trigger
-- no pueda. El rastro se escribe siempre y nadie puede tocarlo por fuera.
-- =============================================================================

SET search_path TO academico_oltp, public;

CREATE OR REPLACE FUNCTION auditoria.fn_auditoria_cambio_nota()
RETURNS TRIGGER AS $$
BEGIN
    IF (OLD.nota IS DISTINCT FROM NEW.nota) THEN
        INSERT INTO auditoria.log_cambios_notas (
            calificacion_id, nota_anterior, nota_nueva, usuario_db
        )
        VALUES (
            OLD.calificacion_id,
            OLD.nota,
            NEW.nota,
            -- Hay que registrar el rol explícitamente. La columna tiene DEFAULT
            -- CURRENT_USER, pero dentro de una función SECURITY DEFINER
            -- CURRENT_USER es el DUEÑO de la función, no quien hizo el cambio:
            -- la bitácora acabaría diciendo 'postgres' en todas las filas y no
            -- serviría para nada.
            --
            -- El GUC 'role' sí conserva el valor del SET ROLE que hizo la
            -- aplicación, que es exactamente el rol del usuario autenticado.
            -- Vale 'none' cuando nadie cambió de rol (por ejemplo una conexión
            -- directa de mantenimiento); en ese caso se registra el usuario de
            -- sesión.
            COALESCE(NULLIF(current_setting('role', true), 'none'), session_user)
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
-- search_path fijo: obligatorio en toda función SECURITY DEFINER. Sin esto,
-- quien llama podría anteponer un esquema propio y hacer que la función
-- resuelva un nombre hacia un objeto suyo, ejecutándolo con los permisos del
-- dueño. Las referencias de arriba además van calificadas con su esquema.
SET search_path = pg_catalog, auditoria;

COMMENT ON FUNCTION auditoria.fn_auditoria_cambio_nota() IS
    'Registra los cambios de nota. SECURITY DEFINER para poder escribir en una bitácora que los roles auditados no pueden tocar.';

-- El trigger de 01_init_oltp_academico.sql sigue siendo válido: CREATE OR
-- REPLACE cambia el cuerpo de la función sin tocar el trigger que la invoca.
-- Solo se recrea si el script se ejecuta sobre una base donde no exista.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_auditoria_cambio_nota' AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER trg_auditoria_cambio_nota
        AFTER UPDATE ON academico_oltp.calificaciones
        FOR EACH ROW
        EXECUTE FUNCTION auditoria.fn_auditoria_cambio_nota();
    END IF;
END
$$;

-- Lectura de la bitácora: el coordinador ya la tenía y se mantiene. El docente
-- no la recibe a propósito — puede ser auditado, no auditor.
GRANT USAGE ON SCHEMA auditoria TO rol_coordinador;
GRANT SELECT ON auditoria.log_cambios_notas TO rol_coordinador;

-- -----------------------------------------------------------------------------
-- RETIRO DE LOS PERMISOS QUE YA NO HACEN FALTA
-- -----------------------------------------------------------------------------
-- Una corrección anterior de este mismo defecto concedió INSERT sobre la
-- bitácora a los dos roles de la aplicación. Funcionaba, pero dejaba que el
-- auditado escribiera entradas a mano en su propio expediente. Con la función
-- en SECURITY DEFINER esos permisos sobran, así que se retiran: el rastro lo
-- escribe el trigger y nadie más.
--
-- Los REVOKE no fallan si el permiso no estaba concedido, de modo que este
-- script sirve igual para bases que nunca lo tuvieron.
REVOKE INSERT ON auditoria.log_cambios_notas FROM rol_coordinador, rol_docente;
REVOKE USAGE, SELECT ON ALL SEQUENCES IN SCHEMA auditoria FROM rol_docente;
REVOKE USAGE ON SCHEMA auditoria FROM rol_docente;
