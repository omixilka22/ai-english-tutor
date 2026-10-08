from pydantic_settings import BaseSettings
from pydantic import SecretStr


class Settings(BaseSettings):
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str

    TELEGRAM_BOT_TOKEN: str
    TEACHER_REGISTRATION_CODE: str

    RECALL_API_KEY: SecretStr | None = None
    RECALL_BASE_URL: str = "https://eu-central-1.recall.ai"
    RECALL_WEBHOOK_SECRET: SecretStr | None = None
    RECALL_WEBHOOK_READY: bool = False

    GEMINI_API_KEY: SecretStr | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_FALLBACK_MODEL: str = "gemini-2.5-flash-lite"

    class Config:
        env_file = ".env"
        extra = "ignore"
        hide_input_in_errors = True


settings = Settings()