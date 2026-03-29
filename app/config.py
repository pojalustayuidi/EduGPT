from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    GEMINI_API_URL: str
    GEMINI_API_KEY: str

    DATABASE_URL: str = "sqlite:///./data/methodics.db"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings(
)