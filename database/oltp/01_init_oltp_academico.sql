-- =============================================================================
-- UNIVERSIDAD DE EL SALVADOR - FACULTAD MULTIDISCIPLINARIA ORIENTAL
-- DEPARTAMENTO DE INGENIERÍA Y ARQUITECTURA
-- CURSO DE ESPECIALIZACIÓN: ADMINISTRACIÓN DE BASES DE DATOS E INTELIGENCIA DE NEGOCIOS
-- PROYECTO: GESTIÓN ACADÉMICA Y ANALÍTICA DE RENDIMIENTO ESTUDIANTIL
-- FASE 1: DEFINICIÓN DE ESTRUCTURAS OPERACIONALES (OLTP)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. CONFIGURACIÓN INICIAL Y ESQUEMAS
-- -----------------------------------------------------------------------------
CREATE SCHEMA academico_oltp;
CREATE SCHEMA auditoria;

SET search_path TO academico_oltp, public;

-- Habilitar extensión para generación de identificadores UUID si se requiere
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- -----------------------------------------------------------------------------
-- 2. TABLAS DE CATÁLOGOS BASE Y PLAN DE ESTUDIOS
-- -----------------------------------------------------------------------------

-- Departamentos académicos (Ej: Ciencias de la Computación, Matemática, etc.)
CREATE TABLE academico_oltp.departamentos (
    departamento_id SERIAL PRIMARY KEY,
    codigo_departamento VARCHAR(10) NOT NULL UNIQUE,
    nombre VARCHAR(100) NOT NULL,
    creado_en TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Planes de estudio / Carreras
CREATE TABLE academico_oltp.carreras (
    carrera_id SERIAL PRIMARY KEY,
    codigo_carrera VARCHAR(10) NOT NULL UNIQUE,
    nombre VARCHAR(120) NOT NULL,
    departamento_id INT NOT NULL,
    plan_anio INT NOT NULL CHECK (plan_anio >= 1990 AND plan_anio <= 2100),
    total_uv_carrera INT NOT NULL CHECK (total_uv_carrera > 0),
    activo BOOLEAN DEFAULT TRUE,
    CONSTRAINT fk_carrera_departamento FOREIGN KEY (departamento_id)
        REFERENCES academico_oltp.departamentos (departamento_id) ON DELETE RESTRICT
);

-- Asignaturas / Materias del pensum
CREATE TABLE academico_oltp.materias (
    materia_id SERIAL PRIMARY KEY,
    codigo_materia VARCHAR(15) NOT NULL UNIQUE,
    nombre VARCHAR(150) NOT NULL,
    unidades_valorativas INT NOT NULL CHECK (unidades_valorativas BETWEEN 1 AND 10),
    ciclo_plan INT NOT NULL CHECK (ciclo_plan BETWEEN 1 AND 12),
    carrera_id INT NOT NULL,
    activo BOOLEAN DEFAULT TRUE,
    CONSTRAINT fk_materia_carrera FOREIGN KEY (carrera_id)
        REFERENCES academico_oltp.carreras (carrera_id) ON DELETE RESTRICT
);

-- -----------------------------------------------------------------------------
-- 3. ACTORES: ESTUDIANTES Y DOCENTES
-- -----------------------------------------------------------------------------

-- Estudiantes (con hashing/anonimización contemplada desde el diseño)
CREATE TABLE academico_oltp.estudiantes (
    estudiante_id SERIAL PRIMARY KEY,
    carnet_hash VARCHAR(64) NOT NULL UNIQUE, -- SHA-256 o identificador enmascarado
    anio_ingreso INT NOT NULL CHECK (anio_ingreso >= 2000 AND anio_ingreso <= 2100),
    carrera_id INT NOT NULL,
    trabaja BOOLEAN DEFAULT FALSE,
    condicion_academica VARCHAR(20) DEFAULT 'REGULAR' CHECK (condicion_academica IN ('REGULAR', 'CONDICIONAL', 'EGRESADO', 'RETIRADO')),
    activo BOOLEAN DEFAULT TRUE,
    creado_en TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_estudiante_carrera FOREIGN KEY (carrera_id)
        REFERENCES academico_oltp.carreras (carrera_id) ON DELETE RESTRICT
);

-- Docentes
CREATE TABLE academico_oltp.docentes (
    docente_id SERIAL PRIMARY KEY,
    codigo_docente VARCHAR(20) NOT NULL UNIQUE,
    escalafon VARCHAR(50) NOT NULL CHECK (escalafon IN ('HORA CLASE', 'AUXILIAR', 'ADJUNTO', 'TITULAR')),
    departamento_id INT NOT NULL,
    activo BOOLEAN DEFAULT TRUE,
    creado_en TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_docente_departamento FOREIGN KEY (departamento_id)
        REFERENCES academico_oltp.departamentos (departamento_id) ON DELETE RESTRICT
);

-- -----------------------------------------------------------------------------
-- 4. GESTIÓN DE CICLOS, SECCIONES Y MATRÍCULAS
-- -----------------------------------------------------------------------------

-- Periodos académicos (Ciclos lectivos: Ciclo I, Ciclo II)
CREATE TABLE academico_oltp.periodos_academicos (
    periodo_id SERIAL PRIMARY KEY,
    codigo_periodo VARCHAR(10) NOT NULL UNIQUE, -- Ej: '2026-I', '2026-II'
    anio INT NOT NULL CHECK (anio >= 2000 AND anio <= 2100),
    ciclo_romano VARCHAR(5) NOT NULL CHECK (ciclo_romano IN ('I', 'II', 'EXTRA')),
    fecha_inicio DATE NOT NULL,
    fecha_fin DATE NOT NULL,
    activo BOOLEAN DEFAULT FALSE,
    CONSTRAINT chk_rango_fechas_periodo CHECK (fecha_fin > fecha_inicio)
);

-- Secciones / Cursos ofertados en un ciclo
CREATE TABLE academico_oltp.secciones (
    seccion_id SERIAL PRIMARY KEY,
    materia_id INT NOT NULL,
    docente_id INT NOT NULL,
    periodo_id INT NOT NULL,
    numero_seccion INT NOT NULL CHECK (numero_seccion > 0),
    turno VARCHAR(15) NOT NULL CHECK (turno IN ('MATUTINO', 'VESPERTINO', 'NOCTURNO')),
    aula VARCHAR(30) NOT NULL,
    cupo_maximo INT NOT NULL CHECK (cupo_maximo > 0),
    creado_en TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_materia_periodo_seccion UNIQUE (materia_id, periodo_id, numero_seccion),
    CONSTRAINT fk_seccion_materia FOREIGN KEY (materia_id)
        REFERENCES academico_oltp.materias (materia_id) ON DELETE RESTRICT,
    CONSTRAINT fk_seccion_docente FOREIGN KEY (docente_id)
        REFERENCES academico_oltp.docentes (docente_id) ON DELETE RESTRICT,
    CONSTRAINT fk_seccion_periodo FOREIGN KEY (periodo_id)
        REFERENCES academico_oltp.periodos_academicos (periodo_id) ON DELETE RESTRICT
);

-- Inscripciones / Matrícula de materias por estudiante
CREATE TABLE academico_oltp.inscripciones (
    inscripcion_id BIGSERIAL PRIMARY KEY,
    estudiante_id INT NOT NULL,
    seccion_id INT NOT NULL,
    fecha_inscripcion TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    numero_intento INT NOT NULL DEFAULT 1 CHECK (numero_intento >= 1),
    estado_inscripcion VARCHAR(20) DEFAULT 'INSCRITO' CHECK (estado_inscripcion IN ('INSCRITO', 'RETIRADO', 'FINALIZADO')),
    CONSTRAINT uq_estudiante_seccion UNIQUE (estudiante_id, seccion_id),
    CONSTRAINT fk_inscripcion_estudiante FOREIGN KEY (estudiante_id)
        REFERENCES academico_oltp.estudiantes (estudiante_id) ON DELETE CASCADE,
    CONSTRAINT fk_inscripcion_seccion FOREIGN KEY (seccion_id)
        REFERENCES academico_oltp.secciones (seccion_id) ON DELETE RESTRICT
);

-- -----------------------------------------------------------------------------
-- 5. EVALUACIONES, CALIFICACIONES Y CONTROL DE ASISTENCIA
-- -----------------------------------------------------------------------------

-- Planificación de evaluaciones por sección (Ej: Parcial 1, Laboratorio 1)
CREATE TABLE academico_oltp.evaluaciones (
    evaluacion_id SERIAL PRIMARY KEY,
    seccion_id INT NOT NULL,
    nombre_evaluacion VARCHAR(100) NOT NULL,
    porcentaje NUMERIC(5,2) NOT NULL CHECK (porcentaje > 0.00 AND porcentaje <= 100.00),
    fecha_evaluacion DATE NOT NULL,
    CONSTRAINT fk_evaluacion_seccion FOREIGN KEY (seccion_id)
        REFERENCES academico_oltp.secciones (seccion_id) ON DELETE CASCADE
);

-- Calificaciones individuales
CREATE TABLE academico_oltp.calificaciones (
    calificacion_id BIGSERIAL PRIMARY KEY,
    inscripcion_id BIGINT NOT NULL,
    evaluacion_id INT NOT NULL,
    nota NUMERIC(4,2) NOT NULL CHECK (nota >= 0.00 AND nota <= 10.00),
    fecha_registro TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_inscripcion_evaluacion UNIQUE (inscripcion_id, evaluacion_id),
    CONSTRAINT fk_calificacion_inscripcion FOREIGN KEY (inscripcion_id)
        REFERENCES academico_oltp.inscripciones (inscripcion_id) ON DELETE CASCADE,
    CONSTRAINT fk_calificacion_evaluacion FOREIGN KEY (evaluacion_id)
        REFERENCES academico_oltp.evaluaciones (evaluacion_id) ON DELETE CASCADE
);

-- Registro diario/periódico de asistencia
CREATE TABLE academico_oltp.asistencias (
    asistencia_id BIGSERIAL PRIMARY KEY,
    inscripcion_id BIGINT NOT NULL,
    fecha_sesion DATE NOT NULL,
    estado_asistencia VARCHAR(15) NOT NULL CHECK (estado_asistencia IN ('PRESENTE', 'AUSENTE', 'JUSTIFICADO')),
    CONSTRAINT uq_inscripcion_sesion UNIQUE (inscripcion_id, fecha_sesion),
    CONSTRAINT fk_asistencia_inscripcion FOREIGN KEY (inscripcion_id)
        REFERENCES academico_oltp.inscripciones (inscripcion_id) ON DELETE CASCADE
);

-- -----------------------------------------------------------------------------
-- 6. AUDITORÍA Y DISPARADORES (TRIGGERS) DE INTEGRIDAD
-- -----------------------------------------------------------------------------

-- A. Regla de negocio: La suma de porcentajes de evaluación en una sección no debe superar el 100%
CREATE OR REPLACE FUNCTION academico_oltp.fn_validar_ponderacion_evaluacion()
RETURNS TRIGGER AS $$
DECLARE
    v_total_ponderacion NUMERIC(5,2);
BEGIN
    SELECT COALESCE(SUM(porcentaje), 0.00)
    INTO v_total_ponderacion
    FROM academico_oltp.evaluaciones
    WHERE seccion_id = NEW.seccion_id
      AND evaluacion_id <> COALESCE(NEW.evaluacion_id, -1);

    IF (v_total_ponderacion + NEW.porcentaje) > 100.00 THEN
        RAISE EXCEPTION 'Regla violada: La ponderación total de las evaluaciones para la sección % no puede exceder el 100.00%% (Ponderación actual: %, Nueva ponderación propuesta: %)',
            NEW.seccion_id, v_total_ponderacion, (v_total_ponderacion + NEW.porcentaje);
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_validar_ponderacion_evaluacion
BEFORE INSERT OR UPDATE ON academico_oltp.evaluaciones
FOR EACH ROW
EXECUTE FUNCTION academico_oltp.fn_validar_ponderacion_evaluacion();

-- B. Tabla y trigger de auditoría de calificaciones (Trazabilidad de cambios de nota)
CREATE TABLE auditoria.log_cambios_notas (
    log_id BIGSERIAL PRIMARY KEY,
    calificacion_id BIGINT NOT NULL,
    nota_anterior NUMERIC(4,2),
    nota_nueva NUMERIC(4,2),
    usuario_db VARCHAR(50) DEFAULT CURRENT_USER,
    fecha_modificacion TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE OR REPLACE FUNCTION auditoria.fn_auditoria_cambio_nota()
RETURNS TRIGGER AS $$
BEGIN
    IF (OLD.nota <> NEW.nota) THEN
        INSERT INTO auditoria.log_cambios_notas (calificacion_id, nota_anterior, nota_nueva)
        VALUES (OLD.calificacion_id, OLD.nota, NEW.nota);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_auditoria_cambio_nota
AFTER UPDATE ON academico_oltp.calificaciones
FOR EACH ROW
EXECUTE FUNCTION auditoria.fn_auditoria_cambio_nota();

-- -----------------------------------------------------------------------------
-- 7. ROLES Y POLÍTICAS DE ACCESO (RBAC) - SECCIÓN 4.2
-- -----------------------------------------------------------------------------

-- Crear roles si no existen
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'rol_coordinador') THEN
        CREATE ROLE rol_coordinador;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'rol_docente') THEN
        CREATE ROLE rol_docente;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'rol_etl') THEN
        CREATE ROLE rol_etl;
    END IF;
END
$$;

-- Permisos de esquema
GRANT USAGE ON SCHEMA academico_oltp TO rol_coordinador, rol_docente, rol_etl;
GRANT USAGE ON SCHEMA auditoria TO rol_coordinador;

-- Rol Coordinador: Control total sobre el esquema operacional
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA academico_oltp TO rol_coordinador;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA academico_oltp TO rol_coordinador;
GRANT SELECT ON ALL TABLES IN SCHEMA auditoria TO rol_coordinador;

-- Rol Docente: Gestión de evaluaciones, calificaciones y asistencias
GRANT SELECT ON academico_oltp.departamentos, academico_oltp.carreras, 
                academico_oltp.materias, academico_oltp.periodos_academicos, 
                academico_oltp.secciones, academico_oltp.estudiantes, 
                academico_oltp.inscripciones TO rol_docente;

GRANT SELECT, INSERT, UPDATE ON academico_oltp.evaluaciones, 
                                 academico_oltp.calificaciones, 
                                 academico_oltp.asistencias TO rol_docente;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA academico_oltp TO rol_docente;

-- Rol ETL: Solo lectura para extracción sin alterar el estado operacional
GRANT SELECT ON ALL TABLES IN SCHEMA academico_oltp TO rol_etl;