from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurazione dell'applicazione.

    I segreti restano sempre in .env / variabili d'ambiente.
    """

    bot_token: SecretStr
    admin_user_id: int

    app_env: Literal["development", "production"] = "development"
    database_url: str = "sqlite+aiosqlite:///./amazondealsbot.db"
    app_timezone: str = "Europe/Rome"

    # Amazon / affiliazione
    amazon_partner_tag: str = "example-21"
    amazon_provider: Literal["demo", "creators"] = "demo"
    amazon_marketplace: str = "www.amazon.it"
    amazon_search_keywords: str = "offerta"
    amazon_scan_categories_per_run: int = 4
    amazon_search_item_count: int = 10

    amazon_creators_client_id: SecretStr | None = None
    amazon_creators_client_secret: SecretStr | None = None
    amazon_creators_credential_version: str = "3.2"
    amazon_creators_timeout_seconds: float = 20.0
    amazon_min_request_interval_seconds: float = 1.05

    # Shortlink proprietario opzionale
    shortlink_enabled: bool = False
    shortlink_base_url: str | None = None

    # Web dashboard / health
    web_enabled: bool = False
    web_host: str = "0.0.0.0"
    web_port: int = 8080
    web_admin_token: SecretStr | None = None

    # AI opzionale
    ai_enabled: bool = False
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5"
    ai_timeout_seconds: float = 30.0

    # Notifiche amministratore
    admin_notifications_enabled: bool = True

    # Backup
    backup_dir: str = "./backups"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
