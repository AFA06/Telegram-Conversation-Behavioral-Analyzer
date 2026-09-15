from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routes import activity, bot, config as config_route, data_explorer, export, imports, overview, responses, sessions, trends


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


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
app.include_router(bot.router, prefix="/api/bot", tags=["bot"])
