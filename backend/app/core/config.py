from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    app_name: str = "StudioFlow API"
    database_url: str = "postgresql+asyncpg://studioflow:studioflow@db:5432/studioflow"
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 60
    session_hours: int = Field(default=24, ge=1, le=720)
    session_cookie_secure: bool = False
    allowed_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"]
    dev_auth_enabled: bool = False
    dev_user_id: str = "00000000-0000-0000-0000-000000000001"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

