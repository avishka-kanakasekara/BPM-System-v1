from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables / `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # Supabase. Empty strings become None so JWT/JWKS paths can fail closed.
    SUPABASE_URL: Optional[str] = None
    SUPABASE_ANON_KEY: Optional[str] = None
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None
    # Optional legacy HS256 JWT secret (Dashboard → Project Settings → API → JWT Secret).
    # Prefer JWKS verification via SUPABASE_URL when the project uses asymmetric signing keys.
    SUPABASE_JWT_SECRET: Optional[str] = None

    # Sync SQLAlchemy (Agent 1) uses postgresql://. Async callers should use async_database_url.
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/bpmflow"

    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    DEBUG: bool = True

    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"
    MOCK_LLM: bool = False
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL_FLASH: str = "gemini-3.6-flash"
    GEMINI_MODEL_PRO: str = "gemini-3.6-flash"
    GEMINI_OFFLINE: bool = False
    EMAIL_DRY_RUN: bool = True

    MAX_UPLOAD_MB: int = 20
    ALLOWED_FILE_TYPES: str = "pdf,docx,csv"
    ENV: str = "development"

    CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://localhost:5174",
        ]
    )

    @field_validator(
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_JWT_SECRET",
        mode="before",
    )
    @classmethod
    def _empty_supabase_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @property
    def allowed_file_types_list(self) -> List[str]:
        return [item.strip().lower() for item in self.ALLOWED_FILE_TYPES.split(",") if item.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_MB * 1024 * 1024

    @property
    def is_development(self) -> bool:
        return self.ENV.lower() in {"development", "dev", "local"}

    @property
    def async_database_url(self) -> str:
        """postgresql+asyncpg:// form for Agent 3 / async SQLAlchemy. Leaves sqlite unchanged."""
        url = self.DATABASE_URL
        if url.startswith("postgresql+asyncpg://"):
            return url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
