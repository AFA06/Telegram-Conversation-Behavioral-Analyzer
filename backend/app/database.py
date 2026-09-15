import re
import threading
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

    Schema-aware: a Postgres tenant engine carries a ``schema_translate_map``
    execution option (see ``_build_tenant_engine``), but that mapping only
    rewrites SQLAlchemy Core/ORM constructs — NOT raw ``text()`` SQL, and NOT
    ``inspect()`` calls, both of which we use here. So the target schema is
    extracted explicitly and passed to every inspector call and qualified
    into every raw ALTER TABLE statement; otherwise this would silently
    inspect (and alter) the wrong schema, as it did before this fix.
    """
    schema = (target_engine.get_execution_options() or {}).get("schema_translate_map", {}).get(None)

    inspector = inspect(target_engine)
    existing_tables = set(inspector.get_table_names(schema=schema))
    qualified_prefix = f'"{schema}".' if schema else ""
    with target_engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # brand new table — create_all already made it in full
            existing_columns = {col["name"] for col in inspector.get_columns(table.name, schema=schema)}
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
                conn.execute(
                    text(f'ALTER TABLE {qualified_prefix}"{table.name}" ADD COLUMN "{column.name}" {col_type}{default_sql}')
                )


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
# Each tenant (a verified Telegram user id) gets its own isolated database,
# so the entire existing single-tenant service layer works completely
# unchanged — it just gets handed a Session bound to that tenant's own
# database. Two backends implement that isolation (settings.tenant_backend):
#   "sqlite_file"      — one SQLite file per tenant (needs a persistent disk)
#   "postgres_schema"  — one Postgres SCHEMA per tenant on one shared DB
#                         (works on hosts with no persistent disk at all)

_TENANT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_tenant_engines: dict[str, Engine] = {}
_tenant_sessionmakers: dict[str, sessionmaker] = {}
_shared_postgres_engine: Engine | None = None
# Bot handlers (and, in general, any concurrent request) run their DB work
# via asyncio.to_thread, i.e. on real OS threads, not just concurrent
# coroutines on one event loop — so a plain "if tenant_id not in cache"
# check is a genuine TOCTOU race: two threads seeing the same brand-new
# tenant simultaneously both proceed to CREATE TABLE, and the loser gets
# "table already exists". A threading.Lock (not asyncio.Lock, which only
# guards a single event loop) with double-checked locking fixes this.
_tenant_engine_lock = threading.Lock()


def _get_shared_postgres_engine() -> Engine:
    global _shared_postgres_engine
    if _shared_postgres_engine is None:
        if not settings.postgres_url:
            raise RuntimeError("POSTGRES_URL is not set but TENANT_BACKEND=postgres_schema")
        # pool_pre_ping matters here: a free-tier Postgres (e.g. Neon) can
        # suspend itself after idling and drop old connections — pre_ping
        # detects that and transparently reconnects instead of erroring.
        _shared_postgres_engine = create_engine(settings.postgres_url, pool_pre_ping=True)
    return _shared_postgres_engine


def _schema_name_for_tenant(tenant_id: str) -> str:
    if not _TENANT_ID_RE.match(tenant_id):
        raise ValueError(f"Invalid tenant id: {tenant_id!r}")
    return f"tenant_{tenant_id}"


def _build_tenant_engine(tenant_id: str) -> Engine:
    from app import models  # noqa: F401  (register models on Base.metadata)

    if settings.tenant_backend == "postgres_schema":
        base_engine = _get_shared_postgres_engine()
        schema = _schema_name_for_tenant(tenant_id)
        with base_engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        # schema_translate_map rewrites every unqualified (schema=None)
        # table reference in emitted SQL to this tenant's schema — for both
        # DDL and DML — so none of the model/service code needs to know
        # about schemas at all.
        tenant_engine = base_engine.execution_options(schema_translate_map={None: schema})
    elif settings.tenant_backend == "sqlite_file":
        if not _TENANT_ID_RE.match(tenant_id):
            raise ValueError(f"Invalid tenant id: {tenant_id!r}")
        db_path = Path(settings.tenant_db_dir) / f"{tenant_id}.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        tenant_engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    else:
        raise RuntimeError(f"Unknown TENANT_BACKEND: {settings.tenant_backend!r}")

    Base.metadata.create_all(bind=tenant_engine)
    _apply_additive_migrations(tenant_engine)
    return tenant_engine


def get_engine_for_tenant(tenant_id: str) -> Engine:
    from app.auth import LOCAL_TENANT_ID

    if tenant_id == LOCAL_TENANT_ID:
        return engine

    if tenant_id not in _tenant_engines:
        with _tenant_engine_lock:
            if tenant_id not in _tenant_engines:  # re-check: another thread may have just built it
                tenant_engine = _build_tenant_engine(tenant_id)
                _tenant_engines[tenant_id] = tenant_engine
                _tenant_sessionmakers[tenant_id] = sessionmaker(bind=tenant_engine, autoflush=False, autocommit=False)

    return _tenant_engines[tenant_id]


def get_session_for_tenant(tenant_id: str) -> Session:
    from app.auth import LOCAL_TENANT_ID

    if tenant_id == LOCAL_TENANT_ID:
        return SessionLocal()

    get_engine_for_tenant(tenant_id)  # ensures it's created + registered
    return _tenant_sessionmakers[tenant_id]()
