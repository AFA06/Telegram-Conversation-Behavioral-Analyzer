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

    # CORS for the local dashboard / Mini App origin
    dashboard_origin: str = "http://localhost:5173"

    # --- Cloud / multi-tenant mode (Phase 9) ---
    # False (default): original single-user local-first behavior, unchanged.
    # True: each Telegram user gets an isolated database, and every API
    # request must carry a verified Telegram Mini App initData header.
    multi_tenant: bool = False
    tenant_db_dir: str = str(DATA_DIR / "tenants")
    # Public base URL the bot uses to build the Mini App button link.
    public_web_app_url: str | None = None
    # Runs the bot's polling loop inside the API process (see app/main.py's
    # lifespan). Off by default so the local two-process flow (`analyzer
    # server` + `python -m bot.main`) doesn't double-poll the same bot
    # token; turn this on for a single-service production deployment.
    run_bot_in_process: bool = False

    # How tenant isolation is implemented:
    # "sqlite_file" (default): one SQLite file per tenant on local disk —
    #   simple, zero extra infra, but requires a host with a persistent
    #   volume (fine for a self-managed VPS; NOT fine for Render's free
    #   tier, which has no persistent disk).
    # "postgres_schema": one Postgres SCHEMA per tenant on a single shared
    #   database (e.g. a free Neon/Supabase project) — works on hosts with
    #   no persistent disk at all, since the data lives in the external DB.
    tenant_backend: str = "sqlite_file"
    # Connection string for the shared Postgres server, only used when
    # tenant_backend="postgres_schema". Never commit a real one.
    postgres_url: str | None = None
    # Optional webhook mode for the bot (needed on hosts that sleep the
    # process when idle, e.g. Render's free tier — polling can't survive
    # that, but an incoming webhook request wakes the process). Leave unset
    # to use polling (the default, and the only mode for local dev).
    telegram_webhook_url: str | None = None
    telegram_webhook_secret: str | None = None


settings = Settings()
DATA_DIR.mkdir(parents=True, exist_ok=True)
if settings.multi_tenant:
    Path(settings.tenant_db_dir).mkdir(parents=True, exist_ok=True)
