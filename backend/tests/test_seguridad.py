"""Pruebas de seguridad de la aplicación web (sin base de datos).

CSRF, mensajes en la sesión, límite de intentos de login, vigencia de la sesión
y el docente que get_db declara para la seguridad por fila.

    cd backend && python -m unittest tests.test_seguridad -v
"""

import asyncio
import os
import re
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("APP_DB_PASSWORD", "x")
os.environ.setdefault("APP_SECRET_KEY", "y")

from fastapi import HTTPException  # noqa: E402
from starlette.requests import Request  # noqa: E402

from app import avisos, csrf, database, dependencies  # noqa: E402
from app.limite_login import LimiteIntentos  # noqa: E402
from app.main import app  # noqa: E402
from app.routers import auth  # noqa: E402
from app.security import hashear_password  # noqa: E402
from app.templating import templates  # noqa: E402

RAIZ_APP = Path(__file__).resolve().parents[1] / "app"


def _peticion(metodo="POST", sesion=None, form=None, cabeceras=None):
    async def leer_form():
        return form or {}
    return SimpleNamespace(method=metodo, session={} if sesion is None else sesion,
                           headers=cabeceras or {}, form=leer_form, state=SimpleNamespace())


def _verificar(peticion):
    asyncio.run(csrf.verificar_csrf(peticion))


FORM = {"content-type": "application/x-www-form-urlencoded"}

RUTAS_POST = [
    "/login", "/logout", "/cuenta/contrasena", "/cuenta/perfil",
    "/matricula/inscribir", "/matricula/retirar/1", "/matricula/importar", "/matricula/importar/confirmar",
    "/calificaciones/evaluaciones", "/calificaciones/registrar", "/calificaciones/evaluaciones/1/editar",
    "/calificaciones/evaluaciones/1/eliminar", "/calificaciones/importar", "/calificaciones/importar/confirmar",
    "/calificaciones/acta/cerrar", "/calificaciones/acta/reabrir", "/calificaciones/buscar",
    "/asistencia/registrar", "/asistencia/sesion/eliminar", "/asistencia/importar", "/asistencia/importar/confirmar",
    "/costos/recargar", "/costos/1",
    "/usuarios", "/usuarios/1/editar", "/usuarios/1/estado", "/usuarios/1/restablecer",
    "/admin/materias/nuevo", "/admin/materias/1", "/admin/materias/1/eliminar",
    "/admin/materias/importar", "/admin/materias/importar/confirmar",
    "/admin/malla/agregar", "/admin/malla/quitar", "/admin/malla/sincronizar",
    "/admin/metas/tasa_reprobacion", "/almacen/validar",
]


def _post_asgi(ruta, cuerpo):
    """POST de formulario directo a la app ASGI (sin servidor ni httpx)."""
    respuesta = {"estado": None, "cuerpo": b""}
    enviado = False

    async def recibir():
        nonlocal enviado
        if enviado:
            return {"type": "http.disconnect"}
        enviado = True
        return {"type": "http.request", "body": cuerpo, "more_body": False}

    async def enviar(mensaje):
        if mensaje["type"] == "http.response.start":
            respuesta["estado"] = mensaje["status"]
        elif mensaje["type"] == "http.response.body":
            respuesta["cuerpo"] += mensaje.get("body", b"")

    alcance = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
               "scheme": "http", "path": ruta, "raw_path": ruta.encode(), "query_string": b"",
               "root_path": "", "server": ("testserver", 80), "client": ("1.2.3.4", 5000),
               "headers": [(b"host", b"testserver"),
                           (b"content-type", b"application/x-www-form-urlencoded"),
                           (b"content-length", str(len(cuerpo)).encode())]}
    asyncio.run(app(alcance, recibir, enviar))
    return respuesta["estado"], respuesta["cuerpo"].decode("utf-8", "replace")


