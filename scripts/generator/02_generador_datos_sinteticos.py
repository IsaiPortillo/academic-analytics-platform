"""
UNIVERSIDAD DE EL SALVADOR - FACULTAD MULTIDISCIPLINARIA ORIENTAL
ESPECIALIZACIÓN EN BD & BI 2026
FASE 1 - PUNTO 1.2: GENERACIÓN DE DATOS SINTÉTICOS (OLTP)

Puebla la base operacional con datos que se parecen a los de la FMO-UES: ocho
departamentos, doce carreras con su plan de estudios, docentes, estudiantes que
avanzan por su plan, secciones por ciclo, evaluaciones (un parcial corto por módulo en
la mayoría), notas y asistencia. Dos ciclos al año y cuatro módulos dentro de cada uno.
Todo es sintético: ningún dato corresponde a una persona real. Ver catalogo_ues.py (qué
es público y qué es inventado) y simulacion_ues.py (cómo se simula).

Uso (desde la raíz del proyecto, con el .env completo):

    python scripts/generator/02_generador_datos_sinteticos.py                 # base vacía
    python scripts/generator/02_generador_datos_sinteticos.py --reiniciar     # reemplaza lo anterior

--reiniciar borra lo transaccional (estudiantes, secciones, evaluaciones, inscripciones,
notas, asistencia) y lo vuelve a generar. Conserva los catálogos que ya existían (los
docentes DOC-101 a DOC-120, con sus cuentas de usuario, y las materias del plan de
Sistemas), las cuentas de usuario, los costos y las bitácoras de auditoría. Después hay
que recargar el almacén de datos (python -m etl.carga) y, si cambió la malla, el grafo
(python database/nosql/03_cargar_grafo_neo4j.py --reiniciar).
"""

import argparse
import os
import random
import sys
from datetime import date, datetime, time
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_values

sys.path.insert(0, str(Path(__file__).resolve().parent))
import catalogo_ues as cat  # noqa: E402
import simulacion_ues as sim  # noqa: E402

# Credenciales desde el archivo .env de la raíz del proyecto (ver .env.example)
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

SEMILLA = 42
TABLAS_TRANSACCIONALES = ("calificaciones", "asistencias", "inscripciones", "evaluaciones", "secciones")


def configuracion() -> dict:
    return {
        "dbname": os.getenv("POSTGRES_DB", "academico_db"),
        "user": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD"),
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", 5432)),
    }


def preparar_catalogos(cur) -> dict:
    """Departamentos, carreras, materias, docentes y períodos. Idempotente: actualiza lo que ya
    existía y agrega lo que falta. Devuelve los identificadores que necesita la carga."""
    print("[1/5] Catálogos: departamentos, carreras, materias, docentes y ciclos...")
    execute_values(cur, """INSERT INTO academico_oltp.departamentos (codigo_departamento, nombre) VALUES %s
                           ON CONFLICT (codigo_departamento) DO UPDATE SET nombre = EXCLUDED.nombre""",
                   cat.DEPARTAMENTOS)
    cur.execute("SELECT codigo_departamento, departamento_id FROM academico_oltp.departamentos")
    depto_id = dict(cur.fetchall())

    execute_values(cur, """INSERT INTO academico_oltp.carreras
                               (codigo_carrera, nombre, departamento_id, plan_anio, total_uv_carrera) VALUES %s
                           ON CONFLICT (codigo_carrera) DO UPDATE SET
                               nombre = EXCLUDED.nombre, departamento_id = EXCLUDED.departamento_id,
                               plan_anio = EXCLUDED.plan_anio, total_uv_carrera = EXCLUDED.total_uv_carrera,
                               activo = TRUE""",
                   [(c.codigo, c.nombre, depto_id[c.departamento], c.plan_anio, c.total_uv) for c in cat.CARRERAS])
    cur.execute("SELECT codigo_carrera, carrera_id FROM academico_oltp.carreras")
    carrera_id = dict(cur.fetchall())

    execute_values(cur, """INSERT INTO academico_oltp.materias
                               (codigo_materia, nombre, unidades_valorativas, ciclo_plan, carrera_id) VALUES %s
                           ON CONFLICT (codigo_materia) DO UPDATE SET
                               nombre = EXCLUDED.nombre, unidades_valorativas = EXCLUDED.unidades_valorativas,
                               ciclo_plan = EXCLUDED.ciclo_plan, carrera_id = EXCLUDED.carrera_id, activo = TRUE""",
                   [(m.codigo, m.nombre, m.uv, m.ciclo, carrera_id[c.codigo]) for c in cat.CARRERAS for m in c.materias])
    cur.execute("SELECT codigo_materia, materia_id FROM academico_oltp.materias")
    materia_id = dict(cur.fetchall())

    rng = random.Random(SEMILLA)
    docentes = []
    for departamento, codigos in sim.numeracion_de_docentes().items():
        for codigo in codigos:
            escalafon = rng.choices(cat.ESCALAFONES, weights=cat.PESO_ESCALAFON)[0]
            docentes.append((codigo, escalafon, depto_id[departamento]))
    # Los que ya existen se dejan como están (hay cuentas ligadas a ellos).
    execute_values(cur, """INSERT INTO academico_oltp.docentes (codigo_docente, escalafon, departamento_id) VALUES %s
                           ON CONFLICT (codigo_docente) DO NOTHING""", docentes)
    cur.execute("SELECT codigo_docente, docente_id FROM academico_oltp.docentes")
    docente_id = dict(cur.fetchall())

    periodos = cat.periodos(cat.ANIO_INICIAL, cat.ANIO_FINAL)
    execute_values(cur, """INSERT INTO academico_oltp.periodos_academicos
                               (codigo_periodo, anio, ciclo_romano, fecha_inicio, fecha_fin, activo) VALUES %s
                           ON CONFLICT (codigo_periodo) DO UPDATE SET
                               fecha_inicio = EXCLUDED.fecha_inicio, fecha_fin = EXCLUDED.fecha_fin""",
                   [(codigo, anio, ciclo, inicio, fin, False) for codigo, anio, ciclo, inicio, fin in periodos])
    cur.execute("UPDATE academico_oltp.periodos_academicos SET activo = (codigo_periodo = %s)", (cat.CICLO_VIGENTE,))
    cur.execute("SELECT codigo_periodo, periodo_id FROM academico_oltp.periodos_academicos")
    periodo_id = dict(cur.fetchall())
    # Los ciclos nuevos reciben el mismo supuesto de costo que los demás (script 08): el
    # costo por UV real se registra en Costos institucionales.
    cur.execute("""INSERT INTO academico_oltp.costos_uv (periodo_id, costo_por_uv, moneda, fuente)
                   SELECT p.periodo_id, 25.00, 'USD',
                          'SUPUESTO PARAMETRICO - pendiente de sustituir por cifra presupuestaria oficial'
                   FROM academico_oltp.periodos_academicos p ON CONFLICT (periodo_id) DO NOTHING""")
    return {"carrera": carrera_id, "materia": materia_id, "docente": docente_id, "periodo": periodo_id}


