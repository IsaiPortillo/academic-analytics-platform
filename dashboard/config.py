"""Configuración de la app Streamlit — SCRUM-44 (Fase 4.1).

Mismo patrón que etl/config.py y backend/app/config.py: las credenciales salen
del .env de la raíz, nunca del código. La diferencia es el rol de PostgreSQL:
aquí rol_dashboard, que solo tiene SELECT sobre dw_academico y ningún permiso
sobre academico_oltp. Que el dashboard no pueda leer el sistema transaccional
no depende de que este código se porte bien, sino de los GRANT del motor.

A propósito NO carga APP_DB_PASSWORD ni APP_SECRET_KEY: son del rol de servicio
y de la sesión de la aplicación web, y este proceso no tiene por qué verlas.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ_PROYECTO = Path(__file__).resolve().parents[1]


class ErrorConfiguracion(Exception):
    """Falta una credencial que el dashboard necesita."""


class SettingsDashboard(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=RAIZ_PROYECTO / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "academico_db"

    # Opcional a nivel de clase para que importar este módulo nunca falle: el
    # error se da, con un mensaje claro, al pedir la URL de conexión.
    dashboard_db_user: str = "rol_dashboard"
    dashboard_db_password: str | None = None

    @property
    def database_url(self) -> str:
        if not self.dashboard_db_password:
            raise ErrorConfiguracion(
                "Falta DASHBOARD_DB_PASSWORD en el .env (ver .env.example). Es la "
                "contraseña de rol_dashboard, el rol de solo lectura del Data Warehouse."
            )
        return (
            f"postgresql+psycopg2://{self.dashboard_db_user}:{self.dashboard_db_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = SettingsDashboard()
