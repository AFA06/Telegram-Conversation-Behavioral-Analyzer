import asyncio
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.deps import get_current_db
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

    app.dependency_overrides[get_current_db] = override_get_db
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


def test_reimporting_a_different_conversation_fully_replaces_the_old_one(client: TestClient):
    """Regression test reported directly by a user: sending a genuinely
    different conversation after already having one imported still showed
    the old data. Root cause: the import route blindly trusted the
    *previous* import's me_user_id/other_user_id and ran analysis with
    them — the new "other" person's messages silently resolved to role
    "unknown" (excluded from every stat) while other_display_name kept
    showing the *previous* conversation's participant. Fixed by
    re-verifying the configured participants against every fresh import,
    not just the first one, and clearing them (rather than silently
    running analysis wrong) when they no longer match.
    """
    first = _import_sample(client)
    assert first["valid_count"] == 6

    overview_after_first = client.get("/api/overview").json()
    assert overview_after_first["chat_name"] == "Synthetic Test Chat"
    assert overview_after_first["total_messages"] == 6

    second_fixture = Path(__file__).parent / "fixtures" / "second_export.json"
    with second_fixture.open("rb") as f:
        resp = client.post("/api/import", files={"file": ("second_export.json", f, "application/json")})
    assert resp.status_code == 200, resp.text
    second = resp.json()
    assert second["valid_count"] == 3
    # "user2000" (the old "other") isn't in this file at all -> the stale
    # mapping is no longer valid, so this must NOT silently analyze wrong
    assert second["participants_configured"] is False
    assert second["analysis"] is None
    assert {d["sender_id"] for d in second["detected_participants"]} == {"user1000", "user3000"}

    overview_after_second = client.get("/api/overview").json()
    assert overview_after_second["chat_name"] == "A Different Chat Entirely"
    assert overview_after_second["total_messages"] == 3
    # stale participant identity is cleared, not left pointing at the old chat
    assert overview_after_second["other_display_name"] is None

    # nothing from the first conversation survives
    messages = client.get("/api/messages?limit=50").json()
    assert messages["total"] == 3
    all_text = " ".join(m["text"] or "" for m in messages["items"])
    assert "Synthetic" not in all_text
    assert "brand new chat" in all_text

    # configuring the new pair (as the Settings page / bot would) then
    # works correctly against the new data
    resp = client.put(
        "/api/config/participants",
        json={"me_user_id": "user1000", "me_display_name": "Me", "other_user_id": "user3000", "other_display_name": "Someone Else"},
    )
    assert resp.status_code == 200
    resp = client.post("/api/import/analyze")
    assert resp.status_code == 200, resp.text
    overview_final = client.get("/api/overview").json()
    assert overview_final["other_display_name"] == "Someone Else"
    assert overview_final["other_messages"] == 1


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


def test_historically_responsive_message_volume_matches_sample_size(client: TestClient):
    """Regression test: message_volume must reflect actual activity in that
    window, not silently read 0 because of a bucket-alignment mismatch
    between the volume lookup and the response-time buckets.
    """
    _import_sample(client)
    # lower the sample-size gate so the tiny fixture still produces windows
    client.put("/api/config/settings", json={"min_sample_size": 1})
    client.post("/api/import/analyze")

    data = client.get("/api/responses/historically-responsive?top_n=5").json()
    assert data["windows"], "expected at least one window with min_sample_size=1"
    for w in data["windows"]:
        assert w["message_volume"] >= 1, w


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


def test_telegram_webhook_404_when_bot_not_running(client: TestClient):
    # app.state.telegram_bot_app is never set in tests (no bot token/webhook
    # configured), so the endpoint must reject rather than crash.
    resp = client.post("/telegram/webhook", json={"update_id": 1})
    assert resp.status_code == 404