def hay_datos(cur) -> bool:
    cur.execute("SELECT EXISTS (SELECT 1 FROM academico_oltp.estudiantes) OR "
                "EXISTS (SELECT 1 FROM academico_oltp.inscripciones)")
    return cur.fetchone()[0]


def apagar_disparadores(cur) -> None:
    """Se apagan los disparadores de usuario (bitácora de notas, bloqueo de actas, ponderación)
    mientras dura la carga: no son cambios de personas, llenarían la bitácora y las actas cerradas
    rechazarían sus propias evaluaciones. Se vuelven a encender al final, en la misma transacción."""
    for tabla in TABLAS_TRANSACCIONALES:
        cur.execute(f"ALTER TABLE academico_oltp.{tabla} DISABLE TRIGGER USER")


def reiniciar(cur) -> None:
    """Borra lo transaccional (con los disparadores ya apagados)."""
    print("      Borrando datos transaccionales anteriores...")
    for tabla in (*TABLAS_TRANSACCIONALES, "estudiantes"):
        cur.execute(f"DELETE FROM academico_oltp.{tabla}")


def _ids(cur, tabla: str, columna: str, cantidad: int) -> list[int]:
    if not cantidad:
        return []
    cur.execute(f"SELECT nextval(pg_get_serial_sequence('academico_oltp.{tabla}', '{columna}')) "
                "FROM generate_series(1, %s)", (cantidad,))
    return sorted(r[0] for r in cur.fetchall())


def _a_hora(dia: date, hora: int = 9) -> datetime:
    return datetime.combine(dia, time(hora, 0))


