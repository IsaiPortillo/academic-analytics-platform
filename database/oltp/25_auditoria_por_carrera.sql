-- =============================================================================
-- UNIVERSIDAD DE EL SALVADOR - FACULTAD MULTIDISCIPLINARIA ORIENTAL
-- LA BITÁCORA TAMBIÉN SE ACOTA A LA CARRERA DEL COORDINADOR
-- =============================================================================
-- Los scripts 23 y 24 acotaron al coordinador de carrera en el OLTP y en el
-- almacén, pero la auditoría quedó fuera: las dos bitácoras no tenían seguridad
-- por fila y rol_coordinador tiene SELECT sobre ellas, así que la pantalla
-- /auditoria le mostraba los cambios de nota y los cierres de acta de TODAS las
-- carreras. El recorte servía para los datos y se podía esquivar leyendo su
-- rastro.
--
--   rol_admin        ve toda la bitácora
--   rol_coordinador  ve las filas de su carrera
--   (nadie escribe)  las escriben funciones SECURITY DEFINER; ningún rol de la
--                    aplicación tiene INSERT, UPDATE ni DELETE, y este script no
--                    cambia eso
--
-- Las filas que no se pueden atribuir a una carrera NO las ve el coordinador:
--   - log_cambios_notas anteriores al script 17 tienen inscripcion_id NULL;
--   - log_actas de una sección que ya se borró (posible desde el script 22, que
--     quitó la clave ajena a propósito para que el rastro sobreviva).
-- El admin sí las ve: es quien tiene que poder auditar lo que no encaja.
--
-- Políticas en línea, por la razón del script 16 (una función con
-- SET search_path no se puede «inlinear» y se ejecutaría por cada fila).
--
-- Idempotente.
-- =============================================================================

ALTER TABLE auditoria.log_cambios_notas ENABLE ROW LEVEL SECURITY;
ALTER TABLE auditoria.log_actas         ENABLE ROW LEVEL SECURITY;

-- El dueño (postgres) no está sujeto a RLS, así que las funciones
-- SECURITY DEFINER que escriben la bitácora siguen funcionando igual.

DROP POLICY IF EXISTS admin_todo ON auditoria.log_cambios_notas;
CREATE POLICY admin_todo ON auditoria.log_cambios_notas FOR SELECT TO rol_admin
    USING (true);

DROP POLICY IF EXISTS coordinador_carrera ON auditoria.log_cambios_notas;
CREATE POLICY coordinador_carrera ON auditoria.log_cambios_notas FOR SELECT TO rol_coordinador
    USING (inscripcion_id IN (SELECT i.inscripcion_id FROM academico_oltp.inscripciones i
                              JOIN academico_oltp.secciones s ON s.seccion_id = i.seccion_id
                              JOIN academico_oltp.materias m ON m.materia_id = s.materia_id
                              WHERE m.carrera_id = academico_oltp.carrera_sesion()));

DROP POLICY IF EXISTS admin_todo ON auditoria.log_actas;
CREATE POLICY admin_todo ON auditoria.log_actas FOR SELECT TO rol_admin
    USING (true);

DROP POLICY IF EXISTS coordinador_carrera ON auditoria.log_actas;
CREATE POLICY coordinador_carrera ON auditoria.log_actas FOR SELECT TO rol_coordinador
    USING (seccion_id IN (SELECT s.seccion_id FROM academico_oltp.secciones s
                          JOIN academico_oltp.materias m ON m.materia_id = s.materia_id
                          WHERE m.carrera_id = academico_oltp.carrera_sesion()));

-- La política del coordinador consulta inscripciones, secciones y materias, que
-- a su vez tienen RLS (script 23). Eso es deseable: se acota dos veces por el
-- mismo criterio y no hay forma de que una vía dé más que la otra.
