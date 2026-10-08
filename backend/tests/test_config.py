"""Configuración de la sesión web — cookie Secure por entorno.

    cd backend && python -m unittest discover -s tests -v
"""

import unittest
from unittest import mock

from app.config import Settings


def _ajustes(**entorno):
    """Settings sin leer el .env del proyecto: solo lo que se pasa aquí."""
    base = {"APP_DB_PASSWORD": "x", "APP_SECRET_KEY": "y"}
    base.update(entorno)
    with mock.patch.dict("os.environ", base, clear=True):
        return Settings(_env_file=None)


class TestCookieSecure(unittest.TestCase):
    def test_apagada_por_defecto(self):
        # En http://localhost una cookie Secure se descarta y nadie podría entrar.
        self.assertFalse(_ajustes().cookie_secure)

    def test_se_activa_por_entorno(self):
        self.assertTrue(_ajustes(COOKIE_SECURE="true").cookie_secure)

    def test_modo_demo_sigue_apagado_por_defecto(self):
        self.assertFalse(_ajustes().modo_demo)


if __name__ == "__main__":
    unittest.main()
