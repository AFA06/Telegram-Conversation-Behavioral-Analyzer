from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

FIXTURE = Path(__file__).parent / "fixtures" / "sample_export.json"


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _import_sample(client: TestClient) -> None:
    client.put(
        "/api/config/participants",
        json={"me_user_id": "user1000", "me_display_name": "Me", "other_user_id": "user2000", "other_display_name": "Them"},
    )
    with FIXTURE.open("rb") as f:
        resp = client.post("/api/import", files={"file": ("sample_export.json", f, "application/json")})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_health(client: TestClient):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_import_and_auto_analyze(client: TestClient):
    body = _import_sample(client)
    assert body["valid_count"] == 6  # 7 records, 1 service message skipped
    assert body["skipped_count"] == 1
    assert body["participants_configured"] is True
    assert body["analysis"]["sessions"] >= 1


def test_overview_endpoint(client: TestClient):
    _import_sample(client)
    data = client.get("/api/overview").json()
    assert data["total_messages"] == 6
    assert data["me_messages"] == 4
    assert data["other_messages"] == 2


def test_activity_heatmap_endpoint(client: TestClient):
    _import_sample(client)
    hm = client.get("/api/activity/heatmap").json()
    assert len(hm["grid"]) == 7
    assert len(hm["grid"][0]) == 24


def test_responses_summary_endpoint(client: TestClient):
    _import_sample(client)
    data = client.get("/api/responses/summary?role=other").json()
    assert data["stats"]["count"] == 2  # her replies to burst(1,2) and to message 4


def test_responses_unanswered_endpoint(client: TestClient):
    _import_sample(client)
    data = client.get("/api/responses/unanswered?role=me").json()
    assert data["total"] >= 1
    assert "cannot indicate intentional ignoring" in data["explanation"]


def test_sessions_list_endpoint(client: TestClient):
    _import_sample(client)
    data = client.get("/api/sessions").json()
    assert data["total"] >= 1


def test_data_explorer_filters(client: TestClient):
    _import_sample(client)
    data = client.get("/api/messages?sender=other").json()
    assert data["total"] == 2
    assert all(item["sender_role"] == "other" for item in data["items"])


def test_export_json_and_html(client: TestClient):
    _import_sample(client)
    j = client.get("/api/export/json").json()
    assert j["overview"]["total_messages"] == 6

    html = client.get("/api/export/html")
    assert html.status_code == 200
    assert "Telegram Conversation Report" in html.text


def test_bot_ask_fastest(client: TestClient):
    _import_sample(client)
    resp = client.post("/api/bot/ask", json={"question": "What was her fastest reply?"})
    assert "Fastest observed reply" in resp.json()["answer"]


def test_bot_ask_overview_fallback(client: TestClient):
    _import_sample(client)
    resp = client.post("/api/bot/ask", json={"question": "random gibberish question"})
    assert "Total messages" in resp.json()["answer"]


def test_data_quality_report_endpoint_via_import_response(client: TestClient):
    body = _import_sample(client)
    assert "skipped_reasons" in body
    assert body["skipped_reasons"].get("service_message_ignored") == 1
