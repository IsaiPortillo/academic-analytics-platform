"""Pruebas de la configuración de la app Streamlit — SCRUM-44.

No tocan la base de datos. Fijan el criterio de credenciales del ticket:
variables de entorno desde el .env, un rol de solo lectura, y nada de
credenciales en el código ni de más (el dashboard no carga las del rol de
servicio de la aplicación web).

    python -m unittest discover -s dashboard/tests -t . -v
"""

import unittest

from dashboard.config import ErrorConfiguracion, SettingsDashboard


def _config(**valores):
    # _env_file=None: la prueba no depende del .env de quien la corre.
    return SettingsDashboard(_env_file=None, **valores)


class TestConfiguracionDashboard(unittest.TestCase):
    def test_usa_el_rol_de_solo_lectura_por_defecto(self):
        self.assertEqual(_config(dashboard_db_password="x").dashboard_db_user, "rol_dashboard")

    def test_sin_contrasena_falla_con_un_mensaje_claro_y_no_antes(self):
        config = _config(dashboard_db_password=None)  # construirla no falla
        with self.assertRaises(ErrorConfiguracion) as ctx:
            config.database_url
        self.assertIn("DASHBOARD_DB_PASSWORD", str(ctx.exception))

    def test_la_url_sale_de_la_configuracion(self):
        url = _config(dashboard_db_password="secreto", postgres_host="db", postgres_port=5433,
                      postgres_db="otra").database_url
        self.assertEqual(url, "postgresql+psycopg2://rol_dashboard:secreto@db:5433/otra")

    def test_no_exige_las_credenciales_del_rol_de_servicio(self):
        campos = set(SettingsDashboard.model_fields)
        self.assertFalse(any(c.startswith("app_") for c in campos), campos)
        # Y por eso se puede construir sin APP_DB_PASSWORD ni APP_SECRET_KEY.
        _config(dashboard_db_password="x")


if __name__ == "__main__":
    unittest.main()