class TestCSRF(unittest.TestCase):
    def test_el_token_se_crea_una_vez_y_se_reutiliza(self):
        p = _peticion()
        token = csrf.token_csrf(p)
        self.assertGreaterEqual(len(token), 40)
        self.assertEqual(csrf.token_csrf(p), token)

    def test_get_no_lo_exige(self):
        _verificar(_peticion("GET"))

    def test_post_sin_token_es_403(self):
        with self.assertRaises(HTTPException) as e:
            _verificar(_peticion(sesion={"csrf": "bueno"}, cabeceras=FORM))
        self.assertEqual(e.exception.status_code, 403)

    def test_post_con_token_equivocado_es_403(self):
        with self.assertRaises(HTTPException):
            _verificar(_peticion(sesion={"csrf": "bueno"}, cabeceras=FORM, form={"csrf_token": "malo"}))

    def test_sin_token_en_la_sesion_nada_pasa(self):
        # Otro sitio no puede "adivinar" un token si la sesión no tiene ninguno.
        with self.assertRaises(HTTPException):
            _verificar(_peticion(sesion={}, cabeceras=FORM, form={"csrf_token": ""}))

    def test_post_con_el_token_del_formulario_pasa(self):
        _verificar(_peticion(sesion={"csrf": "bueno"}, cabeceras=FORM, form={"csrf_token": "bueno"}))

    def test_post_con_el_token_en_la_cabecera_pasa(self):
        _verificar(_peticion(sesion={"csrf": "bueno"}, cabeceras={"X-CSRF-Token": "bueno"}))

    def test_renovar_cambia_el_token(self):
        p = _peticion(sesion={"csrf": "viejo"})
        self.assertNotEqual(csrf.renovar_token(p), "viejo")

    def test_el_campo_oculto_lleva_el_token_de_la_sesion(self):
        p = _peticion(sesion={"csrf": "abc123"})
        html = templates.env.from_string("{{ csrf_campo() }}").render(request=p)
        self.assertEqual(html, '<input type="hidden" name="csrf_token" value="abc123">')

    def test_todas_las_rutas_post_lo_exigen(self):
        # Petición real a la aplicación ASGI, sin sesión ni token: el rechazo debe
        # llegar antes que cualquier otra cosa (ni login, ni rol, ni base de datos).
        for ruta in RUTAS_POST:
            estado, cuerpo = _post_asgi(ruta, b"periodo_id=1&seccion_id=1")
            self.assertEqual(estado, 403, ruta)
            self.assertIn("El formulario caducó", cuerpo, ruta)

    def test_no_queda_ninguna_ruta_post_sin_listar(self):
        codigo = "\n".join(f.read_text(encoding="utf-8") for f in (RAIZ_APP / "routers").glob("*.py"))
        self.assertEqual(len(re.findall(r"@router\.post\(", codigo)), len(RUTAS_POST))

    def test_todo_formulario_post_incluye_el_campo(self):
        plantillas = list((RAIZ_APP / "templates").rglob("*.html"))
        formularios = 0
        for archivo in plantillas:
            texto = archivo.read_text(encoding="utf-8")
            for m in re.finditer(r'<form[^>]*method="post"[^>]*>(.*?)</form>', texto, re.S | re.I):
                formularios += 1
                self.assertIn("csrf_campo()", m.group(1), f"{archivo.name}: {m.group(0)[:80]}")
        self.assertGreaterEqual(formularios, 8)

    def test_el_dock_de_matricula_envia_el_token(self):
        js = (RAIZ_APP / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('"csrf_token"', js)
        self.assertNotIn('fetch("/matricula/inscribir"', js)


class TestAvisos(unittest.TestCase):
    def test_el_mensaje_va_a_la_sesion_no_a_la_url(self):
        p = _peticion()
        r = avisos.redirigir(p, "/matricula?periodo_id=1", error="Sección no encontrada")
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], "/matricula?periodo_id=1")
        self.assertEqual(p.session["aviso"], {"error": "Sección no encontrada"})

    def test_se_muestra_una_sola_vez(self):
        p = _peticion(sesion={"aviso": {"ok": "Listo"}})
        self.assertEqual(avisos.tomar_aviso(p), ("Listo", None))
        self.assertEqual(avisos.tomar_aviso(p), (None, None))

    def test_sin_mensaje_no_ensucia_la_sesion(self):
        p = _peticion()
        avisos.redirigir(p, "/costos")
        self.assertNotIn("aviso", p.session)

    def test_ningun_router_pone_mensajes_en_la_url(self):
        for archivo in (RAIZ_APP / "routers").glob("*.py"):
            texto = archivo.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"[?&](ok|error)=", texto), archivo.name)
            self.assertNotRegex(texto, r"(ok|error): Optional\[str\] = Query", archivo.name)


