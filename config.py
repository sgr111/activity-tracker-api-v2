from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Auth ──────────────────────────────────────────
    SECRET_KEY:                   str            # required — no fallback, on purpose
    ALGORITHM:                    str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES:  int = 30

    # ── Gemini ────────────────────────────────────────
    GEMINI_API_KEY:                str

    # ── Database (used by both database.py and database_async.py) ──
    #DATABASE_URL:str = "postgresql://postgres:password@localhost:5432/activity_tracker"
    DATABASE_URL:                  str    
    # required — no fallback, on purpose (same reasoning as SECRET_KEY/GEMINI_API_KEY)

settings = Settings()
