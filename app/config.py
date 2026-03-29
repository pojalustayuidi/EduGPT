from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    GEMINI_API_URL: str
    GEMINI_API_KEY: str

    DATABASE_URL: str = "sqlite:///./data/methodics.db"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# GEMINI_API_URL=https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent
# GEMINI_API_KEY=AIzaSyD8Q8sZLn89PZPers0a9B_Swfpoef72W20
settings = Settings(
)