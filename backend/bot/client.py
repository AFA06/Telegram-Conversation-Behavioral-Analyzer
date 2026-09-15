"""Thin async HTTP client for talking to the local analysis backend.

The bot never touches the Telegram export or the database directly — it
only reads already-computed statistics from the FastAPI backend, which
must be running (``python -m analyzer server``).
"""
from __future__ import annotations

import httpx

from app.config import settings


class BackendClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.bot_backend_url).rstrip("/")

    async def get(self, path: str, params: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{self.base_url}/api{path}", params=params)
            resp.raise_for_status()
            return resp.json()

    async def post(self, path: str, json: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{self.base_url}/api{path}", json=json or {})
            resp.raise_for_status()
            return resp.json()


backend = BackendClient()
