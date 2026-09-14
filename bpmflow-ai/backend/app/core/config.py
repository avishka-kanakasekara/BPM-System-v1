from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PersistenceModeSetting = Literal["auto", "postgres", "rest"]


class Settings(BaseSettings):
    """Application settings — the only source of runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # --- Supabase / auth -------------------------------------------------------
    SUPABASE_URL: str | None = None
    SUPABASE_ANON_KEY: str | None = None
    SUPABASE_SERVICE_ROLE_KEY: str | None = None
    SUPABASE_JWT_SECRET: str | None = None

    # --- Database / persistence ------------------------------------------------
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/bpmflow"
    PERSISTENCE_MODE: PersistenceModeSetting = "auto"

    # --- API runtime -----------------------------------------------------------
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    DEBUG: bool = True
    ENV: str = "development"
    DEMO_TENANT_ID: str = "00000000-0000-0000-0000-000000000001"

    # --- LLM -------------------------------------------------------------------
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-20250514"
    MOCK_LLM: bool = False
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL_FLASH: str = "gemini-3.6-flash"
    GEMINI_MODEL_PRO: str = "gemini-3.6-flash"
    GEMINI_OFFLINE: bool = False

    # --- Email (Agent 2) -------------------------------------------------------
    EMAIL_DRY_RUN: bool = True
    EMAIL_PROVIDER: str = "smtp"
    EMAIL_API_KEY: str = ""
    EMAIL_FROM: str = ""
    EMAIL_REPLY_TO: str = ""
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""

    # --- Uploads ---------------------------------------------------------------
    MAX_UPLOAD_MB: int = 20
    MAX_REQUEST_MB: int = 25
    ALLOWED_FILE_TYPES: str = "pdf,docx,csv,txt"

    # --- Rate limiting ---------------------------------------------------------
    RATE_LIMIT_AUTH_PER_MINUTE: int = 20
    RATE_LIMIT_UPLOAD_PER_MINUTE: int = 10

    # --- External calls --------------------------------------------------------
    EXTERNAL_HTTP_TIMEOUT_SECONDS: float = 30.0
    LLM_REQUEST_TIMEOUT_SECONDS: float = 60.0
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5
    CIRCUIT_BREAKER_RECOVERY_SECONDS: float = 30.0

    # --- Database pool (Postgres direct; NullPool used for Supabase pooler) ----
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT_SECONDS: float = 30.0

    # --- Shutdown --------------------------------------------------------------
    SHUTDOWN_DRAIN_SECONDS: float = 15.0

    # --- Infrastructure --------------------------------------------------------
    REDIS_URL: str | None = None
    JWKS_CACHE_TTL_SECONDS: int = 300
    HEALTH_PROBE_TIMEOUT_SECONDS: float = 3.0

    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5174",
        ]
    )

    @field_validator(
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_JWT_SECRET",
        "REDIS_URL",
        mode="before",
    )
    @classmethod
    def _empty_optional_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @field_validator("PERSISTENCE_MODE", mode="before")
    @classmethod
    def _normalize_persistence_mode(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("EMAIL_PROVIDER", mode="before")
    @classmethod
    def _normalize_email_provider(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @model_validator(mode="after")
    def _validate_combinations(self) -> "Settings":
        if self.PERSISTENCE_MODE not in {"auto", "postgres", "rest"}:
            raise ValueError(
                f"PERSISTENCE_MODE must be auto, postgres, or rest (got {self.PERSISTENCE_MODE!r})"
            )

        if self.EMAIL_PROVIDER not in {"smtp", "resend"}:
            raise ValueError(
                f"EMAIL_PROVIDER must be smtp or resend (got {self.EMAIL_PROVIDER!r})"
            )

        if self.is_production:
            if not self.SUPABASE_URL:
                raise ValueError("SUPABASE_URL is required when ENV=production")
            if self.PERSISTENCE_MODE == "rest" and not self.SUPABASE_SERVICE_ROLE_KEY:
                raise ValueError(
                    "SUPABASE_SERVICE_ROLE_KEY is required when PERSISTENCE_MODE=rest in production"
                )
            if self.PERSISTENCE_MODE == "postgres" and not self.DATABASE_URL:
                raise ValueError("DATABASE_URL is required when PERSISTENCE_MODE=postgres in production")

        if self.PERSISTENCE_MODE == "rest":
            if not self.SUPABASE_URL or not self.SUPABASE_SERVICE_ROLE_KEY:
                raise ValueError(
                    "PERSISTENCE_MODE=rest requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY"
                )

        if self.HEALTH_PROBE_TIMEOUT_SECONDS <= 0:
            raise ValueError("HEALTH_PROBE_TIMEOUT_SECONDS must be positive")

        if self.JWKS_CACHE_TTL_SECONDS <= 0:
            raise ValueError("JWKS_CACHE_TTL_SECONDS must be positive")

        if self.is_production:
            if not self.CORS_ORIGINS:
                raise ValueError("CORS_ORIGINS must list explicit origins in production")
            for origin in self.CORS_ORIGINS:
                if origin.strip() == "*":
                    raise ValueError("CORS_ORIGINS cannot include '*' in production")

        if self.RATE_LIMIT_AUTH_PER_MINUTE <= 0 or self.RATE_LIMIT_UPLOAD_PER_MINUTE <= 0:
            raise ValueError("Rate limit settings must be positive")

        if self.EXTERNAL_HTTP_TIMEOUT_SECONDS <= 0:
            raise ValueError("EXTERNAL_HTTP_TIMEOUT_SECONDS must be positive")

        return self

    @property
    def allowed_file_types_list(self) -> list[str]:
        return [item.strip().lower() for item in self.ALLOWED_FILE_TYPES.split(",") if item.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_MB * 1024 * 1024

    @property
    def max_request_bytes(self) -> int:
        return self.MAX_REQUEST_MB * 1024 * 1024

    @property
    def is_development(self) -> bool:
        return self.ENV.lower() in {"development", "dev", "local"}

    @property
    def is_production(self) -> bool:
        return self.ENV.lower() in {"production", "prod"}

    def assert_production_config(self) -> None:
        """G10: fail fast when production invariants are violated."""
        if not self.is_production:
            return
        self.assert_production_llm_config()

    def assert_production_llm_config(self) -> None:
        if not self.is_production:
            return
        if self.DEBUG:
            raise RuntimeError(
                "DEBUG cannot be enabled when ENV=production."
            )
        if self.MOCK_LLM:
            raise RuntimeError(
                "MOCK_LLM cannot be enabled when ENV=production. "
                "Configure GEMINI_API_KEY for real LLM calls."
            )
        if self.GEMINI_OFFLINE:
            raise RuntimeError(
                "GEMINI_OFFLINE cannot be enabled when ENV=production. "
                "Configure GEMINI_API_KEY for real Agent 2 execution intelligence."
            )
        if not (self.GEMINI_API_KEY or "").strip() or self.GEMINI_API_KEY.startswith("your_"):
            raise RuntimeError(
                "GEMINI_API_KEY is required when ENV=production "
                "(used for Agent 1 discovery and Agent 2 execution)."
            )
        self.assert_production_email_config()

    def assert_production_email_config(self) -> None:
        if not self.is_production:
            return
        if self.EMAIL_DRY_RUN:
            raise RuntimeError(
                "EMAIL_DRY_RUN cannot be enabled when ENV=production. "
                "Configure EMAIL_PROVIDER + credentials for real email delivery, "
                "or set EMAIL_DRY_RUN=false."
            )
        provider = (self.EMAIL_PROVIDER or "smtp").strip().lower()
        email_from = (self.EMAIL_FROM or self.SMTP_FROM_EMAIL or "").strip()
        if provider == "resend":
            api_key = (self.EMAIL_API_KEY or "").strip()
            if not api_key or not email_from:
                raise RuntimeError(
                    "EMAIL_PROVIDER=resend requires EMAIL_API_KEY and EMAIL_FROM when ENV=production."
                )
        elif not (self.SMTP_HOST or "").strip() or not email_from:
            raise RuntimeError(
                "EMAIL_PROVIDER=smtp requires SMTP_HOST and EMAIL_FROM when ENV=production."
            )

    @property
    def async_database_url(self) -> str:
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
