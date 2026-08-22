from pydantic import ConfigDict
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
import os
from typing import Optional

load_dotenv()


class Settings(BaseSettings):
    # Supabase Configuration
    # Empty-string defaults allow app import without env; JWT/JWKS paths fail closed when unset.
    SUPABASE_URL: Optional[str] = os.getenv("SUPABASE_URL") or None
    SUPABASE_ANON_KEY: Optional[str] = os.getenv("SUPABASE_ANON_KEY") or None
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or None
    # Optional legacy HS256 JWT secret (Dashboard → Project Settings → API → JWT Secret).
    # Prefer JWKS verification via SUPABASE_URL when the project uses asymmetric signing keys.
    SUPABASE_JWT_SECRET: Optional[str] = os.getenv("SUPABASE_JWT_SECRET") or None

    # Database Configuration
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    if DATABASE_URL and DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

    # API Configuration
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"

    # LLM Configuration
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    model_config = ConfigDict(env_file=".env", case_sensitive=True)


settings = Settings()
