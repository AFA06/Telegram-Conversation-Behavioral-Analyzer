"""Application settings.

Everything here is local-first: the SQLite database lives under ``data/``
(gitignored) and no network calls are made to external AI services.
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = f"sqlite:///{DATA_DIR / 'analyzer.db'}"
    default_timezone: str = "Asia/Tashkent"

    # Conversation-analysis defaults (all overridable via the /settings API)
    default_grouping_window_minutes: int = 5
    default_session_gap_hours: int = 6
    default_min_sample_size: int = 10

    # Optional Telegram bot (Phase 7) — token must never be committed.
    telegram_bot_token: str | None = None
    bot_backend_url: str = "http://127.0.0.1:8000"

    # CORS for the local dashboard
    dashboard_origin: str = "http://localhost:5173"


settings = Settings()
DATA_DIR.mkdir(parents=True, exist_ok=True)
