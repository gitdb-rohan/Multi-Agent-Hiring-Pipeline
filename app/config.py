from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Branding (white-label)
    APP_NAME: str = "HireFlow"
    APP_TAGLINE: str = "AI-Powered Hiring Pipeline"

    # LLM provider-agnostic config
    LLM_PROVIDER: str = "openai"
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    # Infra
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/hiring"
    REDIS_URL: str = "redis://localhost:6379/0"
    CHROMA_PERSIST_DIR: str = "./data/chroma"

    # Security
    JWT_SECRET_KEY: str = Field(default_factory=lambda: __import__('secrets').token_urlsafe(32))
    JWT_ALGORITHM: str = "HS256"
    FRONTEND_URL: str = "http://localhost:3000"

    # Candidate ingestion
    RESUME_WATCH_DIR: str = "./data/resumes"
    RESUME_PROCESSED_DIR: str = "./data/resumes/processed"

    # Rate limiting
    EMAIL_SEND_RATE_PER_MINUTE: int = 10

    # Eval thresholds
    EVAL_MIN_CONFIDENCE: float = 0.75

    # Observability
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
