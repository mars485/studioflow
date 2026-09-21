from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "StudioFlow API"
    database_url: str = "postgresql+asyncpg://studioflow:studioflow@db:5432/studioflow"
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 60
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

