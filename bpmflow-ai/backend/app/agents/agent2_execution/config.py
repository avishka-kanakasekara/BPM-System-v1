"""
Agent 2 — Application Configuration

Loads all settings from a .env file via pydantic-settings.
"""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Shared backend .env (bpmflow-ai/backend/.env) — one env file for all agents.
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """Agent 2 configuration — all values read from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── Database ────────────────────────────────────────────────────────────
    DATABASE_URL: str = ""

    # ── Google Gemini LLM ───────────────────────────────────────────────────
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL_FLASH: str = "gemini-3.6-flash"
    GEMINI_MODEL_PRO: str = "gemini-3.6-flash"
    GEMINI_OFFLINE: bool = False

    # ── SMTP — email sending ────────────────────────────────────────────────
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""

    # ── Agent 4 (orchestrator) integration ──────────────────────────────────
    AGENT4_BASE_URL: str = ""
    AGENT4_API_KEY: str = ""

    # ── Redis ───────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6380/0"

    # ── Feature flags ───────────────────────────────────────────────────────
    EMAIL_DRY_RUN: bool = True
    ENVIRONMENT: str = "development"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if not isinstance(value, str) or not value:
            return value
        if value.startswith("postgresql://"):
            value = value.replace("postgresql://", "postgresql+asyncpg://", 1)
        if "?" in value:
            base, query = value.split("?", 1)
            kept = [part for part in query.split("&") if not part.lower().startswith("ssl")]
            value = base if not kept else f"{base}?{'&'.join(kept)}"
        return value


settings = Settings()
