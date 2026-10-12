"""Acceso al dashboard de Streamlit con la sesión de la app (nginx auth_request).

    cd backend && python -m unittest discover -s tests -v
"""

import os
import unittest
from types import SimpleNamespace

# Las rutas importan la configuración, que exige estas dos variables. Valores de
# prueba: aquí no se conecta a nada.
os.environ.setdefault("APP_DB_PASSWORD", "x")
os.environ.setdefault("APP_SECRET_KEY", "y")

from app.routers.auth import destino_seguro, verificar_acceso_coordinador  # noqa: E402


def _peticion(rol=None):
    sesion = {}
    if rol:
        sesion["usuario"] = {"usuario_id": 1, "username": "u", "nombre_completo": "U",
                             "rol_db": rol, "docente_id": None}
    return SimpleNamespace(session=sesion)


class TestVerificacionParaNginx(unittest.TestCase):
    def test_coordinador_pasa(self):
        self.assertEqual(verificar_acceso_coordinador(_peticion("rol_coordinador")).status_code, 204)

    def test_sin_sesion_es_401_para_que_nginx_mande_al_login(self):
        self.assertEqual(verificar_acceso_coordinador(_peticion()).status_code, 401)

    def test_docente_es_403_no_se_le_manda_a_un_login_que_ya_hizo(self):
        self.assertEqual(verificar_acceso_coordinador(_peticion("rol_docente")).status_code, 403)

    def test_la_respuesta_no_se_guarda_en_cache(self):
        r = verificar_acceso_coordinador(_peticion("rol_coordinador"))
        self.assertEqual(r.headers["cache-control"], "no-store")

    def test_no_devuelve_cuerpo(self):
        self.assertEqual(verificar_acceso_coordinador(_peticion("rol_coordinador")).body, b"")


class TestDestinoTrasElLogin(unittest.TestCase):
    def test_rutas_del_propio_sitio_se_respetan(self):
        for ruta in ("/analitica/", "/red-curricular", "/matricula?periodo_id=8"):
            self.assertEqual(destino_seguro(ruta), ruta)

    def test_no_es_un_redirector_abierto(self):
        for malo in ("//otro.sitio", "https://otro.sitio", "http://otro.sitio/x", "javascript:alert(1)",
                     "/\\otro.sitio", "otro.sitio", "/ok\r\nSet-Cookie: x=1", None, ""):
            self.assertEqual(destino_seguro(malo), "/", repr(malo))


if __name__ == "__main__":
    unittest.main()
