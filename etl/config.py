"""Configuración del pipeline ETL — SCRUM-33.

Mismo patrón que backend/app/config.py: las credenciales salen del .env de la
raíz, nunca del código. La diferencia es el rol de PostgreSQL que se usa —
aquí rol_etl, que solo tiene SELECT — porque el ETL jamás debe escribir en el
esquema operacional.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ_PROYECTO = Path(__file__).resolve().parents[1]


class SettingsETL(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=RAIZ_PROYECTO / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "academico_db"

    # Rol de solo lectura. Que el ETL no pueda escribir no depende de que este
    # código se porte bien, sino de los GRANT del motor.
    etl_db_user: str = "rol_etl"
    etl_db_password: str

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.etl_db_user}:{self.etl_db_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = SettingsETL()
