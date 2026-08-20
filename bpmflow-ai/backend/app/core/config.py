from pydantic_settings import BaseSettings
from dotenv import load_dotenv
import os

load_dotenv()


class Settings(BaseSettings):
    # Supabase Configuration
    SUPABASE_URL: str = os.getenv("SUPABASE_URL") or ""
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY") or ""
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
    # Optional legacy HS256 JWT secret (Dashboard → Project Settings → API → JWT Secret).
    # Prefer JWKS verification via SUPABASE_URL when the project uses asymmetric signing keys.
    SUPABASE_JWT_SECRET: str = os.getenv("SUPABASE_JWT_SECRET") or ""
    
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
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
