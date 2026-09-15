import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routes import activity, config as config_route, data_explorer, export, imports, overview, responses, sessions, trends
from app.routes import bot as bot_routes

logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    telegram_bot_app = None
    if settings.telegram_bot_token and settings.run_bot_in_process:
        # Runs the bot's polling loop inside this same process/event loop
        # so it shares the same filesystem (and therefore the same
        # per-tenant SQLite files) as the API — the simplest setup for a
        # single-service deployment (e.g. one Railway service). Disabled
        # by default so the documented local flow (running
        # `python -m analyzer server` and `python -m bot.main` as two
        # separate processes) keeps working without a double-polling
        # conflict on the same bot token.
        from bot.main import build_application

        telegram_bot_app = build_application()
        await telegram_bot_app.initialize()
        await telegram_bot_app.start()
        await telegram_bot_app.updater.start_polling()
        logger.info("Telegram bot started in-process (polling)")

    yield

    if telegram_bot_app is not None:
        await telegram_bot_app.updater.stop()
        await telegram_bot_app.stop()
        await telegram_bot_app.shutdown()


app = FastAPI(
    title="Telegram Conversation Behavioral Analyzer",
    description=(
        "Local-first analysis of a two-person Telegram conversation export. "
        "Everything runs on your machine; no message content is sent anywhere."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.dashboard_origin, "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


app.include_router(imports.router, prefix="/api/import", tags=["import"])
app.include_router(config_route.router, prefix="/api/config", tags=["config"])
app.include_router(overview.router, prefix="/api/overview", tags=["overview"])
app.include_router(activity.router, prefix="/api/activity", tags=["activity"])
app.include_router(responses.router, prefix="/api/responses", tags=["responses"])
app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(trends.router, prefix="/api/trends", tags=["trends"])
app.include_router(data_explorer.router, prefix="/api/messages", tags=["data-explorer"])
app.include_router(export.router, prefix="/api/export", tags=["export"])
app.include_router(bot_routes.router, prefix="/api/bot", tags=["bot"])

# Serves the built frontend (frontend/dist) as static files when present,
# so a single deployed service can host both the API and the Mini App /
# dashboard on one origin (no CORS needed in production). In local dev,
# frontend/dist doesn't exist — Vite's own dev server handles the frontend
# instead, proxying /api to this backend (see frontend/vite.config.js) —
# so this mount is a pure no-op locally.
_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _FRONTEND_DIST.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
