"""End-to-end tests for the bot's document-upload flow, without a live
Telegram connection — Update/context are mocked, but everything downstream
(tenant DB resolution, import, participant auto-match, analysis) runs for
real against the synthetic fixture.
"""
import asyncio
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("telegram", reason="python-telegram-bot not installed (see backend/bot/requirements.txt)")

import app.database as database_module
from app.database import get_session_for_tenant
from app.models import AppConfig, ConversationSession, Message
from bot.main import handle_document, handle_pick_me

FIXTURE = Path(__file__).parent / "fixtures" / "sample_export.json"


@pytest.fixture()
def isolated_tenants(tmp_path, monkeypatch):
    monkeypatch.setattr(database_module.settings, "tenant_db_dir", str(tmp_path))
    database_module._tenant_engines.clear()
    database_module._tenant_sessionmakers.clear()
    yield tmp_path
    database_module._tenant_engines.clear()
    database_module._tenant_sessionmakers.clear()


def _make_update(telegram_user_id: int, file_path: Path):
    update = MagicMock()
    update.effective_user.id = telegram_user_id
    update.effective_user.language_code = "en"  # MagicMock defaults are truthy, so this must be explicit
    update.message.document.file_id = "fake-file-id"
    update.message.document.file_size = file_path.stat().st_size

    status_message = MagicMock()
    status_message.edit_text = AsyncMock()
    update.message.reply_text = AsyncMock(return_value=status_message)

    context = MagicMock()

    async def fake_download_to_drive(custom_path):
        shutil.copy(file_path, custom_path)

    tg_file = MagicMock()
    tg_file.download_to_drive = AsyncMock(side_effect=fake_download_to_drive)
    context.bot.get_file = AsyncMock(return_value=tg_file)
    context.chat_data = {}

    return update, context, status_message


def test_upload_auto_matches_participant_by_telegram_id(isolated_tenants):
    # sample_export.json uses sender id "user1000" for the export owner —
    # a Telegram user with id 1000 sending it should be auto-matched as "me".
    update, context, status_message = _make_update(telegram_user_id=1000, file_path=FIXTURE)

    asyncio.run(handle_document(update, context))

    db = get_session_for_tenant("1000")
    try:
        cfg = db.query(AppConfig).one()
        assert cfg.me_user_id == "user1000"
        assert cfg.other_user_id == "user2000"
        assert db.query(Message).count() == 6
        assert db.query(ConversationSession).count() >= 1
    finally:
        db.close()

    final_text = status_message.edit_text.call_args.args[0]
    assert "Imported 6 messages" in final_text


def test_upload_falls_back_to_manual_pick_when_id_unmatched(isolated_tenants):
    # Telegram id 9999 matches neither sender in the fixture -> must ask.
    update, context, status_message = _make_update(telegram_user_id=9999, file_path=FIXTURE)

    asyncio.run(handle_document(update, context))

    final_text = status_message.edit_text.call_args.args[0]
    assert "pick" in final_text.lower()
    assert context.chat_data["detected_participants"]

    kwargs = status_message.edit_text.call_args.kwargs
    keyboard = kwargs["reply_markup"]
    picked_sender_id = keyboard.inline_keyboard[0][0].callback_data.split(":", 1)[1]

    callback_update = MagicMock()
    callback_update.effective_user.id = 9999
    callback_update.callback_query.answer = AsyncMock()
    callback_update.callback_query.data = f"pickme:{picked_sender_id}"
    callback_update.callback_query.edit_message_text = AsyncMock()

    asyncio.run(handle_pick_me(callback_update, context))

    db = get_session_for_tenant("9999")
    try:
        cfg = db.query(AppConfig).one()
        assert cfg.me_user_id == picked_sender_id
        assert cfg.other_user_id != picked_sender_id
    finally:
        db.close()


