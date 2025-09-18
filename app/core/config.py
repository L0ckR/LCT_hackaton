from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@db:5432/postgres"
    REDIS_URL: str = "redis://redis:6379/0"
    SECRET_KEY: str = "secret"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    FOUNDATION_API_KEY: str | None = None
    FOUNDATION_API_BASE_URL: str = "https://foundation-models.api.cloud.ru/v1"
    FOUNDATION_CHAT_MODEL: str = "deepseek-ai/DeepSeek-R1-Distill-Llama-70B"
    FOUNDATION_EMBEDDING_MODEL: str = "Qwen/Qwen3-Embedding-0.6B"
    FOUNDATION_EMBEDDING_BATCH_SIZE: int = 16

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
