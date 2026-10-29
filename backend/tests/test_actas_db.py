"""Cierre de actas y cuentas contra PostgreSQL real (scripts 17 y 18).

Se conecta con rol_app, como la aplicación, y recorre el ciclo completo:
completar notas, cerrar el acta, comprobar que el trigger bloquea cambios,
reabrirla con motivo. También las funciones de cuenta (cambiar la propia
contraseña, último acceso) y quién puede llamarlas. Cada prueba corre en una
transacción que se revierte: la base queda como estaba. Sin base, se omite.

    cd backend && python -m unittest tests.test_actas_db -v
"""

import unittest

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.test_rls_docente import MOTOR

HASH_VALIDO = "$2b$12$" + "a" * 53


@unittest.skipIf(MOTOR is None, "PostgreSQL no disponible (docker compose up -d)")
class TestActas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with MOTOR.connect() as c:
            c.execute(text("SET LOCAL ROLE rol_coordinador"))
            # Una sección abierta cuyas evaluaciones suman 100 y con inscritos;
            # preferimos la del docente que tiene usuario.
            fila = c.execute(text("""
                SELECT s.seccion_id, s.docente_id
                FROM academico_oltp.secciones s
                WHERE NOT s.acta_cerrada
                  AND (SELECT sum(porcentaje) FROM academico_oltp.evaluaciones e
                       WHERE e.seccion_id = s.seccion_id) = 100
                  AND EXISTS (SELECT 1 FROM academico_oltp.inscripciones i
                              WHERE i.seccion_id = s.seccion_id AND i.estado_inscripcion = 'INSCRITO')
                ORDER BY EXISTS (SELECT 1 FROM academico_oltp.usuarios u
                                 WHERE u.docente_id = s.docente_id) DESC, s.seccion_id
                LIMIT 1""")).first()
            if fila is None:
                raise unittest.SkipTest("No hay sección abierta con ponderación 100 e inscritos")
            cls.seccion, cls.docente = fila
            cls.otro_docente = c.execute(text(
                "SELECT docente_id FROM academico_oltp.docentes WHERE docente_id <> :d LIMIT 1"),
                {"d": cls.docente}).scalar_one()

    def setUp(self):
        self.c = MOTOR.connect()
        self.c.begin()

    def tearDown(self):
        self.c.rollback()
        self.c.close()

    def _como(self, rol, docente=None, usuario="prueba"):
        self.c.execute(text(f"SET LOCAL ROLE {rol}"))
        self.c.execute(text("SELECT set_config('app.usuario', :u, true), "
                            "set_config('app.docente_id', :d, true)"),
                       {"u": usuario, "d": "" if docente is None else str(docente)})

    def _falla(self, sql, params=None):
        """Ejecuta en un savepoint y devuelve el mensaje de error del motor."""
        punto = self.c.begin_nested()
        with self.assertRaises(DBAPIError) as e:
            self.c.execute(text(sql), params or {})
        punto.rollback()
        return str(e.exception.orig)

    def _completar_notas(self):
        self._como("rol_coordinador")
        self.c.execute(text("""
            INSERT INTO academico_oltp.calificaciones (inscripcion_id, evaluacion_id, nota)
            SELECT i.inscripcion_id, e.evaluacion_id, 8
            FROM academico_oltp.inscripciones i
            JOIN academico_oltp.evaluaciones e ON e.seccion_id = i.seccion_id
            WHERE i.seccion_id = :s AND i.estado_inscripcion = 'INSCRITO'
              AND NOT EXISTS (SELECT 1 FROM academico_oltp.calificaciones c
                              WHERE c.inscripcion_id = i.inscripcion_id
                                AND c.evaluacion_id = e.evaluacion_id)"""), {"s": self.seccion})

    def _inscritos(self):
        return self.c.execute(text(
            "SELECT count(*) FROM academico_oltp.inscripciones "
            "WHERE seccion_id = :s AND estado_inscripcion = 'INSCRITO'"), {"s": self.seccion}).scalar_one()

    def test_no_cierra_con_notas_pendientes(self):
        self._como("rol_coordinador")
        # Quitamos una nota para asegurar que falta al menos una.
        self._completar_notas()
        self.c.execute(text("""
            DELETE FROM academico_oltp.calificaciones WHERE calificacion_id = (
                SELECT c.calificacion_id FROM academico_oltp.calificaciones c
                JOIN academico_oltp.inscripciones i ON i.inscripcion_id = c.inscripcion_id
                WHERE i.seccion_id = :s AND i.estado_inscripcion = 'INSCRITO' LIMIT 1)"""),
            {"s": self.seccion})
        msg = self._falla("SELECT academico_oltp.cerrar_acta(:s)", {"s": self.seccion})
        self.assertIn("Faltan 1 nota(s)", msg)

    def test_no_cierra_si_la_ponderacion_no_suma_100(self):
        self._completar_notas()
        self.c.execute(text("UPDATE academico_oltp.evaluaciones SET porcentaje = porcentaje - 1 "
                            "WHERE evaluacion_id = (SELECT min(evaluacion_id) FROM academico_oltp.evaluaciones "
                            "WHERE seccion_id = :s)"), {"s": self.seccion})
        msg = self._falla("SELECT academico_oltp.cerrar_acta(:s)", {"s": self.seccion})
        self.assertIn("deben sumar 100", msg)

    def test_otro_docente_no_cierra_el_acta(self):
        self._completar_notas()
        self._como("rol_docente", self.otro_docente)
        msg = self._falla("SELECT academico_oltp.cerrar_acta(:s)", {"s": self.seccion})
        self.assertIn("Solo el docente de la sección", msg)

    def test_rol_app_sin_cambiar_de_rol_no_puede_llamarla(self):
        msg = self._falla("SELECT academico_oltp.cerrar_acta(:s)", {"s": self.seccion})
        self.assertIn("permission denied", msg)

    def test_ciclo_cerrar_bloquear_reabrir(self):
        self._completar_notas()
        inscritos = self._inscritos()

        self._como("rol_docente", self.docente, usuario="docente.prueba")
        cerradas = self.c.execute(text("SELECT academico_oltp.cerrar_acta(:s)"), {"s": self.seccion}).scalar_one()
        self.assertEqual(cerradas, inscritos)
        self.assertEqual(self._inscritos(), 0)
        self.assertIn("ya está cerrada",
                      self._falla("SELECT academico_oltp.cerrar_acta(:s)", {"s": self.seccion}))

        # Con el acta cerrada, el trigger rechaza notas, evaluaciones y asistencia,
        # incluso al coordinador.
        for rol, docente in (("rol_docente", self.docente), ("rol_coordinador", None)):
            self._como(rol, docente)
            for sql in (
                "UPDATE academico_oltp.calificaciones SET nota = 10 WHERE inscripcion_id IN "
                "(SELECT inscripcion_id FROM academico_oltp.inscripciones WHERE seccion_id = :s)",
                "UPDATE academico_oltp.evaluaciones SET nombre_evaluacion = 'x' WHERE seccion_id = :s",
                "INSERT INTO academico_oltp.asistencias (inscripcion_id, fecha_sesion, estado_asistencia) "
                "SELECT inscripcion_id, DATE '2099-01-01', 'PRESENTE' FROM academico_oltp.inscripciones "
                "WHERE seccion_id = :s LIMIT 1",
            ):
                with self.subTest(rol=rol, sql=sql[:40]):
                    self.assertIn("acta de esta sección está cerrada", self._falla(sql, {"s": self.seccion}))

        # Reabrir: el docente ni siquiera tiene EXECUTE; el coordinador sí, con motivo.
        self._como("rol_docente", self.docente)
        self.assertIn("permission denied for function reabrir_acta",
                      self._falla("SELECT academico_oltp.reabrir_acta(:s, 'corrección')", {"s": self.seccion}))
        self._como("rol_coordinador", usuario="coord.prueba")
        self.assertIn("al menos 5 caracteres",
                      self._falla("SELECT academico_oltp.reabrir_acta(:s, '  ab ')", {"s": self.seccion}))
        reabiertas = self.c.execute(text("SELECT academico_oltp.reabrir_acta(:s, 'Nota mal digitada')"),
                                    {"s": self.seccion}).scalar_one()
        self.assertEqual(reabiertas, inscritos)
        self.assertEqual(self._inscritos(), inscritos)

        # Abierta otra vez, se puede corregir.
        n = self.c.execute(text(
            "UPDATE academico_oltp.calificaciones SET nota = 9 WHERE inscripcion_id IN "
            "(SELECT inscripcion_id FROM academico_oltp.inscripciones WHERE seccion_id = :s)"),
            {"s": self.seccion}).rowcount
        self.assertGreater(n, 0)

        bitacora = self.c.execute(text(
            "SELECT accion, usuario_app, usuario_db, motivo, cardinality(inscripciones) "
            "FROM auditoria.log_actas WHERE seccion_id = :s ORDER BY log_id DESC LIMIT 2"),
            {"s": self.seccion}).all()
        self.assertEqual([tuple(f) for f in bitacora], [
            ("REABIERTA", "coord.prueba", "rol_coordinador", "Nota mal digitada", inscritos),
            ("CERRADA", "docente.prueba", "rol_docente", None, inscritos),
        ])

    def test_la_auditoria_registra_quien_cambio_la_nota(self):
        self._como("rol_coordinador", usuario="coord.auditoria")
        fila = self.c.execute(text("""
            SELECT c.calificacion_id FROM academico_oltp.calificaciones c
            JOIN academico_oltp.inscripciones i ON i.inscripcion_id = c.inscripcion_id
            WHERE i.seccion_id = :s LIMIT 1"""), {"s": self.seccion}).first()
        if fila is None:
            self.skipTest("La sección no tiene notas")
        self.c.execute(text("UPDATE academico_oltp.calificaciones SET nota = 5.5 WHERE calificacion_id = :c"),
                       {"c": fila[0]})
        self.c.execute(text("DELETE FROM academico_oltp.calificaciones WHERE calificacion_id = :c"), {"c": fila[0]})
        self.c.execute(text("RESET ROLE"))
        self.c.execute(text("SET LOCAL ROLE rol_coordinador"))
        ops = self.c.execute(text(
            "SELECT operacion, usuario_app FROM auditoria.log_cambios_notas "
            "WHERE usuario_app = 'coord.auditoria' ORDER BY 1")).all()
        self.assertEqual([tuple(f) for f in ops], [("D", "coord.auditoria"), ("U", "coord.auditoria")])


