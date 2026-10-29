"""Mi cuenta (datos del perfil, contraseña y apariencia) y la pantalla de ingreso.

    cd backend && python -m unittest discover -s tests -v

No toca la base: la sesión de BD es un doble y la cuenta se da por vigente.
"""

import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock

# Las rutas importan la configuración, que exige estas dos variables. Valores de
# prueba: aquí no se conecta a nada.
os.environ.setdefault("APP_DB_PASSWORD", "x")
os.environ.setdefault("APP_SECRET_KEY", "y")

from sqlalchemy.exc import DBAPIError  # noqa: E402

from app import dependencies  # noqa: E402
from app.dependencies import UsuarioSesion  # noqa: E402
from app.routers import usuarios  # noqa: E402


class TestAyudas(unittest.TestCase):
    def test_el_nombre_se_normaliza_como_lo_hace_la_base(self):
        self.assertEqual(usuarios.normalizar_nombre("  Ana   María \n López "), "Ana María López")
        self.assertEqual(usuarios.normalizar_nombre("   "), "")

    def test_la_hora_se_muestra_en_el_horario_de_el_salvador(self):
        # UTC-6 todo el año (no hay horario de verano).
        self.assertEqual(usuarios.hora_local(datetime(2026, 10, 29, 17, 55, tzinfo=timezone.utc)), "29/10/2026 11:55")
        self.assertEqual(usuarios.hora_local(datetime(2026, 1, 1, 3, 0, tzinfo=timezone.utc)), "31/12/2025 21:00")

    def test_una_fecha_sin_zona_se_toma_como_utc_y_none_no_se_inventa(self):
        self.assertEqual(usuarios.hora_local(datetime(2026, 10, 29, 17, 55)), "29/10/2026 11:55")
        self.assertIsNone(usuarios.hora_local(None))


def _usuario(**extra):
    datos = dict(usuario_id=7, username="ana.lopez", nombre_completo="Ana María López",
                 rol_db="rol_docente", docente_id=3)
    datos.update(extra)
    return UsuarioSesion(**datos)


def _renderizar(plantilla, request, **contexto):
    """La plantilla tal como la muestra la ruta, sin levantar la aplicación."""
    from app.templating import templates
    contexto.setdefault("url_for", lambda *a, **k: "/static/x")
    return templates.env.get_template(plantilla).render(request=request, **contexto)


class TestPantallaMiCuenta(unittest.TestCase):
    def setUp(self):
        self.db = mock.Mock()
        self.db.scalar.return_value = SimpleNamespace(
            ultimo_acceso=datetime(2026, 10, 29, 17, 55, tzinfo=timezone.utc), password_cambiado_en=None,
            creado_en=datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc))
        self.db.get.return_value = SimpleNamespace(codigo_docente="DOC-014")
        self.peticion = SimpleNamespace(session={"csrf": "t"}, url=SimpleNamespace(path="/cuenta"))

    def _pagina(self, usuario=None, sesion_extra=None):
        usuario = usuario or _usuario()
        self.peticion.session.update(sesion_extra or {})
        with mock.patch.object(usuarios, "templates") as plantillas:
            usuarios.ver_cuenta(self.peticion, usuario, self.db)
        contexto = plantillas.TemplateResponse.call_args.args[2]
        return _renderizar("modulos/cuenta.html", self.peticion, **contexto)

    def test_muestra_el_perfil_y_los_datos_de_la_cuenta(self):
        html = self._pagina()
        self.assertIn("Mi cuenta", html)
        self.assertIn('value="Ana María López"', html)
        self.assertIn("ana.lopez", html)
        self.assertIn("DOC-014", html)
        self.assertIn("29/10/2026 11:55", html)          # último acceso, en hora local
        self.assertIn("01/09/2026 09:00", html)          # cuenta creada
        self.assertIn("Nunca desde que se creó", html)   # contraseña sin cambios
        self.assertRegex(html, r">\s*AL\s*<")                      # iniciales del avatar

    def test_el_perfil_la_contrasena_y_la_apariencia_viven_en_la_misma_pantalla(self):
        html = self._pagina()
        self.assertIn('action="/cuenta/perfil"', html)
        self.assertIn('action="/cuenta/contrasena"', html)
        for tema in ("auto", "light", "dark"):
            self.assertIn(f'data-tema="{tema}"', html)

    def test_la_barra_superior_lleva_a_mi_cuenta_y_ya_no_tiene_el_boton_de_la_contrasena(self):
        html = self._pagina()
        self.assertNotIn("Mi contraseña</a>", html)
        self.assertIn('class="topbar-cuenta is-active"', html)
        self.assertIn('href="/cuenta"', html)
        self.assertIn('action="/logout"', html)

    def test_no_muestra_nada_de_la_arquitectura_interna(self):
        html = self._pagina()
        for texto in ("SET LOCAL ROLE", "PostgreSQL 17", "Neo4j GraphDB", "Docker Compose", "rol_docente"):
            self.assertNotIn(texto, html, texto)

    def test_un_coordinador_no_ve_codigo_de_docente(self):
        self.db.get.return_value = None
        html = self._pagina(_usuario(rol_db="rol_coordinador", docente_id=None))
        self.assertNotIn("Código de docente", html)
        self.assertIn("Coordinador", html)

    def test_con_contrasena_temporal_avisa_que_hay_que_cambiarla(self):
        self.assertNotIn("contraseña temporal", self._pagina())
        self.assertIn("contraseña temporal", self._pagina(sesion_extra={dependencies.CLAVE_CAMBIO_OBLIGATORIO: True}))

    def test_el_enlace_viejo_de_la_contrasena_lleva_a_mi_cuenta(self):
        r = usuarios.ver_cambio()
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/cuenta"))


