"""Настройки сервиса приёма."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Настройки подключения и HMAC."""

    postgres_host: str = '127.0.0.1'
    postgres_port: int = 5432
    postgres_db: str
    postgres_user: str
    postgres_password: str

    generic_json_hmac_secret: str
    hmac_tolerance: int = 300

    model_config = SettingsConfigDict(
        env_file=WORKSPACE_ROOT / '.env',
        env_file_encoding='utf-8',
        extra='ignore',
    )


@lru_cache
def get_settings() -> Settings:
    """Кэшированный экземпляр настроек."""
    return Settings()  # type: ignore[call-arg]
