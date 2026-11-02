"""Rol admin y coordinador acotado a una carrera (scripts 23 y 24).

Se conecta con rol_app, como la aplicación, y comprueba contra PostgreSQL real
que el recorte lo impone el motor y no la pantalla:

  - un coordinador sin carrera declarada no ve NINGUNA fila (falla cerrado);
  - con carrera, ve solo la suya, en toda la cadena carrera -> materia ->
    sección -> inscripción -> notas y asistencia;
  - el admin ve todo, pero sobre la bitácora sigue teniendo solo lectura;
  - lo institucional (períodos, carreras, docentes, costos, metas, usuarios) ya
    no lo escribe el coordinador;
  - el almacén respeta la misma carrera con rol_dw_carrera.

Cada prueba corre en una transacción que se revierte. Sin base, se omite.

    cd backend && python -m unittest tests.test_rol_admin_carrera -v
"""

import unittest

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.test_rls_docente import MOTOR


def _motor_dashboard():
    """Conexión como rol_dashboard, que es la que usa app/dw.py.

    rol_app no es miembro de rol_dw_carrera y no puede adoptarlo: el tablero
    tiene su propia credencial a propósito, para que la aplicación web no pueda
    escribir en el almacén.
    """
    from dotenv import dotenv_values
    from sqlalchemy import create_engine
    from app.config import RAIZ_PROYECTO
    env = dotenv_values(RAIZ_PROYECTO / ".env")
    if not env.get("DASHBOARD_DB_PASSWORD"):
        return None
    url = (f"postgresql+psycopg2://{env.get('DASHBOARD_DB_USER') or 'rol_dashboard'}:"
           f"{env['DASHBOARD_DB_PASSWORD']}@{env.get('POSTGRES_HOST') or 'localhost'}:"
           f"{env.get('POSTGRES_PORT') or 5432}/{env.get('POSTGRES_DB') or 'academico_db'}")
    try:
        motor = create_engine(url, future=True)
        with motor.connect() as c:
            c.execute(text("SELECT 1"))
        return motor
    except Exception:  # noqa: BLE001
        return None


MOTOR_DW = _motor_dashboard()


