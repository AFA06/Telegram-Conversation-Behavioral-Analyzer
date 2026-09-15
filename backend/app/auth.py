"""Tenant identity for the multi-user (cloud) deployment.

Two modes, controlled by ``settings.multi_tenant``:

- Single-tenant / local-first (default, unchanged from the original
  self-hosted product): every request resolves to the fixed tenant id
  ``"local"``, which maps onto the original single global database. This
  is exactly the original behavior — nothing changes for anyone running
  this repo locally on their own machine.
- Multi-tenant (cloud): the caller must present a valid Telegram Mini App
  ``initData`` payload (sent as the ``X-Telegram-Init-Data`` header),
  which is cryptographically verified against the bot token per Telegram's
  documented algorithm. The verified Telegram user id becomes the tenant
  id. There is no other way to authenticate — nobody can see or analyze
  anyone else's imported conversation.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException

from app.config import settings

LOCAL_TENANT_ID = "local"
MAX_INIT_DATA_AGE_SECONDS = 24 * 3600


def validate_telegram_init_data(init_data: str, bot_token: str) -> dict:
    """Verifies a Telegram WebApp ``initData`` string and returns the
    parsed fields (including the ``user`` dict) on success.

    Raises ValueError with a human-readable reason on failure. Algorithm:
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-web-app
    """
    pairs = dict(parse_qsl(init_data, strict_parsing=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise ValueError("missing hash")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise ValueError("hash mismatch (forged or corrupted initData)")

    auth_date = int(pairs.get("auth_date", "0"))
    if time.time() - auth_date > MAX_INIT_DATA_AGE_SECONDS:
        raise ValueError("initData has expired")

    result = dict(pairs)
    if "user" in result:
        result["user"] = json.loads(result["user"])
    return result


def get_current_tenant_id(x_telegram_init_data: str | None = Header(default=None)) -> str:
    """FastAPI dependency: resolves the caller's tenant id."""
    if not settings.multi_tenant:
        return LOCAL_TENANT_ID

    if not settings.telegram_bot_token:
        raise HTTPException(status_code=500, detail="Server is not configured with a bot token.")
    if not x_telegram_init_data:
        raise HTTPException(status_code=401, detail="Missing X-Telegram-Init-Data header.")

    try:
        parsed = validate_telegram_init_data(x_telegram_init_data, settings.telegram_bot_token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid Telegram authentication: {exc}") from exc

    user = parsed.get("user")
    if not user or "id" not in user:
        raise HTTPException(status_code=401, detail="initData did not include a user id.")

    return str(user["id"])
