-- =============================================================================
-- UNIVERSIDAD DE EL SALVADOR - FACULTAD MULTIDISCIPLINARIA ORIENTAL
-- SEGURIDAD POR FILA: CADA DOCENTE SOLO VE Y ESCRIBE SUS PROPIAS SECCIONES
-- =============================================================================
-- Los GRANT de rol_docente (script 01) son por tabla completa: le permiten
-- escribir notas, evaluaciones y asistencia de CUALQUIER sección. Hasta ahora
-- solo la aplicación filtraba por Seccion.docente_id. Con estas políticas es el
-- motor el que lo impide, aunque la aplicación tenga un error.
--
-- ¿Cómo sabe el motor qué docente es? Todos los docentes comparten el rol
-- rol_docente, así que la aplicación declara el docente de la sesión en cada
-- transacción, junto al SET LOCAL ROLE (app/database.py):
--
--     SELECT set_config('app.docente_id', '<id>', true);   -- true = solo esta transacción
--
-- Si no se declara, docente_sesion() devuelve NULL y rol_docente no ve ni
-- escribe ninguna fila: falla cerrado, igual que el NOINHERIT de rol_app.
--
-- Alcance honesto: protege contra errores de la aplicación (una consulta sin
-- filtro, un id manipulado en un formulario). No protege contra quien controle
-- la propia conexión de rol_app, que puede declarar cualquier docente; esa
-- credencial ya equivale a la aplicación entera y vive solo en el .env.
--
-- El dueño de las tablas (superusuario del contenedor) no está sujeto a RLS, por
-- lo que las funciones SECURITY DEFINER de auditoría siguen funcionando igual.
-- =============================================================================

SET search_path TO academico_oltp, public;

-- Docente declarado para la transacción en curso (NULL si no hay).
CREATE OR REPLACE FUNCTION academico_oltp.docente_sesion()
RETURNS INT
LANGUAGE sql STABLE
AS $$
    SELECT NULLIF(current_setting('app.docente_id', true), '')::INT
$$;

-- Las políticas usan subconsultas en línea y no funciones auxiliares a propósito:
-- una función con SET search_path no se puede «inlinear», PostgreSQL la ejecuta
-- como consulta aparte por cada fila y un conteo de notas pasaba de 4 ms a 26 s.
-- Escritas en línea, el planificador las convierte en semi-joins con índices.
-- Versiones anteriores de este script sí las creaban: se retiran.
DROP POLICY IF EXISTS docente_propias ON academico_oltp.evaluaciones;
DROP POLICY IF EXISTS docente_propias ON academico_oltp.calificaciones;
DROP POLICY IF EXISTS docente_propias ON academico_oltp.asistencias;
DROP FUNCTION IF EXISTS academico_oltp.seccion_es_del_docente(INT);
DROP FUNCTION IF EXISTS academico_oltp.inscripcion_es_del_docente(BIGINT);
DROP FUNCTION IF EXISTS academico_oltp.calificacion_es_del_docente(BIGINT, INT);

REVOKE ALL ON FUNCTION academico_oltp.docente_sesion() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION academico_oltp.docente_sesion() TO rol_docente, rol_coordinador;

-- -----------------------------------------------------------------------------
-- Activar RLS. Al activarla, un rol sin política no ve ninguna fila: por eso el
-- coordinador y el ETL reciben políticas explícitas de acceso completo.
-- -----------------------------------------------------------------------------
ALTER TABLE academico_oltp.evaluaciones   ENABLE ROW LEVEL SECURITY;
ALTER TABLE academico_oltp.calificaciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE academico_oltp.asistencias    ENABLE ROW LEVEL SECURITY;

