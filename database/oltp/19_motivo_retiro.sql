-- =============================================================================
-- UNIVERSIDAD DE EL SALVADOR - FACULTAD MULTIDISCIPLINARIA ORIENTAL
-- MOTIVO Y FECHA DEL RETIRO DE UNA INSCRIPCIÓN
-- =============================================================================
-- Retirar es un UPDATE a estado RETIRADO (nunca un DELETE: el historial se
-- conserva). Hasta ahora no quedaba constancia de por qué ni cuándo; sin eso,
-- la tasa de retiro se puede medir pero no explicar. Las inscripciones
-- retiradas antes de este script quedan con motivo NULL («sin registrar»).
-- Idempotente.
-- =============================================================================

ALTER TABLE academico_oltp.inscripciones
    ADD COLUMN IF NOT EXISTS motivo_retiro VARCHAR(200),
    ADD COLUMN IF NOT EXISTS fecha_retiro TIMESTAMP WITH TIME ZONE;

-- Al reactivar una inscripción retirada (nuevo intento) se limpian.
CREATE OR REPLACE FUNCTION academico_oltp.fn_datos_retiro()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.estado_inscripcion = 'RETIRADO' AND OLD.estado_inscripcion IS DISTINCT FROM 'RETIRADO' THEN
        NEW.fecha_retiro := COALESCE(NEW.fecha_retiro, now());
    ELSIF NEW.estado_inscripcion <> 'RETIRADO' THEN
        NEW.motivo_retiro := NULL;
        NEW.fecha_retiro := NULL;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql
SET search_path = pg_catalog, academico_oltp;

DROP TRIGGER IF EXISTS trg_datos_retiro ON academico_oltp.inscripciones;
CREATE TRIGGER trg_datos_retiro BEFORE UPDATE OF estado_inscripcion ON academico_oltp.inscripciones
    FOR EACH ROW EXECUTE FUNCTION academico_oltp.fn_datos_retiro();
