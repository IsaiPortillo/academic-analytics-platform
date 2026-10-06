"""Configuración del pipeline ETL — SCRUM-33.

Mismo patrón que backend/app/config.py: las credenciales salen del .env de la
raíz, nunca del código. La diferencia es el rol de PostgreSQL que se usa —
aquí rol_etl, que solo tiene SELECT — porque el ETL jamás debe escribir en el
esquema operacional.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ_PROYECTO = Path(__file__).resolve().parents[1]


class ErrorConfiguracion(Exception):
    """Falta una credencial que la operación pedida necesita."""


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

    # Rol de ESCRITURA del Data Warehouse (SCRUM-35). Es otro rol, a propósito:
    # rol_etl lee el OLTP y no puede escribir el DW; rol_dw_carga escribe el DW
    # y no puede leer el OLTP. Opcional aquí para que los comandos que solo leen
    # (pipeline, verificaciones) no exijan una credencial que no usan; la carga
    # sí la exige y falla con un mensaje claro si falta.
    dw_carga_db_user: str = "rol_dw_carga"
    dw_carga_db_password: str | None = None

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.etl_db_user}:{self.etl_db_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_carga(self) -> str:
        if not self.dw_carga_db_password:
            raise ErrorConfiguracion(
                "Falta DW_CARGA_DB_PASSWORD en el .env: la carga del DW escribe con "
                "rol_dw_carga, no con rol_etl (que es de solo lectura). Ver "
                "database/oltp/14_bootstrap_rol_dw_carga.sh."
            )
        return (
            f"postgresql+psycopg2://{self.dw_carga_db_user}:{self.dw_carga_db_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = SettingsETL()