class TestLimiteIntentos(unittest.TestCase):
    def setUp(self):
        self.ahora = 1000.0
        self.limite = LimiteIntentos(max_por_cuenta=5, max_por_ip=20, ventana_s=900, bloqueo_s=900,
                                     reloj=lambda: self.ahora)

    def _fallar(self, n, ip="1.1.1.1", usuario="ana"):
        for _ in range(n):
            self.limite.registrar_fallo(ip, usuario)

    def test_cuatro_fallos_no_bloquean_el_quinto_si(self):
        self._fallar(4)
        self.assertEqual(self.limite.segundos_de_bloqueo("1.1.1.1", "ana"), 0)
        self._fallar(1)
        self.assertEqual(self.limite.segundos_de_bloqueo("1.1.1.1", "ana"), 900)

    def test_el_bloqueo_expira(self):
        self._fallar(5)
        self.ahora += 901
        self.assertEqual(self.limite.segundos_de_bloqueo("1.1.1.1", "ana"), 0)

    def test_fallos_fuera_de_la_ventana_no_suman(self):
        self._fallar(4)
        self.ahora += 901
        self._fallar(1)
        self.assertEqual(self.limite.segundos_de_bloqueo("1.1.1.1", "ana"), 0)

    def test_mayusculas_y_espacios_no_esquivan_el_bloqueo(self):
        for usuario in ("ana", "ANA", " Ana", "aNa ", "ana"):
            self.limite.registrar_fallo("1.1.1.1", usuario)
        self.assertGreater(self.limite.segundos_de_bloqueo("1.1.1.1", "ana"), 0)

    def test_el_exito_limpia_los_fallos_de_esa_cuenta(self):
        self._fallar(4)
        self.limite.registrar_exito("1.1.1.1", "ana")
        self._fallar(4)
        self.assertEqual(self.limite.segundos_de_bloqueo("1.1.1.1", "ana"), 0)

    def test_otra_ip_no_queda_bloqueada(self):
        self._fallar(5)
        self.assertEqual(self.limite.segundos_de_bloqueo("2.2.2.2", "ana"), 0)

    def test_recorrer_cuentas_desde_una_ip_la_bloquea(self):
        for i in range(20):
            self.limite.registrar_fallo("1.1.1.1", f"usuario{i}")
        self.assertGreater(self.limite.segundos_de_bloqueo("1.1.1.1", "otra_cuenta"), 0)
        self.assertEqual(self.limite.segundos_de_bloqueo("2.2.2.2", "otra_cuenta"), 0)


def _request_login(ip="9.9.9.9", sesion=None):
    alcance = {"type": "http", "method": "POST", "path": "/login", "headers": [],
               "query_string": b"", "client": (ip, 5000), "session": {} if sesion is None else sesion,
               "app": app}
    return Request(alcance)