@unittest.skipIf(MOTOR is None, "PostgreSQL no disponible (docker compose up -d)")
class TestFuncionesDeCuenta(unittest.TestCase):
    def setUp(self):
        self.c = MOTOR.connect()
        self.c.begin()
        self.c.execute(text("SET LOCAL ROLE rol_coordinador"))
        self.usuario, self.otro = self.c.execute(text(
            "SELECT usuario_id FROM academico_oltp.usuarios WHERE activo ORDER BY usuario_id LIMIT 2")).scalars().all()
        self.hash_otro = self._hash(self.otro)

    def tearDown(self):
        self.c.rollback()
        self.c.close()

    def _hash(self, usuario_id):
        return self.c.execute(text("SELECT password_hash FROM academico_oltp.usuarios WHERE usuario_id = :u"),
                              {"u": usuario_id}).scalar_one()

    def _declarar(self, usuario_id):
        self.c.execute(text("SELECT set_config('app.usuario_id', :u, true)"),
                       {"u": "" if usuario_id is None else str(usuario_id)})

    def _falla(self, sql, params=None):
        punto = self.c.begin_nested()
        with self.assertRaises(DBAPIError) as e:
            self.c.execute(text(sql), params or {})
        punto.rollback()
        return str(e.exception.orig)

    def test_cambia_solo_la_propia_contrasena(self):
        self._declarar(self.usuario)
        self.c.execute(text("UPDATE academico_oltp.usuarios SET debe_cambiar_password = TRUE "
                            "WHERE usuario_id = :u"), {"u": self.usuario})
        self.c.execute(text("SELECT academico_oltp.cambiar_password_propio(:h)"), {"h": HASH_VALIDO})
        fila = self.c.execute(text(
            "SELECT password_hash, debe_cambiar_password, password_cambiado_en IS NOT NULL "
            "FROM academico_oltp.usuarios WHERE usuario_id = :u"), {"u": self.usuario}).one()
        self.assertEqual(tuple(fila), (HASH_VALIDO, False, True))
        self.assertEqual(self._hash(self.otro), self.hash_otro)

    def test_sin_usuario_declarado_no_cambia_nada(self):
        self._declarar(None)
        self.assertIn("Sesión sin usuario declarado",
                      self._falla("SELECT academico_oltp.cambiar_password_propio(:h)", {"h": HASH_VALIDO}))

    def test_solo_acepta_hashes_bcrypt(self):
        self._declarar(self.usuario)
        for malo in ("texto-plano", "$2b$12$corto", "$1$md5$" + "a" * 53):
            with self.subTest(hash=malo):
                self.assertIn("Hash de contraseña no válido",
                              self._falla("SELECT academico_oltp.cambiar_password_propio(:h)", {"h": malo}))

    def test_cuenta_desactivada_no_cambia_contrasena(self):
        self.c.execute(text("RESET ROLE"))
        # rol_app no puede desactivar; lo hace el coordinador, que sí puede.
        self.c.execute(text("SET LOCAL ROLE rol_coordinador"))
        self.c.execute(text("UPDATE academico_oltp.usuarios SET activo = FALSE WHERE usuario_id = :u"),
                       {"u": self.usuario})
        self._declarar(self.usuario)
        self.assertIn("desactivada",
                      self._falla("SELECT academico_oltp.cambiar_password_propio(:h)", {"h": HASH_VALIDO}))

    def test_el_docente_no_escribe_usuarios_directamente(self):
        self.c.execute(text("SET LOCAL ROLE rol_docente"))
        self.assertIn("permission denied", self._falla(
            "UPDATE academico_oltp.usuarios SET password_hash = :h", {"h": HASH_VALIDO}))

    def test_registrar_acceso_es_de_rol_app(self):
        self.c.execute(text("RESET ROLE"))
        self.c.execute(text("SELECT academico_oltp.registrar_acceso(:u)"), {"u": self.usuario})
        self.c.execute(text("SET LOCAL ROLE rol_coordinador"))
        reciente = self.c.execute(text(
            "SELECT ultimo_acceso > now() - interval '1 minute' FROM academico_oltp.usuarios "
            "WHERE usuario_id = :u"), {"u": self.usuario}).scalar_one()
        self.assertTrue(reciente)
        self.c.execute(text("SET LOCAL ROLE rol_docente"))
        self.assertIn("permission denied",
                      self._falla("SELECT academico_oltp.registrar_acceso(:u)", {"u": self.usuario}))


if __name__ == "__main__":
    unittest.main()
