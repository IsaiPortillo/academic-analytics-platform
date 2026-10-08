from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ_PROYECTO = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=RAIZ_PROYECTO / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "academico_db"

    # La aplicación se conecta con el rol de servicio, nunca con el superusuario.
    app_db_user: str = "rol_app"
    app_db_password: str

    app_secret_key: str

    # Vista ejecutiva (Fase 4.1): lee el Data Warehouse con un rol aparte, de
    # solo lectura y SIN acceso a academico_oltp (database/oltp/10 y 11). Es
    # opcional para que la app arranque aunque el DW aún no esté configurado;
    # en ese caso la vista ejecutiva lo indica en pantalla.
    dashboard_db_user: str = "rol_dashboard"
    dashboard_db_password: Optional[str] = None

    # Apagado por defecto a propósito: los botones de "acceso rápido" del login
    # exponen credenciales reales de un clic. Nunca debe quedar en true en un
    # despliegue alcanzable desde internet — solo se activa a mano, en un
    # entorno controlado, para una demostración puntual (ej. defensa de tesis).
    modo_demo: bool = False

    # Marca `Secure` de la cookie de sesión: el navegador solo la envía por HTTPS.
    # Actívala (COOKIE_SECURE=true) cuando el sitio se sirva por HTTPS, aunque el
    # TLS termine en un proxy (nginx, Cloudflare): la bandera la interpreta el
    # navegador, no el servidor. Apagada por defecto porque en http://localhost
    # el navegador descartaría la cookie y nadie podría iniciar sesión.
    cookie_secure: bool = False

    @property
    def dw_url(self) -> Optional[str]:
        if not self.dashboard_db_password:
            return None
        return (
            f"postgresql+psycopg2://{self.dashboard_db_user}:{self.dashboard_db_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.app_db_user}:{self.app_db_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