class TestLoginConLimite(unittest.TestCase):
    def setUp(self):
        self.limite = LimiteIntentos(max_por_cuenta=5, max_por_ip=20, ventana_s=900, bloqueo_s=900)
        parche = mock.patch.object(auth, "limite_login", self.limite)
        parche.start()
        self.addCleanup(parche.stop)

    def test_tras_cinco_fallos_responde_429_sin_consultar_la_base(self):
        db = mock.Mock()
        db.scalar.return_value = None  # usuario inexistente
        for _ in range(5):
            r = auth.procesar_login(_request_login(), "ana", "mala", "", db)
            self.assertEqual(r.status_code, 401)
        consultas = db.scalar.call_count
        r = auth.procesar_login(_request_login(), "ana", "mala", "", db)
        self.assertEqual(r.status_code, 429)
        self.assertIn("retry-after", r.headers)
        self.assertEqual(db.scalar.call_count, consultas)

    def test_el_login_correcto_renueva_la_sesion(self):
        usuario = SimpleNamespace(usuario_id=7, username="ana", nombre_completo="Ana",
                                  rol_db="rol_docente", docente_id=3,
                                  password_hash=hashear_password("buena"), debe_cambiar_password=False)
        db = mock.Mock()
        db.scalar.return_value = usuario
        sesion = {"csrf": "token-anterior", "aviso": {"ok": "viejo"}, "otro": 1}
        r = auth.procesar_login(_request_login(sesion=sesion), "ana", "buena", "/asistencia", db)
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], "/asistencia")
        self.assertEqual(sesion["usuario"]["docente_id"], 3)
        self.assertNotIn("otro", sesion)
        self.assertNotIn("aviso", sesion)
        self.assertNotEqual(sesion["csrf"], "token-anterior")
        self.assertAlmostEqual(sesion["ultima_actividad"], time.time(), delta=5)
        self.assertEqual(sesion["huella"], dependencies.huella_password(usuario.password_hash))
        self.assertNotIn("debe_cambiar_password", sesion)

    def test_con_contrasena_temporal_va_directo_a_cambiarla(self):
        usuario = SimpleNamespace(usuario_id=8, username="beto", nombre_completo="Beto", rol_db="rol_docente",
                                  docente_id=4, password_hash=hashear_password("Temporal2026x"),
                                  debe_cambiar_password=True)
        db = mock.Mock()
        db.scalar.return_value = usuario
        sesion = {}
        r = auth.procesar_login(_request_login(sesion=sesion), "beto", "Temporal2026x", "/asistencia", db)
        self.assertEqual(r.headers["location"], "/cuenta")
        self.assertTrue(sesion["debe_cambiar_password"])


def _sesion_valida(**extra):
    datos = {"usuario_id": 7, "username": "ana", "nombre_completo": "Ana",
             "rol_db": "rol_docente", "docente_id": 3}
    return {"usuario": datos, "ultima_actividad": int(time.time()), "csrf": "t", "huella": "h", **extra}


