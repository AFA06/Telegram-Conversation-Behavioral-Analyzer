"""Request-scoped dependencies shared by the API routes.

``get_current_db`` is what routes should depend on (instead of the old
``database.get_db`` directly) — in single-tenant/local mode it behaves
identically to ``get_db`` (same global database), and in multi-tenant/cloud
mode it resolves and opens the caller's own isolated tenant database.
"""
from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends
from sqlalchemy.orm import Session

from app.auth import get_current_tenant_id
from app.database import get_session_for_tenant


def get_current_db(tenant_id: str = Depends(get_current_tenant_id)) -> Generator[Session, None, None]:
    db = get_session_for_tenant(tenant_id)
    try:
        yield db
    finally:
        db.close()
