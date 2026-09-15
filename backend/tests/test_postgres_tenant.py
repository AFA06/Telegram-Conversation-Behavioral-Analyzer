"""Regression tests for the Postgres-schema-per-tenant backend.

Requires a real reachable Postgres (set TEST_POSTGRES_URL, or run the
default local one: `docker run -d -e POSTGRES_PASSWORD=testpass
-e POSTGRES_DB=analyzer -p 5433:5432 postgres:16`). Skips the whole module
if that's not reachable — SQLite-backed tests elsewhere already cover the
default local/self-hosted path, so this isn't required for the base suite.

This backend matters because a free host with no persistent disk (e.g.
Render's free tier) can't use the SQLite-file-per-tenant backend at all —
tenant data lives in a shared Postgres instead, isolated per tenant by a
dedicated schema.
"""
import os

import pytest
from sqlalchemy import text

TEST_POSTGRES_URL = os.environ.get(
    "TEST_POSTGRES_URL", "postgresql+psycopg2://postgres:testpass@localhost:5433/analyzer"
)

pytest.importorskip("psycopg2", reason="psycopg2-binary not installed (see backend/requirements.txt)")


def _postgres_reachable() -> bool:
    try:
        from sqlalchemy import create_engine

        create_engine(TEST_POSTGRES_URL).connect().close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _postgres_reachable(), reason=f"No Postgres reachable at {TEST_POSTGRES_URL}")


# Fixed set of tenant ids these tests use — cleaned up before AND after
# each test so leftover schemas from a previous run (the Postgres
# container persists state across pytest invocations, unlike SQLite's
# tmp_path) never cause spurious collisions like duplicate-key errors.
_TEST_TENANT_IDS = ("pg_test_a", "pg_test_b", "pg_test_migration", "pg_test_data", "pg_test_race")


def _drop_test_schemas():
    from sqlalchemy import create_engine

    engine = create_engine(TEST_POSTGRES_URL)
    with engine.begin() as conn:
        for tenant_id in _TEST_TENANT_IDS:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "tenant_{tenant_id}" CASCADE'))
    engine.dispose()


@pytest.fixture()
def postgres_tenant_backend(monkeypatch):
    import app.config as config_module
    import app.database as database_module

    _drop_test_schemas()
    monkeypatch.setattr(config_module.settings, "tenant_backend", "postgres_schema")
    monkeypatch.setattr(config_module.settings, "postgres_url", TEST_POSTGRES_URL)
    monkeypatch.setattr(database_module, "_shared_postgres_engine", None)
    database_module._tenant_engines.clear()
    database_module._tenant_sessionmakers.clear()
    yield
    database_module._tenant_engines.clear()
    database_module._tenant_sessionmakers.clear()
    monkeypatch.setattr(database_module, "_shared_postgres_engine", None)
    _drop_test_schemas()


def test_postgres_schema_isolation(postgres_tenant_backend):
    from app.database import get_session_for_tenant
    from app.models import AppConfig
    from app.services.config_service import set_participants

    db_a = get_session_for_tenant("pg_test_a")
    db_b = get_session_for_tenant("pg_test_b")
    try:
        set_participants(db_a, me_user_id="userA", me_display_name="A", other_user_id="userB", other_display_name="B")
        set_participants(db_b, me_user_id="userC", me_display_name="C", other_user_id="userD", other_display_name="D")

        assert db_a.query(AppConfig).one().other_display_name == "B"
        assert db_b.query(AppConfig).one().other_display_name == "D"
    finally:
        db_a.close()
        db_b.close()


