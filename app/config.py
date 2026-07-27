from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str
    farmai_api_key: str
    environment: str = "production"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

@lru_cache
def settings() -> Settings:
    return Settings()
