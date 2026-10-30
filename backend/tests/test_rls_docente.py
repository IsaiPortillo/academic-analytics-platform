"""Seguridad por fila contra PostgreSQL real (database/oltp/16_rls_docente.sql).

Se conecta con rol_app (credenciales del .env), igual que la aplicación, y hace
lo mismo que haría un docente malintencionado o una consulta con un error:
escribir en la sección de otro docente. Todo dentro de transacciones que se
revierten: la base queda como estaba. Si la base no está levantada, se omite.

    cd backend && python -m unittest tests.test_rls_docente -v
"""

import unittest

from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, OperationalError

def _url_del_env():
    """La URL de rol_app leída del .env (no de os.environ: otras pruebas ponen ahí
    contraseñas de mentira para importar la configuración sin base de datos)."""
    from dotenv import dotenv_values
    from app.config import RAIZ_PROYECTO
    env = dotenv_values(RAIZ_PROYECTO / ".env")
    if not env.get("APP_DB_PASSWORD"):
        return None
    return (f"postgresql+psycopg2://{env.get('APP_DB_USER') or 'rol_app'}:{env['APP_DB_PASSWORD']}"
            f"@{env.get('POSTGRES_HOST') or 'localhost'}:{env.get('POSTGRES_PORT') or 5432}"
            f"/{env.get('POSTGRES_DB') or 'academico_db'}")


try:
    _URL = _url_del_env()
except Exception:  # noqa: BLE001 - sin .env no hay contra qué probar
    _URL = None


def _motor():
    if _URL is None:
        return None
    try:
        motor = create_engine(_URL, future=True)
        with motor.connect() as c:
            c.execute(text("SELECT 1"))
        return motor
    except OperationalError:
        return None


MOTOR = _motor()