def test_concurrent_uploads_for_same_tenant_do_not_race(isolated_tenants):
    """Regression test for the production outage: Telegram redelivering an
    update whose response arrived too late used to cause two overlapping
    handle_document runs for the same tenant to race on wipe-then-insert,
    crashing with a duplicate-key IntegrityError. The per-tenant asyncio
    lock in handle_document must serialize them instead.
    """
    update1, context1, status1 = _make_update(telegram_user_id=1000, file_path=FIXTURE)
    update2, context2, status2 = _make_update(telegram_user_id=1000, file_path=FIXTURE)

    async def _run_both():
        await asyncio.gather(
            handle_document(update1, context1),
            handle_document(update2, context2),
        )

    asyncio.run(_run_both())

    # neither run should have hit the generic error path (which is what a
    # duplicate-key crash would have produced)
    for status in (status1, status2):
        final_text = status.edit_text.call_args.args[0]
        assert "went wrong" not in final_text.lower(), final_text

    db = get_session_for_tenant("1000")
    try:
        # wipe-then-insert ran twice, serialized — still exactly one copy
        # of each message, not a crash and not double-counted
        assert db.query(Message).count() == 6
    finally:
        db.close()


def test_upload_shows_waiting_message_instead_of_silence_when_locked(isolated_tenants):
    """Regression test: pressing a button (or resending a file) while a
    previous upload for the same tenant is still processing used to look
    exactly like a dead bot — the lock made it wait silently with no
    feedback at all. It must now show a "still working" message instead.
    """
    import bot.main as bot_main

    # Dedicated tenant id, not reused by other tests: asyncio.Lock binds to
    # the event loop of its first real use, and every test here runs its
    # own asyncio.run() (a fresh loop) — reusing a tenant id (and therefore
    # its cached Lock) across two separate asyncio.run() calls that both
    # actually acquire it raises "bound to a different event loop".
    update, context, status = _make_update(telegram_user_id=5001, file_path=FIXTURE)

    async def _run():
        lock = bot_main._lock_for_tenant("5001")
        await lock.acquire()  # simulate an in-progress operation holding it
        try:
            task = asyncio.create_task(handle_document(update, context))
            await asyncio.sleep(0.2)  # let it reach the lock check and bail out
            texts = [c.args[0] for c in status.edit_text.call_args_list]
            assert any("previous upload" in tx or "kuting" in tx for tx in texts), texts
        finally:
            lock.release()
        await task

    asyncio.run(_run())


def test_pick_me_shows_waiting_toast_instead_of_silence_when_locked(isolated_tenants):
    import bot.main as bot_main

    context = MagicMock()
    context.chat_data = {
        "detected_participants": [
            {"sender_id": "user5002a", "sender_name": "Me", "message_count": 4},
            {"sender_id": "user5002b", "sender_name": "Them", "message_count": 2},
        ]
    }

    callback_update = MagicMock()
    callback_update.effective_user.id = 5002
    callback_update.effective_user.language_code = "en"
    callback_update.callback_query.answer = AsyncMock()
    callback_update.callback_query.data = "pickme:user5002a"
    callback_update.callback_query.edit_message_text = AsyncMock()

    async def _run():
        lock = bot_main._lock_for_tenant("5002")
        await lock.acquire()  # simulate an in-progress operation holding it, within THIS loop
        try:
            task = asyncio.create_task(handle_pick_me(callback_update, context))
            await asyncio.sleep(0.2)
            callback_update.callback_query.answer.assert_awaited_once()
            kwargs = callback_update.callback_query.answer.call_args.kwargs
            assert kwargs.get("show_alert") is True
            assert "previous upload" in kwargs.get("text", "")
        finally:
            lock.release()
        await task

    asyncio.run(_run())


def test_upload_rejects_oversized_file(isolated_tenants):
    update, context, _ = _make_update(telegram_user_id=1000, file_path=FIXTURE)
    update.message.document.file_size = 25 * 1024 * 1024  # over the 20MB cap

    asyncio.run(handle_document(update, context))

    # never got past the size check -> reply_text called with the size warning,
    # not the "Got it" status message that would trigger a download.
    update.message.reply_text.assert_awaited_once()
    assert "too large" in update.message.reply_text.call_args.args[0]
