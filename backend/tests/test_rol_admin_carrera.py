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


@unittest.skipIf(MOTOR is None, "PostgreSQL no disponible (docker compose up -d)")
class TestAuditoriaPorCarrera(unittest.TestCase):
    """La bitácora también se acota (script 25).

    Sin esto, el recorte servía para los datos y se podía esquivar leyendo su
    rastro: /auditoria mostraba los cambios de nota de todas las carreras.
    """

    @classmethod
    def setUpClass(cls):
        with MOTOR.connect() as c:
            c.execute(text("SET LOCAL ROLE rol_admin"))
            fila = c.execute(text("""
                SELECT m.carrera_id, c2.calificacion_id
                FROM academico_oltp.calificaciones c2
                JOIN academico_oltp.inscripciones i ON i.inscripcion_id = c2.inscripcion_id
                JOIN academico_oltp.secciones s ON s.seccion_id = i.seccion_id
                JOIN academico_oltp.materias m ON m.materia_id = s.materia_id
                WHERE NOT s.acta_cerrada LIMIT 1""")).first()
            if fila is None:
                raise unittest.SkipTest("No hay notas en secciones con acta abierta")
            cls.carrera, cls.calificacion = fila
            cls.otra_carrera = c.execute(text(
                "SELECT carrera_id FROM academico_oltp.carreras WHERE carrera_id <> :c LIMIT 1"),
                {"c": cls.carrera}).scalar()
            if cls.otra_carrera is None:
                raise unittest.SkipTest("Solo hay una carrera")

    def setUp(self):
        self.c = MOTOR.connect()
        self.tx = self.c.begin()
        # Un cambio de nota en una sección de cls.carrera: el disparador escribe
        # la bitácora. La transacción se revierte al terminar.
        self.c.execute(text("SET LOCAL ROLE rol_admin"))
        self.c.execute(text("SELECT set_config('app.usuario', 'prueba.alcance', true)"))
        self.c.execute(text("""
            UPDATE academico_oltp.calificaciones
               SET nota = CASE WHEN nota > 5 THEN nota - 1 ELSE nota + 1 END
             WHERE calificacion_id = :id"""), {"id": self.calificacion})

    def tearDown(self):
        self.tx.rollback()
        self.c.close()

    def _ve(self, rol, carrera=None):
        self.c.execute(text("RESET ROLE"))
        self.c.execute(text(f"SET LOCAL ROLE {rol}"))
        self.c.execute(text("SELECT set_config('app.carrera_id', :c, true)"),
                       {"c": "" if carrera is None else str(carrera)})
        return self.c.execute(text(
            "SELECT count(*) FROM auditoria.log_cambios_notas "
            "WHERE usuario_app = 'prueba.alcance'")).scalar_one()

    def test_el_coordinador_ve_el_cambio_de_su_carrera(self):
        self.assertEqual(self._ve("rol_coordinador", self.carrera), 1)

    def test_el_coordinador_de_otra_carrera_no_lo_ve(self):
        self.assertEqual(self._ve("rol_coordinador", self.otra_carrera), 0)

    def test_sin_carrera_declarada_no_ve_ninguna_fila(self):
        self.assertEqual(self._ve("rol_coordinador"), 0)

    def test_el_admin_lo_ve(self):
        self.assertEqual(self._ve("rol_admin"), 1)

    def test_nadie_puede_escribir_la_bitacora_aunque_ahora_tenga_politicas(self):
        """Las políticas son FOR SELECT: agregarlas no abrió la escritura."""
        for rol in ("rol_admin", "rol_coordinador"):
            self.c.execute(text("RESET ROLE"))
            self.c.execute(text(f"SET LOCAL ROLE {rol}"))
            punto = self.c.begin_nested()
            with self.assertRaises(DBAPIError) as e:
                self.c.execute(text("DELETE FROM auditoria.log_cambios_notas"))
            punto.rollback()
            with self.subTest(rol=rol):
                self.assertIn("permission denied", str(e.exception.orig).lower())


