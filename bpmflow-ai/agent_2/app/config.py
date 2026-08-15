"""
Agent 2 — Application Configuration

Loads all settings from a .env file via pydantic-settings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Agent 2 configuration — all values read from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # ── Database ────────────────────────────────────────────────────────────
    DATABASE_URL: str = ""

    # ── Google Gemini LLM ───────────────────────────────────────────────────
    GEMINI_API_KEY: str = ""

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


settings = Settings()
