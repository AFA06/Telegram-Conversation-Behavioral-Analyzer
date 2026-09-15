"""Production Telegram bot: upload flow + Mini App dashboard (Phase 9).

Unlike the original local-CLI-paired bot (which called the HTTP API), this
bot talks to the tenant-scoped database directly, in-process — it already
knows the caller's authenticated Telegram user id from the Update itself
(Telegram's own infrastructure verifies that), so there is no separate
auth step needed for the bot's own actions. The same tenant database is
later read by the Mini App dashboard, authenticated there via Telegram's
signed ``initData`` (see app/auth.py) — so a user's data is only ever
reachable by that same verified Telegram identity, through either surface.

Flow:
  1. /start -> instructions to export chat history as JSON from Telegram
     Desktop, then send the result.json file directly in this chat.
     Language is auto-detected from the user's Telegram client on first
     contact (English/Uzbek), switchable any time via /language.
  2. User sends the file -> imported into their own isolated database.
  3. If the file's two senders include this Telegram user's own id (the
     normal case), participants are configured automatically — no manual
     id entry. Otherwise, inline buttons let them pick which sender is them.
  4. Analysis runs automatically; a "Open Dashboard" button opens the Mini
     App (same React dashboard, running inside Telegram).
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from sqlalchemy.orm import Session
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    WebAppInfo,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from app.config import settings
from app.database import get_session_for_tenant
from app.models import AppConfig, ConversationSession, ResponseEvent
from app.services import ask_engine, config_service
from app.services.config_service import CONFIG_ROW_ID
from app.services.importer import import_export_file
from app.services.response_analyzer import run_full_analysis
from app.utils.formatting import format_duration
from bot.i18n import SUPPORTED_LANGUAGES, detect_language, t

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("analyzer-bot")

LANGUAGE_LABELS = {"en": "English", "uz": "O'zbekcha"}


def _tenant_id_for(update: Update) -> str:
    return str(update.effective_user.id)


def _db_for(update: Update) -> Session:
    return get_session_for_tenant(_tenant_id_for(update))


def _resolve_language(db: Session, update: Update) -> str:
    """Returns the tenant's UI language, auto-detecting from the Telegram
    client's language on first-ever contact (any handler, not just
    /start) and never overriding an existing/explicit choice afterwards.
    """
    existing = db.get(AppConfig, CONFIG_ROW_ID)
    cfg = config_service.get_or_create_config(db)
    if existing is None:
        cfg.language = detect_language(update.effective_user.language_code)
        db.commit()
    return cfg.language


def _dashboard_keyboard(lang: str) -> InlineKeyboardMarkup | None:
    if not settings.public_web_app_url:
        return None
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(t(lang, "dashboard_button"), web_app=WebAppInfo(url=settings.public_web_app_url))]]
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _db_for(update)
    try:
        lang = _resolve_language(db, update)
    finally:
        db.close()
    await update.message.reply_text(t(lang, "start", export_instructions=t(lang, "export_instructions")))


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _db_for(update)
    try:
        lang = _resolve_language(db, update)
    finally:
        db.close()
    await update.message.reply_text(t(lang, "help"))


async def language_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _db_for(update)
    try:
        lang = _resolve_language(db, update)
    finally:
        db.close()
    buttons = [[InlineKeyboardButton(label, callback_data=f"setlang:{code}") for code, label in LANGUAGE_LABELS.items()]]
    await update.message.reply_text(t(lang, "choose_language"), reply_markup=InlineKeyboardMarkup(buttons))


async def handle_set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    lang_code = query.data.split(":", 1)[1]
    if lang_code not in SUPPORTED_LANGUAGES:
        return
    db = _db_for(update)
    try:
        cfg = config_service.get_or_create_config(db)
        cfg.language = lang_code
        db.commit()
    finally:
        db.close()
    await query.edit_message_text(t(lang_code, "language_set"))


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    doc = update.message.document
    if not doc:
        return

    setup_db = _db_for(update)
    try:
        lang = _resolve_language(setup_db, update)
    finally:
        setup_db.close()

    if doc.file_size and doc.file_size > 20 * 1024 * 1024:
        await update.message.reply_text(t(lang, "file_too_large"))
        return

    status = await update.message.reply_text(t(lang, "importing"))

    try:
        tg_file = await context.bot.get_file(doc.file_id)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            await tg_file.download_to_drive(custom_path=str(tmp_path))

            import json

            try:
                data = json.loads(tmp_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                await status.edit_text(t(lang, "invalid_json"))
                return

            if data.get("type") not in ("personal_chat", None):
                await status.edit_text(t(lang, "group_export_rejected"))
                return

            db = _db_for(update)
            try:
                report = import_export_file(db, tmp_path, timezone_name=settings.default_timezone)
                detected = config_service.detect_participants(db, limit=5)

                my_sender_id = f"user{update.effective_user.id}"
                mine = next((d for d in detected if d["sender_id"] == my_sender_id), None)
                others = [d for d in detected if d["sender_id"] != my_sender_id]

                if len(detected) < 2:
                    await status.edit_text(t(lang, "only_one_sender", count=report.valid_count))
                    return

                if mine and others:
                    cfg = config_service.set_participants(
                        db,
                        me_user_id=mine["sender_id"],
                        me_display_name=mine["sender_name"] or "Me",
                        other_user_id=others[0]["sender_id"],
                        other_display_name=others[0]["sender_name"] or "Other person",
                    )
                    cfg.timezone = settings.default_timezone
                    db.commit()
                    result = run_full_analysis(db)
                    keyboard = _dashboard_keyboard(lang)
                    dashboard_note = "" if keyboard else t(lang, "dashboard_not_configured_note")
                    await status.edit_text(
                        t(
                            lang,
                            "import_success",
                            count=report.valid_count,
                            other=cfg.other_display_name,
                            sessions=result["sessions"],
                            events=result["response_events"],
                            dashboard_note=dashboard_note,
                        ),
                        reply_markup=keyboard,
                    )
                else:
                    # Couldn't auto-match "me" by Telegram id — ask explicitly.
                    buttons = [
                        [InlineKeyboardButton(t(lang, "pick_me_button", name=d["sender_name"] or d["sender_id"]), callback_data=f"pickme:{d['sender_id']}")]
                        for d in detected[:2]
                    ]
                    context.chat_data["detected_participants"] = detected[:2]
                    await status.edit_text(
                        t(lang, "pick_me_prompt", count=report.valid_count),
                        reply_markup=InlineKeyboardMarkup(buttons),
                    )
            finally:
                db.close()
        finally:
            tmp_path.unlink(missing_ok=True)
    except Exception:
        logger.exception("handle_document failed for chat %s", update.effective_chat.id if update.effective_chat else "?")
        try:
            await status.edit_text(t(lang, "import_error"))
        except Exception:
            pass


async def handle_pick_me(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    me_id = query.data.split(":", 1)[1]

    db = _db_for(update)
    try:
        lang = _resolve_language(db, update)

        detected = context.chat_data.get("detected_participants", [])
        mine = next((d for d in detected if d["sender_id"] == me_id), None)
        other = next((d for d in detected if d["sender_id"] != me_id), None)
        if not mine or not other:
            await query.edit_message_text(t(lang, "pick_me_error"))
            return

        cfg = config_service.set_participants(
            db,
            me_user_id=mine["sender_id"],
            me_display_name=mine["sender_name"] or "Me",
            other_user_id=other["sender_id"],
            other_display_name=other["sender_name"] or "Other person",
        )
        cfg.timezone = settings.default_timezone
        db.commit()
        result = run_full_analysis(db)
        keyboard = _dashboard_keyboard(lang)
        await query.edit_message_text(
            t(lang, "setup_complete", sessions=result["sessions"], events=result["response_events"]),
            reply_markup=keyboard,
        )
    finally:
        db.close()


async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _db_for(update)
    try:
        lang = _resolve_language(db, update)
    finally:
        db.close()
    keyboard = _dashboard_keyboard(lang)
    if not keyboard:
        await update.message.reply_text(t(lang, "dashboard_not_configured"))
        return
    await update.message.reply_text(t(lang, "dashboard_prompt"), reply_markup=keyboard)


async def overview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from app.services import statistics

    db = _db_for(update)
    try:
        lang = _resolve_language(db, update)
        cfg = config_service.get_or_create_config(db)
        if not cfg.me_user_id:
            await update.message.reply_text(t(lang, "start", export_instructions=t(lang, "export_instructions")))
            return
        ov = statistics.compute_overview(db)
        if not ov.total_messages:
            await update.message.reply_text(t(lang, "no_conversation"))
            return
        other = cfg.other_display_name or "Other person"
        sessions = db.query(ConversationSession).count()
        text = t(
            lang,
            "overview_template",
            total=ov.total_messages,
            other_name=other,
            other_count=ov.other_messages,
            other_pct=ov.other_percentage,
            me_count=ov.me_messages,
            me_pct=ov.me_percentage,
            first=ov.first_message_date,
            last=ov.last_message_date,
            active_days=ov.active_days,
            sessions=sessions,
        )
        await update.message.reply_text(text)
    finally:
        db.close()


async def fastest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _db_for(update)
    try:
        lang = _resolve_language(db, update)
        event = db.query(ResponseEvent).filter_by(response_role="other").order_by(ResponseEvent.response_seconds.asc()).first()
        if event is None:
            await update.message.reply_text(t(lang, "no_response_yet"))
            return
        await update.message.reply_text(t(lang, "fastest_reply", duration=format_duration(event.response_seconds)))
    finally:
        db.close()


async def slowest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _db_for(update)
    try:
        lang = _resolve_language(db, update)
        event = db.query(ResponseEvent).filter_by(response_role="other").order_by(ResponseEvent.response_seconds.desc()).first()
        if event is None:
            await update.message.reply_text(t(lang, "no_response_yet"))
            return
        await update.message.reply_text(t(lang, "slowest_reply", duration=format_duration(event.response_seconds)))
    finally:
        db.close()


async def sessions_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from app.routes.sessions import sessions_summary  # reuse the same aggregate logic

    db = _db_for(update)
    try:
        lang = _resolve_language(db, update)
        data = sessions_summary(db)
        if not data.get("count"):
            await update.message.reply_text(t(lang, "no_sessions_yet"))
            return
        text = t(
            lang,
            "sessions_template",
            count=data["count"],
            avg=format_duration(data["average_duration_seconds"]),
            median=format_duration(data["median_duration_seconds"]),
            longest=format_duration(data["longest_duration_seconds"]),
            avg_msgs=data["average_messages_per_session"],
        )
        await update.message.reply_text(text)
    finally:
        db.close()


async def windows(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from app.routes.responses import historically_responsive

    db = _db_for(update)
    try:
        lang = _resolve_language(db, update)
        data = historically_responsive(top_n=5, db=db)
        if not data.get("windows"):
            await update.message.reply_text(data.get("note") or t(lang, "windows_not_enough"))
            return
        lines = [
            f"{i+1}. {w['weekday_name']} {w['start_label']}-{w['end_label']} (n={w['sample_size']})"
            for i, w in enumerate(data["windows"])
        ]
        await update.message.reply_text(t(lang, "windows_template", lines="\n".join(lines), note=data["note"]))
    finally:
        db.close()


async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    question = " ".join(context.args) if context.args else ""
    db = _db_for(update)
    try:
        lang = _resolve_language(db, update)
        if not question:
            await update.message.reply_text(t(lang, "ask_usage"))
            return
        result = ask_engine.answer(db, question, lang=lang)
        await update.message.reply_text(result.get("answer") or t(lang, "no_answer"))
    finally:
        db.close()


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled error while processing update %s", update, exc_info=context.error)


def build_application() -> Application:
    if not settings.telegram_bot_token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. Put it in backend/.env (see .env.example) — never commit it."
        )
    # Default httpx timeouts (5s) are too tight for get_file/download on a
    # slower connection — a timeout there previously left the user staring
    # at "Got it..." forever with no error shown (see handle_document's
    # try/except for the user-facing side of this fix).
    request = HTTPXRequest(connect_timeout=15.0, read_timeout=30.0, write_timeout=30.0, media_write_timeout=60.0)
    app = Application.builder().token(settings.telegram_bot_token).request(request).build()
    app.add_error_handler(_on_error)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("language", language_cmd))
    app.add_handler(CommandHandler("dashboard", dashboard))
    app.add_handler(CommandHandler("overview", overview))
    app.add_handler(CommandHandler("fastest", fastest))
    app.add_handler(CommandHandler("slowest", slowest))
    app.add_handler(CommandHandler("sessions", sessions_cmd))
    app.add_handler(CommandHandler("windows", windows))
    app.add_handler(CommandHandler("ask", ask))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(handle_pick_me, pattern=r"^pickme:"))
    app.add_handler(CallbackQueryHandler(handle_set_language, pattern=r"^setlang:"))
    return app


def main() -> None:
    application = build_application()
    logger.info("Starting bot in multi_tenant=%s mode", settings.multi_tenant)
    application.run_polling()


if __name__ == "__main__":
    main()