@unittest.skipIf(MOTOR is None, "PostgreSQL no disponible (docker compose up -d)")
class TestAlcancePorCarrera(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with MOTOR.connect() as c:
            c.execute(text("SET LOCAL ROLE rol_admin"))
            fila = c.execute(text("""
                SELECT m.carrera_id, count(*) AS materias
                FROM academico_oltp.materias m
                GROUP BY m.carrera_id ORDER BY count(*) DESC LIMIT 1""")).first()
            if fila is None:
                raise unittest.SkipTest("No hay materias en la base")
            cls.carrera, cls.materias_de_la_carrera = fila
            cls.materias_totales = c.execute(text(
                "SELECT count(*) FROM academico_oltp.materias")).scalar_one()
        if cls.materias_totales == cls.materias_de_la_carrera:
            raise unittest.SkipTest("Solo hay una carrera: el recorte no se puede distinguir")

    def setUp(self):
        self.c = MOTOR.connect()
        self.tx = self.c.begin()

    def tearDown(self):
        self.tx.rollback()
        self.c.close()

    def _como(self, rol, carrera=None):
        self.c.execute(text(f"SET LOCAL ROLE {rol}"))
        self.c.execute(text("SELECT set_config('app.carrera_id', :c, true)"),
                       {"c": "" if carrera is None else str(carrera)})

    def _cuenta(self, tabla):
        return self.c.execute(text(f"SELECT count(*) FROM academico_oltp.{tabla}")).scalar_one()

    def _falla(self, sql):
        punto = self.c.begin_nested()
        with self.assertRaises(DBAPIError) as e:
            self.c.execute(text(sql))
        punto.rollback()
        return str(e.exception.orig)

    # --- el recorte ---

    def test_sin_carrera_declarada_no_ve_nada(self):
        self._como("rol_coordinador")
        for tabla in ("carreras", "materias", "estudiantes", "secciones", "inscripciones",
                      "calificaciones", "asistencias", "evaluaciones"):
            with self.subTest(tabla=tabla):
                self.assertEqual(self._cuenta(tabla), 0)

    def test_con_carrera_ve_solo_la_suya(self):
        self._como("rol_coordinador", self.carrera)
        self.assertEqual(self._cuenta("carreras"), 1)
        self.assertEqual(self._cuenta("materias"), self.materias_de_la_carrera)
        self.assertLess(self._cuenta("materias"), self.materias_totales)

    def test_la_cadena_completa_queda_acotada(self):
        """Secciones, inscripciones, notas y asistencia: todo de su carrera."""
        self._como("rol_coordinador", self.carrera)
        ajenas = self.c.execute(text("""
            SELECT count(*) FROM academico_oltp.secciones s
            WHERE s.materia_id NOT IN (SELECT materia_id FROM academico_oltp.materias)""")).scalar_one()
        self.assertEqual(ajenas, 0)
        # Ninguna inscripción de una sección que no ve.
        huerfanas = self.c.execute(text("""
            SELECT count(*) FROM academico_oltp.inscripciones i
            WHERE i.seccion_id NOT IN (SELECT seccion_id FROM academico_oltp.secciones)""")).scalar_one()
        self.assertEqual(huerfanas, 0)

    def test_el_admin_ve_todo(self):
        self._como("rol_admin")
        self.assertEqual(self._cuenta("materias"), self.materias_totales)
        self.assertGreater(self._cuenta("carreras"), 1)

    def test_no_puede_escribir_en_la_carrera_de_otro(self):
        self._como("rol_coordinador", self.carrera)
        otra = self.c.execute(text("""
            SELECT materia_id FROM academico_oltp.materias LIMIT 1""")).scalar_one()
        # Mover su materia a otra carrera: la política de WITH CHECK lo rechaza.
        mensaje = self._falla(
            f"UPDATE academico_oltp.materias SET carrera_id = carrera_id + 1 WHERE materia_id = {otra}")
        self.assertIn("row-level security", mensaje.lower())

    # --- lo institucional ---

    def test_el_coordinador_ya_no_escribe_lo_institucional(self):
        self._como("rol_coordinador", self.carrera)
        for sql in (
            "INSERT INTO academico_oltp.periodos_academicos "
            "(codigo_periodo, anio, ciclo_romano, fecha_inicio, fecha_fin) "
            "VALUES ('9999-I', 9999, 'I', DATE '9999-01-01', DATE '9999-02-01')",
            "UPDATE academico_oltp.departamentos SET nombre = nombre",
            "UPDATE academico_oltp.docentes SET activo = activo",
            "UPDATE academico_oltp.costos_uv SET costo_por_uv = costo_por_uv",
            "UPDATE academico_oltp.metas_indicador SET meta = meta",
            "UPDATE academico_oltp.usuarios SET nombre_completo = nombre_completo",
        ):
            with self.subTest(sql=sql[:45]):
                self.assertIn("permission denied", self._falla(sql).lower())

    def test_el_admin_si_escribe_lo_institucional(self):
        self._como("rol_admin")
        self.c.execute(text("UPDATE academico_oltp.costos_uv SET costo_por_uv = costo_por_uv"))
        self.c.execute(text("UPDATE academico_oltp.metas_indicador SET meta = meta"))

    def test_la_bitacora_sigue_siendo_de_solo_lectura_incluso_para_el_admin(self):
        """La jerarquía no alcanza a la auditoría: es la garantía del sistema."""
        self._como("rol_admin")
        self.c.execute(text("SELECT count(*) FROM auditoria.log_cambios_notas"))
        for sql in ("DELETE FROM auditoria.log_cambios_notas",
                    "UPDATE auditoria.log_cambios_notas SET nota_nueva = 10",
                    "DELETE FROM auditoria.log_actas"):
            with self.subTest(sql=sql[:35]):
                self.assertIn("permission denied", self._falla(sql).lower())

    # --- el almacén ---

    @unittest.skipIf(MOTOR_DW is None, "Falta DASHBOARD_DB_PASSWORD en el .env")
    def test_el_almacen_respeta_la_carrera(self):
        with MOTOR_DW.connect() as c:
            totales = c.execute(text(
                "SELECT count(*) FROM dw_academico.fact_inscripcion")).scalar_one()
            # La primera consulta ya abrió una transacción implícita: hay que
            # cerrarla antes de abrir la propia con SET LOCAL ROLE.
            c.rollback()

            tx = c.begin()
            c.execute(text("SET LOCAL ROLE rol_dw_carrera"))
            sin_declarar = c.execute(text(
                "SELECT count(*) FROM dw_academico.fact_inscripcion")).scalar_one()
            c.execute(text("SELECT set_config('app.carrera_id', :c, true)"),
                      {"c": str(self.carrera)})
            propias = c.execute(text(
                "SELECT count(*) FROM dw_academico.fact_inscripcion")).scalar_one()
            carreras = c.execute(text(
                "SELECT count(*) FROM dw_academico.dim_carrera")).scalar_one()
            tx.rollback()

        self.assertEqual(sin_declarar, 0, "sin carrera declarada debe ver cero filas")
        self.assertEqual(carreras, 1)
        self.assertGreater(propias, 0)
        self.assertLess(propias, totales)

    @unittest.skipIf(MOTOR_DW is None, "Falta DASHBOARD_DB_PASSWORD en el .env")
    def test_el_tablero_institucional_sigue_viendo_todo(self):
        """Streamlit y la validación del almacén usan rol_dashboard sin adoptar
        el rol acotado: no deben quedar recortados por este cambio."""
        with MOTOR_DW.connect() as c:
            self.assertGreater(c.execute(text(
                "SELECT count(*) FROM dw_academico.fact_inscripcion")).scalar_one(), 0)
            self.assertGreater(c.execute(text(
                "SELECT count(*) FROM dw_academico.dim_carrera")).scalar_one(), 1)

    def test_el_data_mart_no_esquiva_el_recorte(self):
        """Una vista normal se evalúa con los permisos de su dueño; esta no."""
        invoker = self.c.execute(text("""
            SELECT 'security_invoker=on' = ANY(c.reloptions)
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'dw_academico' AND c.relname = 'v_mart_departamento'""")).scalar_one()
        self.assertTrue(invoker)


@unittest.skipIf(MOTOR is None, "PostgreSQL no disponible (docker compose up -d)")
class TestReglasDeLaCuenta(unittest.TestCase):
    """La base exige la carrera del coordinador; no se confía solo en la pantalla."""

    def setUp(self):
        self.c = MOTOR.connect()
        self.tx = self.c.begin()
        self.c.execute(text("SET LOCAL ROLE rol_admin"))

    def tearDown(self):
        self.tx.rollback()
        self.c.close()

    def _crear(self, rol, carrera=None, docente=None):
        punto = self.c.begin_nested()
        try:
            self.c.execute(text("""
                INSERT INTO academico_oltp.usuarios
                    (username, password_hash, nombre_completo, rol_db, docente_id, carrera_id)
                VALUES ('prueba.alcance', :h, 'Prueba', :rol, :doc, :car)"""),
                {"h": "$2b$12$" + "a" * 53, "rol": rol, "doc": docente, "car": carrera})
        except DBAPIError as e:
            punto.rollback()
            return str(e.orig)
        punto.rollback()
        return None

    def test_un_coordinador_sin_carrera_no_se_puede_crear(self):
        self.assertIn("chk_coordinador_con_carrera", self._crear("rol_coordinador"))

    def test_un_admin_con_carrera_tampoco(self):
        carrera = self.c.execute(text(
            "SELECT carrera_id FROM academico_oltp.carreras LIMIT 1")).scalar_one()
        self.assertIn("chk_coordinador_con_carrera", self._crear("rol_admin", carrera=carrera))

    def test_un_coordinador_con_carrera_si(self):
        carrera = self.c.execute(text(
            "SELECT carrera_id FROM academico_oltp.carreras LIMIT 1")).scalar_one()
        self.assertIsNone(self._crear("rol_coordinador", carrera=carrera))

    def test_el_rol_tiene_que_ser_uno_de_los_tres(self):
        self.assertIn("usuarios_rol_db_check", self._crear("rol_inventado"))