def test_telegram_webhook_rejects_wrong_secret_token(client: TestClient, monkeypatch):
    import app.main as main_module

    class _FakeBotApp:
        bot = object()

        async def process_update(self, update):
            raise AssertionError("must not be called when the secret token is wrong")

    app.state.telegram_bot_app = _FakeBotApp()
    monkeypatch.setattr(main_module.settings, "telegram_webhook_secret", "correct-secret")
    try:
        resp = client.post("/telegram/webhook", json={"update_id": 1}, headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"})
        assert resp.status_code == 403
    finally:
        del app.state.telegram_bot_app


def test_telegram_webhook_acks_immediately_without_waiting_for_processing(client: TestClient):
    """Regression test for the production outage: the webhook endpoint
    must return before the update finishes processing, not after —
    otherwise a slow update (a big import over a real network DB) exceeds
    Telegram's own webhook timeout, and Telegram resends the same update,
    causing it to be processed twice concurrently (this is exactly what
    caused duplicate-key crashes in production).
    """
    import app.main as main_module

    started = asyncio.Event()
    finished = asyncio.Event()

    class _SlowBotApp:
        bot = object()

        async def process_update(self, update):
            started.set()
            await asyncio.sleep(0.3)  # stands in for a slow real import
            finished.set()

    app.state.telegram_bot_app = _SlowBotApp()
    try:
        t0 = time.monotonic()
        resp = client.post("/telegram/webhook", json={"update_id": 1})
        elapsed = time.monotonic() - t0

        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        # the request must return well before the 0.3s of "processing" —
        # otherwise this is the exact bug that caused the outage
        assert elapsed < 0.3, f"webhook response took {elapsed}s — it's waiting for processing to finish"
    finally:
        del app.state.telegram_bot_app


def test_import_response_includes_detected_participants(client: TestClient):
    body = _import_sample(client)
    ids = {p["sender_id"] for p in body["detected_participants"]}
    assert ids == {"user1000", "user2000"}


def test_import_participants_endpoint(client: TestClient):
    _import_sample(client)
    data = client.get("/api/import/participants").json()
    assert {p["sender_id"] for p in data} == {"user1000", "user2000"}


def test_import_with_mismatched_participant_ids_reports_error_not_zeros(client: TestClient):
    """Regression test for the silent-zero bug: configuring ids that don't
    match any sender in the imported data must never silently run analysis
    against them (which used to produce a fake all-zero report). The
    import route now checks this proactively — before even attempting
    analysis — and reports the mismatch by clearing the stale config and
    returning the real detected senders, rather than attempting analysis
    and catching the resulting error (still covered directly for
    run_full_analysis itself in test_response_analyzer.py, and for the
    standalone /api/import/analyze endpoint below).
    """
    client.put(
        "/api/config/participants",
        json={"me_user_id": "938613594", "me_display_name": "Me", "other_user_id": "6424173522", "other_display_name": "Jayrona"},
    )
    with FIXTURE.open("rb") as f:
        resp = client.post("/api/import", files={"file": ("sample_export.json", f, "application/json")})
    body = resp.json()
    assert body["participants_configured"] is False
    assert body["analysis"] is None
    assert body["analysis_error"] is None  # no analysis was even attempted
    assert {d["sender_id"] for d in body["detected_participants"]} == {"user1000", "user2000"}

    cfg = client.get("/api/config").json()
    assert cfg["me_user_id"] is None
    assert cfg["other_user_id"] is None


def test_reanalyze_endpoint_still_reports_mismatched_ids_as_a_clear_error(client: TestClient):
    """The standalone /api/import/analyze endpoint (e.g. called after
    manually editing Settings) is a different code path from import_file
    and must still surface run_full_analysis's ValueError directly.
    """
    _import_sample(client)
    client.put(
        "/api/config/participants",
        json={"me_user_id": "totally-wrong-id", "me_display_name": "Me", "other_user_id": "also-wrong", "other_display_name": "Them"},
    )
    resp = client.post("/api/import/analyze")
    assert resp.status_code == 400
    assert "don't match any imported message senders" in resp.json()["detail"]
