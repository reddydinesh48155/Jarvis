from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables or .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "NOVA API"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://nova:nova@localhost:5432/nova"
    jwt_secret_key: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=15, ge=1, le=1440)
    refresh_token_expire_days: int = Field(default=7, ge=1, le=365)
    refresh_cookie_name: str = "refresh_token"
    secure_cookies: bool = False
    cookie_samesite: str = "lax"
    frontend_origin: str = "http://localhost:3000"
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    livekit_agent_name: str = "nova-voice"
    livekit_token_ttl_seconds: int = Field(default=3600, ge=60, le=86400)

    # Voice pipeline & agent settings (Part 3 & 4)
    whisper_model_size: str = "base.en"
    whisper_device: str = "cpu"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"
    piper_voice: str = "en_US-lessac-medium"
    piper_binary_path: str = "piper"
    voice_sample_rate: int = 48000

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origin.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
