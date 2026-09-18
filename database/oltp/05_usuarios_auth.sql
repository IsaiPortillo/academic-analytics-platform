-- =============================================================================
-- UNIVERSIDAD DE EL SALVADOR - FACULTAD MULTIDISCIPLINARIA ORIENTAL
-- CURSO DE ESPECIALIZACIÓN: ADMINISTRACIÓN DE BASES DE DATOS E INTELIGENCIA DE NEGOCIOS
-- FASE 2 - PUNTO 2.1: AUTENTICACIÓN DE LA APLICACIÓN TRANSACCIONAL
-- =============================================================================
-- Los roles rol_coordinador / rol_docente definidos en 01_init_oltp_academico.sql
-- son roles del MOTOR, no personas. Esta tabla asocia credenciales de aplicación
-- con uno de esos roles; la aplicación ejecuta SET LOCAL ROLE tras autenticar,
-- de modo que los GRANT del motor son los que gobiernan cada operación.
-- =============================================================================

SET search_path TO academico_oltp, public;

-- -----------------------------------------------------------------------------
-- 1. TABLA DE USUARIOS DE APLICACIÓN
-- -----------------------------------------------------------------------------
CREATE TABLE academico_oltp.usuarios (
    usuario_id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,          -- bcrypt
    nombre_completo VARCHAR(120) NOT NULL,
    rol_db VARCHAR(30) NOT NULL CHECK (rol_db IN ('rol_coordinador', 'rol_docente')),
    docente_id INT NULL,                          -- solo aplica si rol_db = 'rol_docente'
    activo BOOLEAN DEFAULT TRUE,
    creado_en TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_usuario_docente FOREIGN KEY (docente_id)
        REFERENCES academico_oltp.docentes (docente_id) ON DELETE RESTRICT,
    -- Un usuario docente debe estar vinculado a su registro en la tabla docentes
    CONSTRAINT chk_docente_vinculado CHECK (
        (rol_db = 'rol_docente' AND docente_id IS NOT NULL)
        OR (rol_db = 'rol_coordinador' AND docente_id IS NULL)
    )
);

CREATE INDEX idx_usuarios_username_activo
    ON academico_oltp.usuarios (username) WHERE activo = TRUE;

-- -----------------------------------------------------------------------------
-- 2. PERMISOS SOBRE LA NUEVA TABLA
-- -----------------------------------------------------------------------------
-- El GRANT ... ON ALL TABLES IN SCHEMA del script 01 solo afectó a las tablas
-- existentes en ese momento: no cubre tablas creadas después, por lo que la
-- tabla usuarios necesita sus propias concesiones explícitas.

GRANT SELECT, INSERT, UPDATE, DELETE ON academico_oltp.usuarios TO rol_coordinador;
GRANT USAGE, SELECT ON SEQUENCE academico_oltp.usuarios_usuario_id_seq TO rol_coordinador;

-- El docente solo puede leer su propio registro (la app filtra por usuario_id)
GRANT SELECT ON academico_oltp.usuarios TO rol_docente;
