from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str

    TELEGRAM_BOT_TOKEN: str
    TEACHER_REGISTRATION_CODE: str

    class Config:
        env_file = ".env"


settings = Settings()