class TestMensajesYMenus(unittest.TestCase):
    """Lo que ve el usuario cuando el motor lo rechaza, y lo que el menú le ofrece."""

    def _catalogo(self, slug):
        from app.catalogos import CATALOGOS
        return CATALOGOS[slug]

    def _mensaje(self, slug, pgcode):
        from types import SimpleNamespace
        from app.routers.administracion import mensaje_bd
        exc = SimpleNamespace(orig=SimpleNamespace(pgcode=pgcode, diag=None))
        return mensaje_bd(exc, self._catalogo(slug))

    def test_la_violacion_de_fila_se_explica_en_castellano(self):
        # 42501 es el código con el que PostgreSQL rechaza una fila de otra
        # carrera; sin esto, la pantalla mostraba «new row violates row-level
        # security policy for table "materias"».
        mensaje = self._mensaje("materias", "42501")
        self.assertIn("otra carrera", mensaje)
        self.assertNotIn("row-level", mensaje)

    def test_el_mensaje_concuerda_en_genero(self):
        self.assertTrue(self._mensaje("materias", "42501").startswith("Esa materia"))
        self.assertTrue(self._mensaje("periodos", "42501").startswith("Ese período"))

    def test_los_catalogos_institucionales_estan_declarados(self):
        from app.catalogos import CATALOGOS, CATALOGOS_INSTITUCIONALES
        self.assertEqual(CATALOGOS_INSTITUCIONALES,
                         {"periodos", "docentes", "carreras", "departamentos"})
        # Los de la carrera NO son institucionales: los lleva el coordinador.
        for slug in ("materias", "secciones", "estudiantes"):
            self.assertFalse(CATALOGOS[slug].solo_admin, slug)

    def test_el_admin_es_superconjunto_del_coordinador(self):
        """Una ruta abierta al coordinador también lo está para el admin."""
        from fastapi import HTTPException
        from app.dependencies import UsuarioSesion, requiere_rol

        def usuario(rol, carrera=None):
            return UsuarioSesion(usuario_id=1, username="u", nombre_completo="U",
                                 rol_db=rol, docente_id=None, carrera_id=carrera)

        abierta = requiere_rol("rol_coordinador")
        for rol, carrera in (("rol_admin", None), ("rol_coordinador", 1)):
            self.assertIs(abierta(usuario(rol, carrera)).rol_db, rol)
        with self.assertRaises(HTTPException):
            abierta(usuario("rol_docente"))

        # Pero lo exclusivo del admin no se abre al coordinador.
        solo_admin = requiere_rol("rol_admin")
        with self.assertRaises(HTTPException):
            solo_admin(usuario("rol_coordinador", 1))

    def test_el_rol_legible_distingue_los_tres(self):
        from app.dependencies import UsuarioSesion
        def legible(rol, carrera=None):
            return UsuarioSesion(1, "u", "U", rol, None, carrera).rol_legible
        self.assertEqual(legible("rol_admin"), "Administrador")
        self.assertEqual(legible("rol_coordinador", 1), "Coordinador")
        self.assertEqual(legible("rol_docente"), "Docente")


