from sqlalchemy import create_engine, inspect, text

from app.database import Base, _apply_additive_migrations


def test_additive_migration_adds_missing_column(tmp_path):
    db_path = tmp_path / "old_schema.db"
    engine = create_engine(f"sqlite:///{db_path}")

    # Simulate a database created before AppConfig.language existed: create
    # every table via the current metadata, then drop the new column to
    # imitate an old, already-deployed schema.
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE app_config DROP COLUMN language"))
        conn.execute(
            text(
                "INSERT INTO app_config (id, timezone, grouping_window_minutes, session_gap_hours, min_sample_size, updated_at) "
                "VALUES (1, 'Asia/Tashkent', 5, 6, 10, '2026-01-01 00:00:00')"
            )
        )
        conn.commit()

    columns_before = {c["name"] for c in inspect(engine).get_columns("app_config")}
    assert "language" not in columns_before

    _apply_additive_migrations(engine)

    columns_after = {c["name"] for c in inspect(engine).get_columns("app_config")}
    assert "language" in columns_after

    with engine.connect() as conn:
        row = conn.execute(text("SELECT id, language FROM app_config")).fetchone()
        assert row.language == "en"  # existing row backfilled with the column default


def test_additive_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "current_schema.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)

    # Already up to date — must be a safe no-op, not an error.
    _apply_additive_migrations(engine)
    _apply_additive_migrations(engine)


def test_additive_migration_skips_nonexistent_tables(tmp_path):
    db_path = tmp_path / "empty.db"
    engine = create_engine(f"sqlite:///{db_path}")
    # No create_all at all — every table is "missing", migration must not error.
    _apply_additive_migrations(engine)
