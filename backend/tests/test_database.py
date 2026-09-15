"""Regression tests for tenant database resolution.

These deliberately do NOT go through FastAPI's dependency-override
mechanism (unlike the API integration tests), because overriding
``get_current_db`` directly would bypass the exact code path that had a
real bug: ``get_session_for_tenant("local")`` raised KeyError because the
"local" tenant was never registered in the per-tenant sessionmaker cache.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.database as database_module
from app.auth import LOCAL_TENANT_ID
from app.database import Base, get_session_for_tenant


@pytest.fixture()
def isolated_local_db(monkeypatch, tmp_path):
    """Points the global 'local' database at a throwaway sqlite file so
    this test never touches the real data/analyzer.db.
    """
    engine = create_engine(f"sqlite:///{tmp_path/'test_local.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(database_module, "engine", engine)
    monkeypatch.setattr(database_module, "SessionLocal", sessionmaker(bind=engine))
    yield


def test_get_session_for_tenant_local_does_not_raise(isolated_local_db):
    session = get_session_for_tenant(LOCAL_TENANT_ID)
    try:
        assert session.query(database_module.Base.metadata.tables["app_config"]).count() >= 0
    finally:
        session.close()


def test_get_session_for_tenant_creates_isolated_file_per_tenant(tmp_path, monkeypatch):
    monkeypatch.setattr(database_module.settings, "tenant_db_dir", str(tmp_path))
    database_module._tenant_engines.clear()
    database_module._tenant_sessionmakers.clear()

    s1 = get_session_for_tenant("111")
    s2 = get_session_for_tenant("222")
    s1.close()
    s2.close()

    assert (tmp_path / "111.db").exists()
    assert (tmp_path / "222.db").exists()


def test_get_session_for_tenant_rejects_malformed_tenant_id(tmp_path, monkeypatch):
    monkeypatch.setattr(database_module.settings, "tenant_db_dir", str(tmp_path))
    with pytest.raises(ValueError):
        get_session_for_tenant("../../etc/passwd")
