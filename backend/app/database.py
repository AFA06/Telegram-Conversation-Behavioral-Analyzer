import re
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def _apply_additive_migrations(target_engine: Engine) -> None:
    """Adds columns that exist in the ORM models but not yet in an
    already-created database (e.g. an existing tenant's file from before a
    column like AppConfig.language was added). ``create_all`` only creates
    missing *tables*, never missing columns on existing ones — there's no
    real migration tool (Alembic) at this project stage, so this covers
    the common additive case safely and idempotently.
    """
    inspector = inspect(target_engine)
    existing_tables = set(inspector.get_table_names())
    with target_engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # brand new table — create_all already made it in full
            existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_columns:
                    continue
                col_type = column.type.compile(target_engine.dialect)
                default_sql = ""
                if column.default is not None and getattr(column.default, "is_scalar", False):
                    value = column.default.arg
                    if isinstance(value, str):
                        default_sql = f" DEFAULT '{value.replace(chr(39), chr(39) * 2)}'"
                    elif isinstance(value, bool):
                        default_sql = f" DEFAULT {int(value)}"
                    elif isinstance(value, (int, float)):
                        default_sql = f" DEFAULT {value}"
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}{default_sql}'))


def init_db() -> None:
    from app import models  # noqa: F401  (register models on Base.metadata)

    Base.metadata.create_all(bind=engine)
    _apply_additive_migrations(engine)


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
        _apply_additive_migrations(tenant_engine)
        _tenant_engines[tenant_id] = tenant_engine
        _tenant_sessionmakers[tenant_id] = sessionmaker(bind=tenant_engine, autoflush=False, autocommit=False)

    return _tenant_engines[tenant_id]


def get_session_for_tenant(tenant_id: str) -> Session:
    from app.auth import LOCAL_TENANT_ID

    if tenant_id == LOCAL_TENANT_ID:
        return SessionLocal()

    get_engine_for_tenant(tenant_id)  # ensures it's created + registered
    return _tenant_sessionmakers[tenant_id]()