class TestActualizarPerfil(unittest.TestCase):
    def setUp(self):
        self.db = mock.Mock()
        self.sesion = {"usuario": {"usuario_id": 7, "username": "ana.lopez", "nombre_completo": "Ana María López",
                                   "rol_db": "rol_docente", "docente_id": 3}}
        self.peticion = SimpleNamespace(session=self.sesion)

    def _enviar(self, nombre):
        return usuarios.actualizar_perfil(self.peticion, nombre, _usuario(), self.db)

    def test_guarda_el_nombre_normalizado_y_lo_refleja_en_la_sesion(self):
        r = self._enviar("  Ana   María  López de Pérez ")
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/cuenta"))
        sentencia, parametros = self.db.execute.call_args.args
        self.assertIn("actualizar_perfil_propio", str(sentencia))
        self.assertEqual(parametros, {"n": "Ana María López de Pérez"})
        self.assertEqual(self.sesion["usuario"]["nombre_completo"], "Ana María López de Pérez")
        self.assertIn("actualizaron", self.sesion["aviso"]["ok"])

    def test_los_demas_datos_de_la_sesion_no_cambian(self):
        self._enviar("Otro Nombre")
        self.assertEqual(self.sesion["usuario"]["rol_db"], "rol_docente")
        self.assertEqual(self.sesion["usuario"]["docente_id"], 3)

    def test_un_nombre_vacio_o_demasiado_corto_o_largo_se_rechaza_sin_tocar_la_base(self):
        for malo in ("   ", "Al", "x" * 121):
            self.sesion.pop("aviso", None)
            self._enviar(malo)
            self.assertIn("entre 3 y 120", self.sesion["aviso"]["error"], malo)
        self.db.execute.assert_not_called()

    def test_sin_cambios_no_escribe(self):
        self._enviar("Ana María López")
        self.db.execute.assert_not_called()
        self.assertIn("No había cambios", self.sesion["aviso"]["ok"])

    def test_si_la_base_lo_rechaza_se_muestra_su_motivo_y_la_sesion_no_cambia(self):
        orig = SimpleNamespace(diag=SimpleNamespace(constraint_name=None, message_primary="Cuenta desactivada"))
        self.db.execute.side_effect = DBAPIError("SELECT", {}, orig)
        self._enviar("Otro Nombre")
        self.db.rollback.assert_called_once()
        self.assertEqual(self.sesion["aviso"]["error"], "Cuenta desactivada")
        self.assertEqual(self.sesion["usuario"]["nombre_completo"], "Ana María López")


class TestCambioObligatorio(unittest.TestCase):
    def test_la_contrasena_temporal_se_cambia_desde_mi_cuenta(self):
        for ruta in ("/cuenta", "/cuenta/contrasena", "/cuenta/perfil", "/logout"):
            self.assertIn(ruta, dependencies.RUTAS_SIN_CAMBIO)


class TestPantallaDeIngreso(unittest.TestCase):
    def _html(self, **contexto):
        peticion = SimpleNamespace(session={"csrf": "t"}, url=SimpleNamespace(path="/login"))
        base = {"siguiente": "/", "modo_demo": False, "error": None}
        base.update(contexto)
        return _renderizar("login.html", peticion, **base)

    def test_solo_pide_usuario_y_contrasena(self):
        html = self._html()
        self.assertIn('id="username"', html)
        self.assertIn('id="password"', html)
        self.assertIn("Ingresar", html)

    def test_no_muestra_detalles_internos_ni_decoracion_tecnica(self):
        html = self._html()
        for texto in ("SET LOCAL ROLE", "BEGIN;", "fail-closed", "Arquitectura de seguridad", "rol_app",
                      "PostgreSQL", "Neo4j", "Docker", "FastAPI", "rolSelector", "Coordinación Académica"):
            self.assertNotIn(texto, html, texto)

    def test_el_acceso_de_demostracion_solo_aparece_con_modo_demo(self):
        self.assertNotIn("js-demo-login", self._html(modo_demo=False))
        self.assertIn("js-demo-login", self._html(modo_demo=True))

    def test_muestra_el_error(self):
        self.assertIn("Credenciales inválidas", self._html(error="Credenciales inválidas"))


if __name__ == "__main__":
    unittest.main()