class TestVigenciaDeLaSesion(unittest.TestCase):
    def _cuenta(self, fila, huella):
        conexion = mock.MagicMock()
        conexion.__enter__.return_value.execute.return_value.first.return_value = fila
        datos = {"usuario_id": 7, "rol_db": "rol_docente", "docente_id": 3}
        with mock.patch.object(dependencies.engine, "connect", return_value=conexion):
            return dependencies.cuenta_vigente(datos, huella)

    def test_vigente_con_mismo_rol_y_misma_contrasena(self):
        fila = SimpleNamespace(rol_db="rol_docente", docente_id=3, password_hash="$2b$12$abc")
        self.assertTrue(self._cuenta(fila, dependencies.huella_password("$2b$12$abc")))

    def test_otra_contrasena_corta_la_sesion(self):
        fila = SimpleNamespace(rol_db="rol_docente", docente_id=3, password_hash="$2b$12$nueva")
        self.assertFalse(self._cuenta(fila, dependencies.huella_password("$2b$12$abc")))

    def test_sin_huella_la_sesion_no_vale(self):
        # Sesiones abiertas antes de existir la huella: se cierran una vez.
        fila = SimpleNamespace(rol_db="rol_docente", docente_id=3, password_hash="$2b$12$abc")
        self.assertFalse(self._cuenta(fila, None))

    def test_otro_rol_o_cuenta_inactiva_corta_la_sesion(self):
        self.assertFalse(self._cuenta(SimpleNamespace(rol_db="rol_coordinador", docente_id=None,
                                                      password_hash="$2b$12$abc"),
                                      dependencies.huella_password("$2b$12$abc")))
        self.assertFalse(self._cuenta(None, dependencies.huella_password("$2b$12$abc")))

    def test_la_huella_cambia_con_la_contrasena(self):
        h1 = dependencies.huella_password(hashear_password("Una2026clave"))
        h2 = dependencies.huella_password(hashear_password("Una2026clave"))
        self.assertEqual(len(h1), 16)
        self.assertNotEqual(h1, h2)   # bcrypt usa sal: otro hash, otra huella

    def test_sesion_activa_y_cuenta_vigente(self):
        p = _peticion("GET", sesion=_sesion_valida())
        with mock.patch.object(dependencies, "cuenta_vigente", return_value=True):
            self.assertEqual(dependencies.usuario_opcional(p).docente_id, 3)

    def test_cuenta_desactivada_cierra_la_sesion_en_el_siguiente_clic(self):
        p = _peticion("GET", sesion=_sesion_valida())
        with mock.patch.object(dependencies, "cuenta_vigente", return_value=False):
            self.assertIsNone(dependencies.usuario_opcional(p))
        self.assertEqual(p.session, {})

    def test_inactividad_cierra_la_sesion(self):
        p = _peticion("GET", sesion=_sesion_valida(ultima_actividad=int(time.time()) - 31 * 60))
        with mock.patch.object(dependencies, "cuenta_vigente", return_value=True) as vigente:
            self.assertIsNone(dependencies.usuario_opcional(p))
        self.assertEqual(p.session, {})
        vigente.assert_not_called()

    def test_una_cookie_anterior_al_cambio_no_vale(self):
        sesion = _sesion_valida()
        del sesion["ultima_actividad"]
        with mock.patch.object(dependencies, "cuenta_vigente", return_value=True):
            self.assertIsNone(dependencies.usuario_opcional(_peticion("GET", sesion=sesion)))

    def test_cada_clic_renueva_la_actividad(self):
        p = _peticion("GET", sesion=_sesion_valida(ultima_actividad=int(time.time()) - 20 * 60))
        with mock.patch.object(dependencies, "cuenta_vigente", return_value=True):
            dependencies.usuario_opcional(p)
        self.assertAlmostEqual(p.session["ultima_actividad"], time.time(), delta=5)

    def test_se_consulta_la_base_una_sola_vez_por_peticion(self):
        p = _peticion("GET", sesion=_sesion_valida())
        with mock.patch.object(dependencies, "cuenta_vigente", return_value=True) as vigente:
            dependencies.usuario_opcional(p)
            dependencies.usuario_opcional(p)
        vigente.assert_called_once()

    def test_la_cookie_dura_horas_no_dos_semanas(self):
        sesiones = [m for m in app.user_middleware if m.cls.__name__ == "SessionMiddleware"]
        self.assertEqual(sesiones[0].kwargs["max_age"], 8 * 3600)


class TestDocenteParaSeguridadPorFila(unittest.TestCase):
    def _sentencias(self, datos_usuario):
        db = mock.Mock()
        with mock.patch.object(database, "SessionLocal", return_value=db):
            generador = database.get_db(SimpleNamespace(session={"usuario": datos_usuario}))
            next(generador)
            generador.close()
        return [(str(c.args[0]), c.args[1] if len(c.args) > 1 else None) for c in db.execute.call_args_list]

    def test_el_docente_declara_su_id_en_la_transaccion(self):
        sentencias = self._sentencias({"rol_db": "rol_docente", "docente_id": 3, "username": "ana", "usuario_id": 7})
        self.assertEqual(sentencias[0][0], "SET LOCAL ROLE rol_docente")
        self.assertIn("set_config('app.usuario', :usuario, true)", sentencias[1][0])
        self.assertEqual(sentencias[1][1], {"usuario": "ana", "usuario_id": "7"})
        self.assertIn("set_config('app.docente_id', :docente, true)", sentencias[2][0])
        self.assertEqual(sentencias[2][1], {"docente": "3"})

    def test_el_coordinador_no_declara_docente(self):
        sentencias = self._sentencias({"rol_db": "rol_coordinador", "docente_id": None, "username": "coord",
                                       "usuario_id": 1})
        self.assertEqual(len(sentencias), 2)
        self.assertEqual(sentencias[0][0], "SET LOCAL ROLE rol_coordinador")
        self.assertNotIn("app.docente_id", sentencias[1][0])

    def test_sin_sesion_no_declara_nada(self):
        self.assertEqual(self._sentencias({}), [])


if __name__ == "__main__":
    unittest.main()