def cargar(cur, r: dict, ids: dict, hoy: date) -> None:
    print(f"[2/5] Estudiantes ({len(r['estudiantes']):,}) con carnet anonimizado...")
    id_estudiante = _ids(cur, "estudiantes", "estudiante_id", len(r["estudiantes"]))
    execute_values(cur, """INSERT INTO academico_oltp.estudiantes
                               (estudiante_id, carnet_hash, anio_ingreso, carrera_id, trabaja, condicion_academica, activo)
                           VALUES %s""",
                   [(id_estudiante[i], e["hash"], e["anio_ingreso"], ids["carrera"][e["carrera"]], e["trabaja"],
                     e["condicion"], e["activo"]) for i, e in enumerate(r["estudiantes"])], page_size=5000)

    print(f"[3/5] Secciones ({len(r['secciones']):,}) y evaluaciones ({len(r['evaluaciones']):,})...")
    id_seccion = _ids(cur, "secciones", "seccion_id", len(r["secciones"]))
    execute_values(cur, """INSERT INTO academico_oltp.secciones
                               (seccion_id, materia_id, docente_id, periodo_id, numero_seccion, turno, aula, cupo_maximo,
                                acta_cerrada) VALUES %s""",
                   [(id_seccion[i], ids["materia"][s["materia"]], ids["docente"][s["docente"]],
                     ids["periodo"][s["periodo"]], s["numero"], s["turno"], s["aula"], s["cupo"], s["cerrada"])
                    for i, s in enumerate(r["secciones"])], page_size=5000)
    id_evaluacion = _ids(cur, "evaluaciones", "evaluacion_id", len(r["evaluaciones"]))
    execute_values(cur, """INSERT INTO academico_oltp.evaluaciones
                               (evaluacion_id, seccion_id, nombre_evaluacion, porcentaje, fecha_evaluacion) VALUES %s""",
                   [(id_evaluacion[i], id_seccion[s], nombre, porcentaje, fecha)
                    for i, (s, nombre, porcentaje, fecha) in enumerate(r["evaluaciones"])], page_size=5000)

    print(f"[4/5] Inscripciones ({len(r['inscripciones']):,}) y calificaciones ({len(r['calificaciones']):,})...")
    id_inscripcion = _ids(cur, "inscripciones", "inscripcion_id", len(r["inscripciones"]))
    execute_values(cur, """INSERT INTO academico_oltp.inscripciones
                               (inscripcion_id, estudiante_id, seccion_id, fecha_inscripcion, numero_intento,
                                estado_inscripcion, motivo_retiro, fecha_retiro) VALUES %s""",
                   [(id_inscripcion[i], id_estudiante[x["estudiante"]], id_seccion[x["seccion"]],
                     _a_hora(x["fecha_inscripcion"]), x["intento"], x["estado"], x["motivo"],
                     _a_hora(x["fecha_retiro"]) if x["fecha_retiro"] else None)
                    for i, x in enumerate(r["inscripciones"])], page_size=5000)
    fechas = [e[3] for e in r["evaluaciones"]]
    execute_values(cur, """INSERT INTO academico_oltp.calificaciones (inscripcion_id, evaluacion_id, nota, fecha_registro)
                           VALUES %s""",
                   [(id_inscripcion[i], id_evaluacion[e], nota, _a_hora(min(fechas[e], hoy), 15))
                    for i, e, nota in r["calificaciones"]], page_size=10000)

    print(f"[5/5] Asistencia ({len(r['asistencias']):,} registros)...")
    execute_values(cur, """INSERT INTO academico_oltp.asistencias (inscripcion_id, fecha_sesion, estado_asistencia)
                           VALUES %s""",
                   [(id_inscripcion[i], dia, estado) for i, dia, estado in r["asistencias"]], page_size=10000)


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera los datos de prueba de la FMO-UES.")
    parser.add_argument("--reiniciar", action="store_true", help="borra y regenera lo transaccional")
    parser.add_argument("--hoy", type=date.fromisoformat, default=date.today(),
                        help="fecha de referencia (AAAA-MM-DD): lo posterior no tiene notas ni asistencia")
    args = parser.parse_args()

    config = configuracion()
    if not config["password"]:
        sys.exit("ERROR: POSTGRES_PASSWORD no está definida. Copia .env.example a .env y complétalo.")

    conexion = psycopg2.connect(**config)
    conexion.autocommit = False
    try:
        with conexion.cursor() as cur:
            if hay_datos(cur) and not args.reiniciar:
                sys.exit("La base ya tiene estudiantes e inscripciones. Para reemplazarlos con datos nuevos "
                         "usa --reiniciar (borra solo lo transaccional).")
            ids = preparar_catalogos(cur)
            apagar_disparadores(cur)
            if args.reiniciar:
                reiniciar(cur)
            resultado = sim.simular(args.hoy, SEMILLA, os.getenv("CARNET_CLAVE") or None)
            cargar(cur, resultado, ids, args.hoy)
            for tabla in TABLAS_TRANSACCIONALES:
                cur.execute(f"ALTER TABLE academico_oltp.{tabla} ENABLE TRIGGER USER")
            for tabla in (*TABLAS_TRANSACCIONALES, "estudiantes", "materias", "docentes"):
                cur.execute(f"ANALYZE academico_oltp.{tabla}")
        conexion.commit()
        with conexion.cursor() as cur:
            print("\nPoblación completada. En la base:")
            for etiqueta, tabla in (("Departamentos", "departamentos"), ("Carreras", "carreras"), ("Materias", "materias"),
                                    ("Docentes", "docentes"), ("Estudiantes", "estudiantes"),
                                    ("Secciones", "secciones"), ("Evaluaciones", "evaluaciones"),
                                    ("Inscripciones", "inscripciones"), ("Calificaciones", "calificaciones"),
                                    ("Asistencias", "asistencias")):
                cur.execute(f"SELECT COUNT(*) FROM academico_oltp.{tabla}")
                print(f" - {etiqueta}: {cur.fetchone()[0]:,}")
        print("\nSiguiente: recarga el almacén (python -m etl.carga) y, si cambió la malla, el grafo "
              "(python database/nosql/03_cargar_grafo_neo4j.py --reiniciar).")
    except Exception as exc:
        conexion.rollback()
        print(f"\nError durante la ejecución del script: {exc}")
        raise
    finally:
        conexion.close()


if __name__ == "__main__":
    main()