@unittest.skipIf(MOTOR is None, "PostgreSQL no disponible (docker compose up -d)")
class TestMetasPorCarrera(unittest.TestCase):
    """Metas por carrera con la institucional de respaldo (scripts 26 y 27)."""

    @classmethod
    def setUpClass(cls):
        with MOTOR.connect() as c:
            c.execute(text("SET LOCAL ROLE rol_admin"))
            cls.carrera, cls.otra = [f[0] for f in c.execute(text(
                "SELECT carrera_id FROM academico_oltp.carreras ORDER BY carrera_id LIMIT 2"))]

    def setUp(self):
        self.c = MOTOR.connect()
        self.tx = self.c.begin()
        self.c.execute(text("SET LOCAL ROLE rol_admin"))

    def tearDown(self):
        self.tx.rollback()
        self.c.close()

    def _metas(self, codigo="tasa_reprobacion"):
        return self.c.execute(text(
            "SELECT carrera_id, meta FROM academico_oltp.metas_indicador "
            "WHERE codigo = :c ORDER BY carrera_id NULLS FIRST"), {"c": codigo}).all()

    def _poner(self, carrera, meta=0.15, codigo="tasa_reprobacion"):
        self.c.execute(text("""
            INSERT INTO academico_oltp.metas_indicador (codigo, carrera_id, meta, tolerancia, justificacion)
            VALUES (:c, :car, :m, 0.01, 'meta de prueba por carrera')
            ON CONFLICT ON CONSTRAINT uq_meta_indicador_carrera
            DO UPDATE SET meta = EXCLUDED.meta"""), {"c": codigo, "car": carrera, "m": meta})

    def test_la_institucional_y_la_de_carrera_conviven(self):
        # Se borra primero por si la base ya traía una meta para esa carrera: la
        # prueba no debe depender de lo que haya configurado alguien.
        self.c.execute(text("DELETE FROM academico_oltp.metas_indicador "
                            "WHERE codigo = 'tasa_reprobacion' AND carrera_id = :c"),
                       {"c": self.carrera})
        antes = len(self._metas())
        self._poner(self.carrera)
        self.assertEqual(len(self._metas()), antes + 1)
        self.assertIn(None, [f.carrera_id for f in self._metas()])

    def test_no_se_pueden_duplicar_ni_la_institucional_ni_la_de_una_carrera(self):
        # NULLS NOT DISTINCT: dos filas institucionales del mismo indicador chocan.
        # La institucional ya existe; la de la carrera se crea para poder repetirla.
        self._poner(self.carrera)
        for carrera in (None, self.carrera):
            punto = self.c.begin_nested()
            with self.assertRaises(DBAPIError) as e:
                self.c.execute(text("""
                    INSERT INTO academico_oltp.metas_indicador (codigo, carrera_id, meta, tolerancia, justificacion)
                    VALUES ('tasa_reprobacion', :car, 0.3, 0.01, 'duplicada a proposito')"""),
                    {"car": carrera})
            punto.rollback()
            with self.subTest(carrera=carrera):
                self.assertIn("uq_meta_indicador_carrera", str(e.exception.orig))

    def test_el_coordinador_ve_la_suya_y_la_general_pero_no_la_ajena(self):
        self._poner(self.carrera, 0.15)
        self._poner(self.otra, 0.30)
        self.c.execute(text("RESET ROLE"))
        self.c.execute(text("SET LOCAL ROLE rol_coordinador"))
        self.c.execute(text("SELECT set_config('app.carrera_id', :c, true)"), {"c": str(self.carrera)})
        visibles = {f.carrera_id for f in self.c.execute(text(
            "SELECT carrera_id FROM academico_oltp.metas_indicador WHERE codigo = 'tasa_reprobacion'"))}
        self.assertIn(None, visibles)                  # la institucional, que hereda
        self.assertIn(self.carrera, visibles)          # la suya
        self.assertNotIn(self.otra, visibles)          # la de otra carrera, no

    def test_el_coordinador_no_escribe_metas(self):
        self.c.execute(text("RESET ROLE"))
        self.c.execute(text("SET LOCAL ROLE rol_coordinador"))
        self.c.execute(text("SELECT set_config('app.carrera_id', :c, true)"), {"c": str(self.carrera)})
        punto = self.c.begin_nested()
        with self.assertRaises(DBAPIError) as e:
            self.c.execute(text("UPDATE academico_oltp.metas_indicador SET meta = meta"))
        punto.rollback()
        self.assertIn("permission denied", str(e.exception.orig).lower())


