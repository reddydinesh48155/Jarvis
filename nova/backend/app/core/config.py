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

    # Tool & MCP Settings (Part 5)
    allowed_tools_dir: str = "storage"
    reports_dir: str = "storage/reports"
    tool_default_timeout_seconds: float = 10.0

    # Enterprise RAG settings (Part 6). 768 matches Ollama's nomic-embed-text.
    rag_embedding_provider: str = "ollama"
    rag_embedding_model: str = "nomic-embed-text"
    rag_embedding_dimension: int = Field(default=768, ge=16, le=4096)
    rag_embedding_timeout_seconds: float = Field(default=30.0, ge=1.0, le=300.0)
    rag_chunk_size: int = Field(default=900, ge=200, le=4000)
    rag_chunk_overlap: int = Field(default=120, ge=0, le=1000)
    rag_max_file_size_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    rag_min_relevance: float = Field(default=0.20, ge=0.0, le=1.0)
    rag_candidate_limit: int = Field(default=200, ge=10, le=2000)

    # Memory System (Part 7)
    memory_fact_detection_enabled: bool = True
    memory_max_long_term_per_user: int = Field(default=500, ge=10, le=5000)
    memory_relevance_threshold: float = Field(default=0.30, ge=0.0, le=1.0)

    # Security & Hardening (Part 8)
    rate_limit_auth_per_minute: int = Field(default=10, ge=1, le=100)
    rate_limit_api_per_minute: int = Field(default=60, ge=1, le=600)
    tool_confirmation_timeout_seconds: int = Field(default=30, ge=5, le=120)
    admin_emails: str = ""  # comma-separated list of emails auto-promoted to admin

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origin.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