def test_postgres_additive_migration_targets_correct_schema(postgres_tenant_backend):
    """Regression test: inspect() and raw ALTER TABLE SQL must respect the
    tenant's schema_translate_map — this silently no-op'd (and would have
    silently altered the wrong schema) before the fix.
    """
    from app.database import _get_shared_postgres_engine, _tenant_engines, get_session_for_tenant

    db = get_session_for_tenant("pg_test_migration")
    db.close()

    pg = _get_shared_postgres_engine()
    with pg.begin() as conn:
        # a real row to confirm the migration backfills it, not just adds
        # an empty column
        conn.execute(
            text(
                "INSERT INTO tenant_pg_test_migration.app_config "
                "(id, timezone, grouping_window_minutes, session_gap_hours, min_sample_size, language, updated_at) "
                "VALUES (1, 'Asia/Tashkent', 5, 6, 10, 'en', now())"
            )
        )
        conn.execute(text("ALTER TABLE tenant_pg_test_migration.app_config DROP COLUMN language"))

    with pg.connect() as conn:
        cols = [
            r[0]
            for r in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='tenant_pg_test_migration' AND table_name='app_config'"
                )
            )
        ]
        assert "language" not in cols

    _tenant_engines.pop("pg_test_migration", None)
    db2 = get_session_for_tenant("pg_test_migration")
    db2.close()

    with pg.connect() as conn:
        cols_after = [
            r[0]
            for r in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='tenant_pg_test_migration' AND table_name='app_config'"
                )
            )
        ]
        assert "language" in cols_after
        value = conn.execute(text("SELECT language FROM tenant_pg_test_migration.app_config")).scalar()
        assert value == "en"


def test_postgres_local_tenant_unaffected(postgres_tenant_backend):
    """The 'local' tenant must always use the original SQLite database,
    regardless of tenant_backend — cloud config must never touch it.
    """
    from app.database import engine, get_session_for_tenant

    db = get_session_for_tenant("local")
    try:
        assert db.bind is engine
    finally:
        db.close()


def test_postgres_tenant_analysis_uses_correct_schema_not_raw_sql(postgres_tenant_backend):
    """Regression test: messages_dataframe() and the monthly-trends query
    used to build raw SQL strings passed straight to pandas.read_sql,
    which bypasses schema_translate_map entirely and queried the wrong
    (public) schema — raising 'relation "messages" does not exist' for any
    Postgres tenant with real data. Both must now use select() against the
    mapped Table so the schema mapping applies.
    """
    from pathlib import Path

    from app.database import get_session_for_tenant
    from app.routes.trends import monthly_trends
    from app.services.config_service import set_participants
    from app.services.importer import import_export_file
    from app.services.response_analyzer import run_full_analysis
    from app.services.statistics import compute_overview

    fixture = Path(__file__).parent / "fixtures" / "sample_export.json"
    db = get_session_for_tenant("pg_test_data")
    try:
        set_participants(db, me_user_id="user1000", me_display_name="Me", other_user_id="user2000", other_display_name="Them")
        import_export_file(db, fixture, "Asia/Tashkent")
        run_full_analysis(db)

        overview = compute_overview(db)
        assert overview.total_messages == 6
        assert overview.me_messages == 4

        months = monthly_trends(db=db)
        assert len(months) == 1
        assert months[0]["total_messages"] == 6
    finally:
        db.close()


def test_postgres_concurrent_first_contact_does_not_race(postgres_tenant_backend):
    """Regression test for a real production crash: multiple threads (the
    bot runs its DB work via asyncio.to_thread, i.e. real OS threads)
    hitting a brand-new tenant at the same moment used to race on both
    schema/table creation (CREATE TABLE from two threads at once) and the
    single-row AppConfig get-or-create (both see no row, both INSERT id=1).
    Runs 8 concurrent "first contact" attempts against one new tenant and
    requires all of them to succeed with exactly one config row at the end.
    """
    from concurrent.futures import ThreadPoolExecutor

    from app.database import get_session_for_tenant
    from app.models import AppConfig
    from app.services.config_service import get_or_create_config

    def _first_contact() -> str:
        db = get_session_for_tenant("pg_test_race")
        try:
            cfg = get_or_create_config(db)
            return cfg.timezone
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: _first_contact(), range(8)))

    assert all(r == "Asia/Tashkent" for r in results)

    db = get_session_for_tenant("pg_test_race")
    try:
        assert db.query(AppConfig).count() == 1
    finally:
        db.close()
