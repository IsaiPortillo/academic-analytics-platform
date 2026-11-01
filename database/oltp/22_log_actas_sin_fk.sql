-- =============================================================================
-- UNIVERSIDAD DE EL SALVADOR - FACULTAD MULTIDISCIPLINARIA ORIENTAL
-- LA BITÁCORA DE ACTAS NO DEBE ANCLAR LA SECCIÓN QUE AUDITA
-- =============================================================================
-- auditoria.log_actas se creó (script 17) con una clave ajena a secciones sin
-- ON DELETE, es decir NO ACTION. Consecuencia: en cuanto se cierra un acta,
-- borrar esa sección queda prohibido, y el generador de datos lo hace al
-- reiniciar:
--
--   ERROR:  update or delete on table "secciones" violates foreign key
--           constraint "log_actas_seccion_id_fkey" on table "log_actas"
--   DETAIL:  Key (seccion_id)=(195) is still referenced from table "log_actas".
--
-- No se veía porque la tabla estaba vacía en todas las máquinas: aparece la
-- primera vez que alguien cierra un acta y después regenera los datos, que es
-- justamente lo que se hace al ensayar la demostración. Y
-- «ALTER TABLE ... DISABLE TRIGGER USER», que el generador usa antes de borrar,
-- no desactiva claves ajenas: son restricciones del sistema.
--
-- Se quita la clave ajena, igual que en auditoria.log_cambios_notas, que guarda
-- calificacion_id como entero suelto a propósito. El criterio es el mismo para
-- las dos bitácoras: el rastro NO depende de que la fila auditada siga
-- existiendo. Si borrar lo auditado borrara o bloqueara el rastro, el rastro no
-- serviría de nada.
--
-- Lo que se pierde es integridad referencial: una fila puede apuntar a una
-- sección que ya no existe. Eso es deseable en una bitácora de solo-agregar; el
-- índice por seccion_id sigue sirviendo para consultarla.
--
-- Idempotente. El script 17 ya no crea la clave ajena, así que una instalación
-- nueva nace bien y aquí no queda nada por hacer.
-- =============================================================================

ALTER TABLE auditoria.log_actas DROP CONSTRAINT IF EXISTS log_actas_seccion_id_fkey;

COMMENT ON COLUMN auditoria.log_actas.seccion_id IS
    'Sección auditada. Sin clave ajena a propósito: la bitácora sobrevive al '
    'borrado de la sección (mismo criterio que log_cambios_notas.calificacion_id).';
