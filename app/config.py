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

    # =========================================================
    # SOCIAL HUB
    # =========================================================
    social_enabled: bool = True

    # Una piattaforma e' realmente pronta soltanto quando il flag e' true
    # E le relative credenziali sono presenti.
    social_facebook_enabled: bool = False
    social_instagram_enabled: bool = False
    social_pinterest_enabled: bool = False
    social_telegram_enabled: bool = False
    social_whatsapp_enabled: bool = False

    # Versione API Meta usata dai client Social Hub.
    meta_graph_api_version: str = "v23.0"
    social_http_timeout_seconds: float = 30.0

    # Meta / Facebook
    meta_system_user_access_token: SecretStr | None = None
    facebook_page_id: str | None = None
    # Opzionale: se presente viene usato direttamente. Se vuoto, il bot prova
    # a ricavarlo automaticamente dal System User token.
    facebook_page_access_token: SecretStr | None = None

    # Instagram API with Instagram Login
    instagram_access_token: SecretStr | None = None
    instagram_app_id: str | None = None
    instagram_app_secret: SecretStr | None = None
    instagram_account_id: str | None = None

    # Pinterest - predisposto, ma Phase 1 resta bloccata finche' non c'e' API
    pinterest_app_id: str | None = None
    pinterest_app_secret: SecretStr | None = None
    pinterest_access_token: SecretStr | None = None
    pinterest_board_id: str | None = None

    # Telegram Social - predisposto per il prossimo sblocco
    social_telegram_channel_id: str | None = None

    # WhatsApp - solo placeholder finche' non definiamo un metodo ufficiale
    social_whatsapp_channel_id: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