@unittest.skipIf(MOTOR is None, "PostgreSQL no disponible (docker compose up -d)")
class TestSeguridadPorFila(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with MOTOR.connect() as c:
            c.execute(text("SET LOCAL ROLE rol_coordinador"))
            # Docente A: una sección con inscripciones y evaluaciones. Sección B: de otro docente.
            # Las dos con el acta abierta: con el acta cerrada, el bloqueo de actas
            # (script 17) rechaza la escritura antes que la seguridad por fila.
            fila = c.execute(text("""
                SELECT s.docente_id, s.seccion_id, i.inscripcion_id, e.evaluacion_id
                FROM academico_oltp.secciones s
                JOIN academico_oltp.inscripciones i ON i.seccion_id = s.seccion_id
                JOIN academico_oltp.evaluaciones e ON e.seccion_id = s.seccion_id
                WHERE NOT s.acta_cerrada
                ORDER BY s.seccion_id LIMIT 1""")).one()
            cls.docente_a, cls.seccion_a, cls.inscripcion_a, cls.evaluacion_a = fila
            fila = c.execute(text("""
                SELECT s.seccion_id, i.inscripcion_id, e.evaluacion_id
                FROM academico_oltp.secciones s
                JOIN academico_oltp.inscripciones i ON i.seccion_id = s.seccion_id
                JOIN academico_oltp.evaluaciones e ON e.seccion_id = s.seccion_id
                WHERE s.docente_id <> :a AND NOT s.acta_cerrada
                ORDER BY s.seccion_id LIMIT 1"""), {"a": cls.docente_a}).one()
            cls.seccion_b, cls.inscripcion_b, cls.evaluacion_b = fila

    def _como(self, conexion, rol, docente=None):
        conexion.execute(text(f"SET LOCAL ROLE {rol}"))
        if docente is not None:
            conexion.execute(text("SELECT set_config('app.docente_id', :d, true)"), {"d": str(docente)})

    def _rechazado(self, sql, params=None, docente=None):
        """Ejecuta como docente A y devuelve el mensaje con que el motor lo rechaza."""
        with MOTOR.connect() as c:
            self._como(c, "rol_docente", self.docente_a if docente is None else docente)
            with self.assertRaises(DBAPIError) as e:
                c.execute(text(sql), params or {})
            c.rollback()
        return str(e.exception.orig)

    def _filas_afectadas(self, sql, params):
        with MOTOR.connect() as c:
            self._como(c, "rol_docente", self.docente_a)
            n = c.execute(text(sql), params).rowcount
            c.rollback()
        return n

    # --- escritura en secciones ajenas ------------------------------------------

    def test_no_registra_asistencia_en_seccion_ajena(self):
        msg = self._rechazado(
            "INSERT INTO academico_oltp.asistencias (inscripcion_id, fecha_sesion, estado_asistencia) "
            "VALUES (:i, DATE '2099-01-01', 'PRESENTE')", {"i": self.inscripcion_b})
        self.assertIn("row-level security", msg)

    def test_no_crea_evaluaciones_en_seccion_ajena(self):
        msg = self._rechazado(
            "INSERT INTO academico_oltp.evaluaciones (seccion_id, nombre_evaluacion, porcentaje, fecha_evaluacion) "
            "VALUES (:s, 'intrusa', 1, DATE '2099-01-01')", {"s": self.seccion_b})
        self.assertIn("row-level security", msg)

    def test_no_pone_notas_en_evaluacion_ajena(self):
        msg = self._rechazado(
            "INSERT INTO academico_oltp.calificaciones (inscripcion_id, evaluacion_id, nota) "
            "VALUES (:i, :e, 10)", {"i": self.inscripcion_b, "e": self.evaluacion_b})
        self.assertIn("row-level security", msg)

    def test_no_cruza_su_evaluacion_con_un_estudiante_de_otra_seccion(self):
        msg = self._rechazado(
            "INSERT INTO academico_oltp.calificaciones (inscripcion_id, evaluacion_id, nota) "
            "VALUES (:i, :e, 10)", {"i": self.inscripcion_b, "e": self.evaluacion_a})
        self.assertIn("row-level security", msg)

    def test_no_mueve_su_evaluacion_a_otra_seccion(self):
        msg = self._rechazado(
            "UPDATE academico_oltp.evaluaciones SET seccion_id = :b WHERE evaluacion_id = :e",
            {"b": self.seccion_b, "e": self.evaluacion_a})
        self.assertIn("row-level security", msg)

    def test_un_update_sobre_notas_ajenas_no_toca_ninguna_fila(self):
        n = self._filas_afectadas(
            "UPDATE academico_oltp.calificaciones SET nota = 10 WHERE evaluacion_id = :e",
            {"e": self.evaluacion_b})
        self.assertEqual(n, 0)

    # --- lectura -----------------------------------------------------------------

    def test_solo_ve_las_notas_de_sus_secciones(self):
        with MOTOR.connect() as c:
            self._como(c, "rol_docente", self.docente_a)
            ajenas = c.execute(text("""
                SELECT count(*) FROM academico_oltp.calificaciones ca
                JOIN academico_oltp.inscripciones i ON i.inscripcion_id = ca.inscripcion_id
                JOIN academico_oltp.secciones s ON s.seccion_id = i.seccion_id
                WHERE s.docente_id <> :a"""), {"a": self.docente_a}).scalar()
            propias = c.execute(text("SELECT count(*) FROM academico_oltp.calificaciones")).scalar()
            c.rollback()
        self.assertEqual(ajenas, 0)
        self.assertGreater(propias, 0)

    def test_sin_docente_declarado_no_ve_nada(self):
        # Falla cerrado: si la aplicación olvidara declarar el docente.
        with MOTOR.connect() as c:
            self._como(c, "rol_docente")
            vistas = [c.execute(text(f"SELECT count(*) FROM academico_oltp.{t}")).scalar()
                      for t in ("evaluaciones", "calificaciones", "asistencias")]
            c.rollback()
        self.assertEqual(vistas, [0, 0, 0])

    def test_el_docente_declarado_es_local_a_la_transaccion(self):
        with MOTOR.connect() as c:
            self._como(c, "rol_docente", self.docente_a)
            c.commit()
            valor = c.execute(text("SELECT current_setting('app.docente_id', true)")).scalar()
            c.rollback()
        self.assertIn(valor, (None, ""))

    # --- lo que sí debe seguir funcionando ---------------------------------------

    def test_registra_asistencia_en_su_seccion(self):
        with MOTOR.connect() as c:
            self._como(c, "rol_docente", self.docente_a)
            c.execute(text(
                "INSERT INTO academico_oltp.asistencias (inscripcion_id, fecha_sesion, estado_asistencia) "
                "VALUES (:i, DATE '2099-01-01', 'PRESENTE')"), {"i": self.inscripcion_a})
            c.rollback()

    def test_actualiza_notas_de_su_seccion(self):
        n = self._filas_afectadas(
            "UPDATE academico_oltp.calificaciones SET nota = nota WHERE evaluacion_id = :e",
            {"e": self.evaluacion_a})
        self.assertGreater(n, 0)

    def test_el_coordinador_ve_todo(self):
        with MOTOR.connect() as c:
            self._como(c, "rol_coordinador")
            total = c.execute(text("SELECT count(*) FROM academico_oltp.calificaciones")).scalar()
            self._como(c, "rol_docente", self.docente_a)
            del_docente = c.execute(text("SELECT count(*) FROM academico_oltp.calificaciones")).scalar()
            c.rollback()
        self.assertGreater(total, del_docente)

    def test_el_etl_conserva_su_lectura(self):
        with MOTOR.connect() as c:
            politicas = c.execute(text("""
                SELECT count(*) FROM pg_policies
                WHERE schemaname = 'academico_oltp' AND policyname = 'etl_lectura'
                  AND 'rol_etl' = ANY(roles) AND cmd = 'SELECT'""")).scalar()
        self.assertEqual(politicas, 3)


if __name__ == "__main__":
    unittest.main()
