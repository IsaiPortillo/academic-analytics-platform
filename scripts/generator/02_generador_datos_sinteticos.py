"""
UNIVERSIDAD DE EL SALVADOR - FACULTAD MULTIDISCIPLINARIA ORIENTAL
ESPECIALIZACIÓN EN BD & BI 2026
FASE 1 - PUNTO 1.2: GENERACIÓN DE DATOS SINTÉTICOS REALISTAS (OLTP)
"""

import hashlib
import os
import random
import sys
from datetime import date, timedelta
from pathlib import Path
import psycopg2
from psycopg2.extras import execute_values
from faker import Faker
from dotenv import load_dotenv
import numpy as np

# Credenciales desde el archivo .env de la raíz del proyecto (ver .env.example)
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

DB_CONFIG = {
    "dbname": os.getenv("POSTGRES_DB", "academico_db"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD"),
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", 5432))
}

if not DB_CONFIG["password"]:
    sys.exit("ERROR: POSTGRES_PASSWORD no está definida. Copia .env.example a .env y complétalo.")

fake = Faker('es_ES')
random.seed(42)
np.random.seed(42)

# Parámetros de volumen
NUM_ESTUDIANTES = 1500
ANIO_INICIAL = 2022
ANIO_FINAL = 2025

def get_connection():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    return conn

def generar_datos_base(cursor):
    print("[1/5] Insertando Departamentos, Carreras y Materias...")
    
    # 1. Departamentos
    deptos = [
        ('DIA', 'Departamento de Ingeniería y Arquitectura'),
        ('DCE', 'Departamento de Ciencias Económicas'),
        ('DCN', 'Departamento de Ciencias Naturales y Matemática')
    ]
    execute_values(
        cursor,
        "INSERT INTO academico_oltp.departamentos (codigo_departamento, nombre) VALUES %s ON CONFLICT DO NOTHING;",
        deptos
    )
    
    cursor.execute("SELECT departamento_id FROM academico_oltp.departamentos WHERE codigo_departamento = 'DIA'")
    depto_dia_id = cursor.fetchone()[0]

    # 2. Carrera de referencia
    cursor.execute("""
        INSERT INTO academico_oltp.carreras (codigo_carrera, nombre, departamento_id, plan_anio, total_uv_carrera)
        VALUES ('I10515', 'Ingeniería de Sistemas Informáticos', %s, 2020, 175)
        ON CONFLICT (codigo_carrera) DO UPDATE SET nombre = EXCLUDED.nombre
        RETURNING carrera_id;
    """, (depto_dia_id,))
    carrera_id = cursor.fetchone()[0]

    # 3. Materias del Pensum (Tronco principal para grafo posterior en Neo4j)
    materias = [
        # (codigo, nombre, uv, ciclo_plan, carrera_id)
        ('MAT115', 'Matemática I', 4, 1, carrera_id),
        ('PRG115', 'Programación I', 4, 1, carrera_id),
        ('ACA115', 'Álgebra Vectorial y Matrices', 4, 1, carrera_id),
        ('MAT215', 'Matemática II', 4, 2, carrera_id),
        ('PRG215', 'Programación II', 4, 2, carrera_id),
        ('BAD115', 'Bases de Datos I', 4, 3, carrera_id),
        ('PRG315', 'Programación III', 4, 3, carrera_id),
        ('MAT315', 'Matemática III', 4, 3, carrera_id),
        ('BAD215', 'Bases de Datos II', 4, 4, carrera_id),
        ('ADS115', 'Análisis y Diseño de Sistemas I', 4, 4, carrera_id),
        ('SIF115', 'Sistemas de Información', 4, 5, carrera_id),
        ('ADS215', 'Análisis y Diseño de Sistemas II', 4, 5, carrera_id),
        ('DWB115', 'Diseño Web y Aplicaciones', 4, 6, carrera_id),
        ('ARC115', 'Arquitectura de Computadoras', 4, 6, carrera_id),
        ('IAI115', 'Inteligencia Artificial', 4, 7, carrera_id),
        ('BIN115', 'Inteligencia de Negocios', 4, 8, carrera_id)
    ]
    execute_values(
        cursor,
        """INSERT INTO academico_oltp.materias (codigo_materia, nombre, unidades_valorativas, ciclo_plan, carrera_id)
           VALUES %s ON CONFLICT (codigo_materia) DO NOTHING;""",
        materias
    )

    # 4. Docentes
    docentes = [
        (f"DOC-{100 + i}", random.choice(['TITULAR', 'ADJUNTO', 'AUXILIAR', 'HORA CLASE']), depto_dia_id)
        for i in range(1, 21)
    ]
    execute_values(
        cursor,
        """INSERT INTO academico_oltp.docentes (codigo_docente, escalafon, departamento_id)
           VALUES %s ON CONFLICT (codigo_docente) DO NOTHING;""",
        docentes
    )

    # 5. Periodos Académicos
    periodos = []
    for anio in range(ANIO_INICIAL, ANIO_FINAL + 1):
        periodos.append((f"{anio}-I", anio, 'I', date(anio, 2, 1), date(anio, 6, 25), False))
        periodos.append((f"{anio}-II", anio, 'II', date(anio, 8, 1), date(anio, 12, 15), False))
    execute_values(
        cursor,
        """INSERT INTO academico_oltp.periodos_academicos 
           (codigo_periodo, anio, ciclo_romano, fecha_inicio, fecha_fin, activo)
           VALUES %s ON CONFLICT (codigo_periodo) DO NOTHING;""",
        periodos
    )

    return carrera_id

def generar_estudiantes(cursor, carrera_id):
    print(f"[2/5] Generando {NUM_ESTUDIANTES} estudiantes con carnet anonimizado (SHA-256)...")
    estudiantes = []
    for i in range(1, NUM_ESTUDIANTES + 1):
        raw_carnet = f"US{random.randint(20, 25)}{i:05d}"
        carnet_hash = hashlib.sha256(raw_carnet.encode()).hexdigest()
        anio_ing = random.choice([2021, 2022, 2023, 2024])
        trabaja = random.random() < 0.28  # 28% de probabilidad de trabajar
        condicion = random.choices(
            ['REGULAR', 'CONDICIONAL', 'RETIRADO'],
            weights=[0.82, 0.13, 0.05],
            k=1
        )[0]
        estudiantes.append((carnet_hash, anio_ing, carrera_id, trabaja, condicion, True))

    execute_values(
        cursor,
        """INSERT INTO academico_oltp.estudiantes 
           (carnet_hash, anio_ingreso, carrera_id, trabaja, condicion_academica, activo)
           VALUES %s ON CONFLICT (carnet_hash) DO NOTHING;""",
        estudiantes
    )

def generar_secciones_y_evaluaciones(cursor):
    print("[3/5] Ofertando Secciones y configurando Evaluaciones ponderadas...")
    cursor.execute("SELECT materia_id FROM academico_oltp.materias WHERE activo = TRUE")
    materia_ids = [r[0] for r in cursor.fetchall()]

    cursor.execute("SELECT docente_id FROM academico_oltp.docentes WHERE activo = TRUE")
    docente_ids = [r[0] for r in cursor.fetchall()]

    cursor.execute("SELECT periodo_id, fecha_inicio FROM academico_oltp.periodos_academicos")
    periodos = cursor.fetchall()

    secciones_params = []
    for periodo_id, _ in periodos:
        for mat_id in materia_ids:
            num_secciones = random.choices([1, 2, 3], weights=[0.6, 0.3, 0.1])[0]
            for sec_num in range(1, num_secciones + 1):
                doc_id = random.choice(docente_ids)
                turno = random.choice(['MATUTINO', 'VESPERTINO', 'NOCTURNO'])
                aula = f"Lab-C{random.randint(1, 4)}" if 'PRG' in str(mat_id) else f"Edif-B{random.randint(101, 205)}"
                secciones_params.append((mat_id, doc_id, periodo_id, sec_num, turno, aula, 45))

    execute_values(
        cursor,
        """INSERT INTO academico_oltp.secciones 
           (materia_id, docente_id, periodo_id, numero_seccion, turno, aula, cupo_maximo)
           VALUES %s ON CONFLICT DO NOTHING;""",
        secciones_params
    )

    # Evaluaciones estándar por sección (Exactamente 100% de ponderación)
    cursor.execute("SELECT seccion_id, periodo_id FROM academico_oltp.secciones")
    secciones = cursor.fetchall()

    eval_params = []
    for sec_id, _ in secciones:
        base_dias = date(2023, 3, 1)  # Referencial
        eval_params.extend([
            (sec_id, 'Evaluación Parcial 1', 25.00, base_dias + timedelta(days=30)),
            (sec_id, 'Laboratorio Práctico 1', 20.00, base_dias + timedelta(days=50)),
            (sec_id, 'Evaluación Parcial 2', 25.00, base_dias + timedelta(days=80)),
            (sec_id, 'Proyecto Integrador Final', 30.00, base_dias + timedelta(days=110))
        ])

    execute_values(
        cursor,
        """INSERT INTO academico_oltp.evaluaciones (seccion_id, nombre_evaluacion, porcentaje, fecha_evaluacion)
           VALUES %s;""",
        eval_params
    )

def generar_matricula_y_calificaciones(cursor):
    print("[4/5] Simulando inscripciones masivas y calificaciones...")
    cursor.execute("SELECT estudiante_id, trabaja FROM academico_oltp.estudiantes")
    estudiantes = cursor.fetchall()

    cursor.execute("SELECT periodo_id FROM academico_oltp.periodos_academicos ORDER BY anio, ciclo_romano")
    periodo_ids = [r[0] for r in cursor.fetchall()]

    for per_id in periodo_ids:
        cursor.execute("SELECT seccion_id FROM academico_oltp.secciones WHERE periodo_id = %s", (per_id,))
        secciones_disponibles = [r[0] for r in cursor.fetchall()]
        if not secciones_disponibles:
            continue

        inscripciones_batch = []
        # Seleccionar subconjunto de estudiantes activos en este ciclo
        estudiantes_ciclo = random.sample(estudiantes, k=int(len(estudiantes) * 0.75))

        for est_id, trabaja in estudiantes_ciclo:
            # Si trabaja, suele inscribir menos materias
            carga = random.randint(2, 4) if trabaja else random.randint(4, 5)
            carga = min(carga, len(secciones_disponibles))
            sec_elegidas = random.sample(secciones_disponibles, k=carga)

            for sec_id in sec_elegidas:
                intento = random.choices([1, 2, 3], weights=[0.85, 0.12, 0.03])[0]
                estado = random.choices(['INSCRITO', 'FINALIZADO', 'RETIRADO'], weights=[0.05, 0.90, 0.05])[0]
                inscripciones_batch.append((est_id, sec_id, intento, estado))

        execute_values(
            cursor,
            """INSERT INTO academico_oltp.inscripciones (estudiante_id, seccion_id, numero_intento, estado_inscripcion)
               VALUES %s ON CONFLICT (estudiante_id, seccion_id) DO NOTHING;""",
            inscripciones_batch
        )

    # Inserción de notas y asistencias sobre las inscripciones generadas
    print("[5/5] Generando registros de calificaciones y sesiones de asistencia...")
    cursor.execute("""
        SELECT i.inscripcion_id, e.evaluacion_id, est.trabaja, i.numero_intento
        FROM academico_oltp.inscripciones i
        JOIN academico_oltp.secciones s ON i.seccion_id = s.seccion_id
        JOIN academico_oltp.evaluaciones e ON s.seccion_id = e.seccion_id
        JOIN academico_oltp.estudiantes est ON i.estudiante_id = est.estudiante_id
        WHERE i.estado_inscripcion = 'FINALIZADO';
    """)
    registros_eval = cursor.fetchall()

    calificaciones_batch = []
    for insc_id, eval_id, trabaja, intento in registros_eval:
        # Generación realista con distribución Beta/Normal centrada en el sistema salvadoreño (0 a 10)
        # Media de aprobación = 6.0
        media = 6.8
        if trabaja:
            media -= 0.6  # Penalización promedio por restricciones de tiempo
        if intento > 1:
            media -= 0.4

        nota_raw = np.random.normal(loc=media, scale=1.7)
        nota = float(np.clip(round(nota_raw, 2), 0.00, 10.00))
        calificaciones_batch.append((insc_id, eval_id, nota))

        # Inserción en bloques de 15,000 para optimizar el búfer de psycopg2
        if len(calificaciones_batch) >= 15000:
            execute_values(
                cursor,
                """INSERT INTO academico_oltp.calificaciones (inscripcion_id, evaluacion_id, nota)
                   VALUES %s ON CONFLICT DO NOTHING;""",
                calificaciones_batch
            )
            calificaciones_batch.clear()

    if calificaciones_batch:
        execute_values(
            cursor,
            """INSERT INTO academico_oltp.calificaciones (inscripcion_id, evaluacion_id, nota)
               VALUES %s ON CONFLICT DO NOTHING;""",
            calificaciones_batch
        )

    # Inserción de asistencias sintéticas
    cursor.execute("""
        SELECT inscripcion_id, estado_inscripcion 
        FROM academico_oltp.inscripciones 
        WHERE estado_inscripcion = 'FINALIZADO' LIMIT 12000;
    """)
    inscripciones_asist = cursor.fetchall()
    
    asistencias_batch = []
    fecha_base = date(2024, 2, 15)
    for insc_id, _ in inscripciones_asist:
        # 10 sesiones representativas por ciclo
        for dia in range(1, 11):
            fecha_sesion = fecha_base + timedelta(days=dia * 7)
            estado = random.choices(['PRESENTE', 'AUSENTE', 'JUSTIFICADO'], weights=[0.82, 0.14, 0.04])[0]
            asistencias_batch.append((insc_id, fecha_sesion, estado))

    execute_values(
        cursor,
        """INSERT INTO academico_oltp.asistencias (inscripcion_id, fecha_sesion, estado_asistencia)
           VALUES %s ON CONFLICT DO NOTHING;""",
        asistencias_batch
    )

def main():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            carrera_id = generar_datos_base(cur)
            generar_estudiantes(cur, carrera_id)
            generar_secciones_y_evaluaciones(cur)
            generar_matricula_y_calificaciones(cur)
            
            conn.commit()
            print("\n Población completada con éxito:")
            cur.execute("SELECT COUNT(*) FROM academico_oltp.estudiantes;")
            print(f" - Estudiantes: {cur.fetchone()[0]:,}")
            cur.execute("SELECT COUNT(*) FROM academico_oltp.inscripciones;")
            print(f" - Inscripciones: {cur.fetchone()[0]:,}")
            cur.execute("SELECT COUNT(*) FROM academico_oltp.calificaciones;")
            print(f" - Calificaciones: {cur.fetchone()[0]:,}")
            cur.execute("SELECT COUNT(*) FROM academico_oltp.asistencias;")
            print(f" - Registros de Asistencia: {cur.fetchone()[0]:,}")
    except Exception as e:
        conn.rollback()
        print(f"\n Error durante la ejecución del script: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()