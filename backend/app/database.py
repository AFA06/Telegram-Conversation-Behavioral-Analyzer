import re
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from app import models  # noqa: F401  (register models on Base.metadata)

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Multi-tenant (cloud) support ---
# Each tenant (a verified Telegram user id) gets its own SQLite file, so the
# entire existing single-tenant service layer works completely unchanged —
# it just gets handed a Session bound to that tenant's own database.

_TENANT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_tenant_engines: dict[str, Engine] = {}
_tenant_sessionmakers: dict[str, sessionmaker] = {}


def get_engine_for_tenant(tenant_id: str) -> Engine:
    from app.auth import LOCAL_TENANT_ID

    if tenant_id == LOCAL_TENANT_ID:
        return engine

    if not _TENANT_ID_RE.match(tenant_id):
        raise ValueError(f"Invalid tenant id: {tenant_id!r}")

    if tenant_id not in _tenant_engines:
        from app import models  # noqa: F401  (register models on Base.metadata)

        db_path = Path(settings.tenant_db_dir) / f"{tenant_id}.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        tenant_engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=tenant_engine)
        _tenant_engines[tenant_id] = tenant_engine
        _tenant_sessionmakers[tenant_id] = sessionmaker(bind=tenant_engine, autoflush=False, autocommit=False)

    return _tenant_engines[tenant_id]


def get_session_for_tenant(tenant_id: str) -> Session:
    from app.auth import LOCAL_TENANT_ID

    if tenant_id == LOCAL_TENANT_ID:
        return SessionLocal()

    get_engine_for_tenant(tenant_id)  # ensures it's created + registered
    return _tenant_sessionmakers[tenant_id]()