-- Idempotente: el script se puede volver a ejecutar (scripts/aplicar_ddl_pendiente.sh).
DROP POLICY IF EXISTS coordinador_todo ON academico_oltp.evaluaciones;
DROP POLICY IF EXISTS etl_lectura      ON academico_oltp.evaluaciones;
DROP POLICY IF EXISTS coordinador_todo ON academico_oltp.calificaciones;
DROP POLICY IF EXISTS etl_lectura      ON academico_oltp.calificaciones;
DROP POLICY IF EXISTS coordinador_todo ON academico_oltp.asistencias;
DROP POLICY IF EXISTS etl_lectura      ON academico_oltp.asistencias;

-- Coordinador: sin restricción de fila (sus GRANT ya son completos).
CREATE POLICY coordinador_todo ON academico_oltp.evaluaciones
    FOR ALL TO rol_coordinador USING (true) WITH CHECK (true);
CREATE POLICY coordinador_todo ON academico_oltp.calificaciones
    FOR ALL TO rol_coordinador USING (true) WITH CHECK (true);
CREATE POLICY coordinador_todo ON academico_oltp.asistencias
    FOR ALL TO rol_coordinador USING (true) WITH CHECK (true);

-- ETL: lee todo (sus GRANT siguen siendo solo SELECT).
CREATE POLICY etl_lectura ON academico_oltp.evaluaciones
    FOR SELECT TO rol_etl USING (true);
CREATE POLICY etl_lectura ON academico_oltp.calificaciones
    FOR SELECT TO rol_etl USING (true);
CREATE POLICY etl_lectura ON academico_oltp.asistencias
    FOR SELECT TO rol_etl USING (true);

-- Docente: lee y escribe solo filas de sus secciones. USING filtra lo que ve y
-- lo que puede modificar; WITH CHECK impide que la fila nueva (o la fila tras un
-- UPDATE, p. ej. cambiando seccion_id) quede en una sección ajena.
CREATE POLICY docente_propias ON academico_oltp.evaluaciones
    FOR ALL TO rol_docente
    USING (seccion_id IN (
        SELECT s.seccion_id FROM academico_oltp.secciones s
        WHERE s.docente_id = academico_oltp.docente_sesion()))
    WITH CHECK (seccion_id IN (
        SELECT s.seccion_id FROM academico_oltp.secciones s
        WHERE s.docente_id = academico_oltp.docente_sesion()));

CREATE POLICY docente_propias ON academico_oltp.asistencias
    FOR ALL TO rol_docente
    USING (inscripcion_id IN (
        SELECT i.inscripcion_id FROM academico_oltp.inscripciones i
        JOIN academico_oltp.secciones s ON s.seccion_id = i.seccion_id
        WHERE s.docente_id = academico_oltp.docente_sesion()))
    WITH CHECK (inscripcion_id IN (
        SELECT i.inscripcion_id FROM academico_oltp.inscripciones i
        JOIN academico_oltp.secciones s ON s.seccion_id = i.seccion_id
        WHERE s.docente_id = academico_oltp.docente_sesion()));

-- Una calificación es del docente si la inscripción Y la evaluación son de la
-- MISMA sección suya: así tampoco se puede cruzar una evaluación de una sección
-- con un estudiante de otra.
CREATE POLICY docente_propias ON academico_oltp.calificaciones
    FOR ALL TO rol_docente
    USING ((inscripcion_id, evaluacion_id) IN (
        SELECT i.inscripcion_id, e.evaluacion_id
        FROM academico_oltp.secciones s
        JOIN academico_oltp.inscripciones i ON i.seccion_id = s.seccion_id
        JOIN academico_oltp.evaluaciones e ON e.seccion_id = s.seccion_id
        WHERE s.docente_id = academico_oltp.docente_sesion()))
    WITH CHECK ((inscripcion_id, evaluacion_id) IN (
        SELECT i.inscripcion_id, e.evaluacion_id
        FROM academico_oltp.secciones s
        JOIN academico_oltp.inscripciones i ON i.seccion_id = s.seccion_id
        JOIN academico_oltp.evaluaciones e ON e.seccion_id = s.seccion_id
        WHERE s.docente_id = academico_oltp.docente_sesion()));
