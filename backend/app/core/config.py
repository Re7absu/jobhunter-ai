from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    APP_ENV: str = "development"
    DATABASE_URL: str = f"sqlite:///{(BACKEND_DIR / 'jobhunter.db').as_posix()}"
    SECRET_KEY: str = "dev-insecure-secret-change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    ENCRYPTION_KEY: str = ""
    ALLOW_REGISTRATION: bool = False

    CORS_ORIGINS: str = "http://localhost:3000"
    FRONTEND_URL: str = "http://localhost:3000"
    STORAGE_DIR: str = str(BACKEND_DIR / "storage")
    MAX_CV_MB: int = 10
    SCHEDULER_ENABLED: bool = True
    LOG_LEVEL: str = "INFO"

    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4.1-mini"
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"

    RAPIDAPI_KEY: str = ""
    JSEARCH_HOST: str = "jsearch.p.rapidapi.com"
    JSEARCH_PATH: str = "/search-v2"  # JSearch retired the old "/search" endpoint
    SERPAPI_KEY: str = ""
    HTTP_USER_AGENT: str = "JobHunterAI/1.0 (personal job-search assistant)"
    # Minimum seconds between requests to the same host (robots.txt Crawl-delay wins if larger)
    CRAWL_MIN_DELAY_SECONDS: float = 1.0

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/gmail/callback"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def storage_path(self) -> Path:
        p = Path(self.STORAGE_DIR)
        if not p.is_absolute():
            p = BACKEND_DIR / p
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def gmail_configured(self) -> bool:
        return bool(self.GOOGLE_CLIENT_ID and self.GOOGLE_CLIENT_SECRET)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
