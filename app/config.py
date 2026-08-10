from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)


class Settings(BaseSettings):
    """
    Configurazione principale
    dell'applicazione.
    """

    bot_token: SecretStr

    admin_user_id: int

    app_env: Literal[
        "development",
        "production",
    ] = "development"

    database_url: str = (
        "sqlite+aiosqlite:///"
        "./amazondealsbot.db"
    )

    amazon_partner_tag: str = (
        "example-21"
    )

    # Fuso orario utilizzato
    # per inserire gli orari
    # dei post programmati.
    app_timezone: str = (
        "Europe/Rome"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
