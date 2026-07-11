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

    # Rate limiting
    EMAIL_SEND_RATE_PER_MINUTE: int = 10

    # Eval thresholds
    EVAL_MIN_CONFIDENCE: float = 0.75

    # Observability
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
