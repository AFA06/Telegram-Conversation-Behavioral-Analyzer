import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

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
        # Runs the bot inside this same process/event loop so it shares the
        # same filesystem/DB connections as the API — the simplest setup
        # for a single-service deployment. Disabled by default so the
        # documented local flow (running `python -m analyzer server` and
        # `python -m bot.main` as two separate processes) keeps working
        # without a double-polling conflict on the same bot token.
        from bot.main import build_application

        telegram_bot_app = build_application()
        await telegram_bot_app.initialize()
        await telegram_bot_app.start()

        if settings.telegram_webhook_url:
            # Webhook mode: Telegram pushes updates to us via HTTP POST
            # (see the /telegram/webhook route below) instead of us
            # continuously polling. This is what makes the bot work on a
            # host that sleeps the process when idle (e.g. Render's free
            # tier) — polling can't survive that (the process isn't
            # running to poll), but an incoming webhook request wakes it.
            await telegram_bot_app.bot.set_webhook(
                url=settings.telegram_webhook_url,
                secret_token=settings.telegram_webhook_secret or None,
            )
            logger.info("Telegram bot started in-process (webhook: %s)", settings.telegram_webhook_url)
        else:
            await telegram_bot_app.updater.start_polling()
            logger.info("Telegram bot started in-process (polling)")

        app.state.telegram_bot_app = telegram_bot_app

    yield

    if telegram_bot_app is not None:
        if telegram_bot_app.updater and telegram_bot_app.updater.running:
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


# asyncio only holds a *weak* reference to a task's future — without
# something else keeping a strong reference, a background task can be
# garbage-collected mid-execution (a documented asyncio gotcha). This set
# is that strong reference; each task removes itself once done.
_background_tasks: set[asyncio.Task] = set()


def _log_background_task_failure(task: asyncio.Task) -> None:
    _background_tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("Background update processing failed", exc_info=exc)


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request) -> dict:
    """Receives pushed updates from Telegram when TELEGRAM_WEBHOOK_URL is
    set (see the lifespan above). The secret_token header is set by
    Telegram itself on every genuine webhook call — verifying it stops
    randoms from POSTing forged updates to this endpoint.

    Acknowledges immediately and processes the update as a background task
    rather than awaiting it: a real import (thousands of messages, over a
    real network DB) can take well past Telegram's own webhook response
    timeout (~60s). Awaiting it here meant Telegram gave up waiting,
    retried by resending the *same* update, and we'd end up processing the
    same file twice concurrently — which is exactly what caused duplicate-
    key crashes and repeated bot replies in production. Acking fast makes
    Telegram stop retrying, so each update is (normally) only processed once.
    """
    telegram_bot_app = getattr(request.app.state, "telegram_bot_app", None)
    if telegram_bot_app is None:
        raise HTTPException(status_code=404, detail="Bot is not running in webhook mode on this server.")

    if settings.telegram_webhook_secret:
        received = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if received != settings.telegram_webhook_secret:
            raise HTTPException(status_code=403, detail="Invalid webhook secret token.")

    from telegram import Update

    data = await request.json()
    update = Update.de_json(data, telegram_bot_app.bot)
    task = asyncio.create_task(telegram_bot_app.process_update(update))
    _background_tasks.add(task)
    task.add_done_callback(_log_background_task_failure)
    return {"ok": True}


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
# frontend/dist doesn't exist yet — Vite's own dev server handles the
# frontend instead, proxying /api to this backend (see vite.config.js) —
# these routes just 404 in that case (checked per-request, not at import
# time, so the app doesn't need a build present just to start or be tested).
_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
_INDEX_HTML = _FRONTEND_DIST / "index.html"


@app.api_route("/{full_path:path}", methods=["GET", "HEAD"])
async def spa(full_path: str) -> FileResponse:
    """Serves the SPA shell for any path that isn't an API route or a real
    built file — React Router handles the actual routing client-side from
    there.

    Without this, only "/" ever worked: a plain StaticFiles(html=True)
    mount has no concept of client-side routes, so a direct request for
    e.g. "/activity" 404s. That 404 is exactly what a user sees as "this
    section doesn't work" — Telegram's Mini App WebView reloads at
    whatever path is currently open (not always "/") when the app is
    backgrounded and reopened, which is a routine, frequent event, not an
    edge case.

    index.html is explicitly never cached: it's what points the
    browser/WebView at the current hashed JS bundle. A stale cached copy
    pointing at an old bundle is exactly what makes a real, live fix look
    like "it's still showing the old version" after a deploy.
    """
    if full_path.startswith("api/") or full_path.startswith("telegram/"):
        raise HTTPException(status_code=404)
    candidate = _FRONTEND_DIST / full_path
    if full_path and candidate.is_file():
        return FileResponse(candidate)
    if _INDEX_HTML.is_file():
        return FileResponse(_INDEX_HTML, headers={"Cache-Control": "no-store"})
    raise HTTPException(status_code=404)
