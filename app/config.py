from pydantic_settings import BaseSettings
from pydantic import SecretStr


class Settings(BaseSettings):
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str

    TELEGRAM_BOT_TOKEN: str
    TEACHER_REGISTRATION_CODE: str

    GEMINI_API_KEY: SecretStr | None = None
    GEMINI_MODEL: str = "gemini-3.8-flash"

    class Config:
        env_file = ".env"
        extra = "ignore"
        hide_input_in_errors = True


settings = Settings()