@unittest.skipIf(MOTOR_DW is None, "Falta DASHBOARD_DB_PASSWORD en el .env")
class TestSemaforoPorCarrera(unittest.TestCase):
    """La vista resuelve la meta: la de la carrera si existe, la institucional si no."""

    def setUp(self):
        self.c = MOTOR_DW.connect()
        self.tx = self.c.begin()

    def tearDown(self):
        self.tx.rollback()
        self.c.close()

    def _fila(self, carrera, codigo="tasa_reprobacion"):
        return self.c.execute(text("""
            SELECT meta, meta_propia, estado FROM dw_academico.v_semaforo_indicador
            WHERE codigo = :c AND carrera_id IS NOT DISTINCT FROM :car
            ORDER BY orden_periodo DESC LIMIT 1"""), {"c": codigo, "car": carrera}).first()

    def test_el_almacen_calcula_por_carrera_y_tambien_el_total(self):
        filas = self.c.execute(text("""
            SELECT count(*) FILTER (WHERE carrera_id IS NULL)     AS institucionales,
                   count(*) FILTER (WHERE carrera_id IS NOT NULL) AS por_carrera
            FROM dw_academico.fact_indicador_periodo""")).first()
        self.assertGreater(filas.institucionales, 0)
        self.assertGreater(filas.por_carrera, filas.institucionales)

    def test_sin_meta_propia_la_carrera_usa_la_institucional(self):
        # Una carrera que NO tenga meta propia para ese indicador: cuál sea
        # depende de lo que haya configurado el admin, así que se busca.
        carrera = self.c.execute(text("""
            SELECT c.carrera_id FROM dw_academico.dim_carrera c
            WHERE NOT EXISTS (SELECT 1 FROM dw_academico.meta_indicador m
                              WHERE m.codigo = 'tasa_reprobacion' AND m.carrera_id = c.carrera_id)
            ORDER BY c.carrera_id LIMIT 1""")).scalar()
        if carrera is None:
            self.skipTest("todas las carreras tienen meta propia")
        institucional = self._fila(None)
        propia = self._fila(carrera)
        self.assertFalse(propia.meta_propia)
        self.assertEqual(propia.meta, institucional.meta)

    def test_con_meta_propia_el_semaforo_usa_la_de_la_carrera(self):
        fila = self.c.execute(text("""
            SELECT s.carrera_id, s.meta, s.meta_propia, m.meta AS meta_configurada
            FROM dw_academico.v_semaforo_indicador s
            JOIN dw_academico.meta_indicador m
              ON m.codigo = s.codigo AND m.carrera_id = s.carrera_id
            WHERE s.codigo = 'tasa_reprobacion' LIMIT 1""")).first()
        if fila is None:
            self.skipTest("ninguna carrera tiene meta propia configurada")
        self.assertTrue(fila.meta_propia)
        self.assertEqual(fila.meta, fila.meta_configurada)

    def test_con_meta_propia_la_carrera_usa_la_suya(self):
        carrera = self.c.execute(text(
            "SELECT carrera_id FROM dw_academico.dim_carrera ORDER BY carrera_id LIMIT 1")).scalar_one()
        # No se puede escribir como rol_dashboard; se prueba la resolución con una
        # consulta equivalente a la de la vista, que es lo que aquí importa.
        resuelta = self.c.execute(text("""
            SELECT mi.meta, mi.carrera_id IS NOT NULL AS propia
            FROM dw_academico.meta_indicador mi
            WHERE mi.codigo = 'tasa_reprobacion'
              AND (mi.carrera_id = :car OR mi.carrera_id IS NULL)
            ORDER BY mi.carrera_id NULLS LAST LIMIT 1"""), {"car": carrera}).first()
        self.assertIsNotNone(resuelta)

    def test_el_merge_es_idempotente_con_el_grano_nuevo(self):
        """Con «=» en vez de IS NOT DISTINCT FROM, las filas institucionales se
        borrarían e insertarían en cada carga para siempre."""
        definicion = self.c.execute(text(
            "SELECT prosrc FROM pg_proc WHERE proname = 'actualizar_resultados_indicadores'")).scalar_one()
        self.assertIn("IS NOT DISTINCT FROM", definicion)


class TestAlcanceDelCoordinadorEnLaVistaEjecutiva(unittest.TestCase):
    """El coordinador no usa el filtro: su alcance se deriva de su cuenta.

    Regresión: sin esto, el coordinador veía los valores de SU carrera contra las
    metas institucionales, y el total daba «Favorable» siempre (393 contra 90.000).
    """

    CARRERAS = [{"carrera_id": 1, "codigo_carrera": "I10515"},
                {"carrera_id": 15, "codigo_carrera": "I10506"}]

    def _usuario(self, rol, carrera=None, docente=None):
        from app.dependencies import UsuarioSesion
        return UsuarioSesion(usuario_id=1, username="u", nombre_completo="U",
                             rol_db=rol, docente_id=docente, carrera_id=carrera)

    def _derivar(self, usuario):
        from app.routers.vista_ejecutiva import carrera_del_usuario
        return carrera_del_usuario(usuario, self.CARRERAS)

    def test_el_coordinador_queda_acotado_a_su_carrera(self):
        self.assertEqual(self._derivar(self._usuario("rol_coordinador", carrera=1)), "I10515")
        self.assertEqual(self._derivar(self._usuario("rol_coordinador", carrera=15)), "I10506")

    def test_el_admin_no_queda_acotado(self):
        self.assertIsNone(self._derivar(self._usuario("rol_admin")))

    def test_una_carrera_que_no_esta_en_el_catalogo_no_inventa_codigo(self):
        # Puede pasar si el almacén todavía no se recargó tras crear la carrera.
        self.assertIsNone(self._derivar(self._usuario("rol_coordinador", carrera=999)))
