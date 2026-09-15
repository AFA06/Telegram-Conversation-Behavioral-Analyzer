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
from app.models import ConversationSession, ResponseEvent
from app.services import ask_engine, config_service
from app.services.importer import import_export_file
from app.services.response_analyzer import run_full_analysis
from app.utils.formatting import format_duration

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("analyzer-bot")

HELP_TEXT = (
    "Commands:\n"
    "/overview — totals and headline stats\n"
    "/dashboard — open the full chart dashboard\n"
    "/fastest — fastest observed reply\n"
    "/slowest — slowest observed reply\n"
    "/sessions — conversation session stats\n"
    "/windows — historically responsive windows\n"
    "/ask <question> — ask in plain language\n\n"
    "Everything here describes historical communication patterns only — "
    "never a claim about intent or availability."
)

EXPORT_INSTRUCTIONS = (
    "Send me your Telegram chat export and I'll analyze it — nothing leaves "
    "this bot's own server, and only you can ever see your results.\n\n"
    "How to export (Telegram Desktop, not the App Store version — that one "
    "doesn't have this feature):\n"
    "1. Open the chat you want to analyze\n"
    "2. Click the ⋮ menu at the top of the chat → Export chat history\n"
    "3. Set format to JSON (media can stay unchecked, it's not needed)\n"
    "4. Export, then send me the resulting result.json file right here"
)


def _tenant_id_for(update: Update) -> str:
    return str(update.effective_user.id)


def _db_for(update: Update) -> Session:
    return get_session_for_tenant(_tenant_id_for(update))


def _dashboard_keyboard() -> InlineKeyboardMarkup | None:
    if not settings.public_web_app_url:
        return None
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("📊 Open Dashboard", web_app=WebAppInfo(url=settings.public_web_app_url))]]
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Telegram Conversation Behavioral Analyzer\n\n" + EXPORT_INSTRUCTIONS
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    doc = update.message.document
    if not doc:
        return
    if doc.file_size and doc.file_size > 20 * 1024 * 1024:
        await update.message.reply_text("That file is too large (over 20MB). Try exporting without media.")
        return

    status = await update.message.reply_text("Got it — importing your export…")

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
                await status.edit_text("That doesn't look like valid JSON. Make sure you're sending result.json.")
                return

            if data.get("type") not in ("personal_chat", None):
                await status.edit_text(
                    "This looks like a group/channel export. This tool analyzes one-on-one "
                    "conversations only — please export a personal chat."
                )
                return

            db = _db_for(update)
            try:
                report = import_export_file(db, tmp_path, timezone_name=settings.default_timezone)
                detected = config_service.detect_participants(db, limit=5)

                my_sender_id = f"user{update.effective_user.id}"
                mine = next((d for d in detected if d["sender_id"] == my_sender_id), None)
                others = [d for d in detected if d["sender_id"] != my_sender_id]

                if len(detected) < 2:
                    await status.edit_text(
                        f"Imported {report.valid_count} messages, but I only found one sender in this "
                        "export — I need a two-person conversation to analyze response patterns."
                    )
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
                    keyboard = _dashboard_keyboard()
                    await status.edit_text(
                        f"Imported {report.valid_count} messages with {cfg.other_display_name}.\n"
                        f"Sessions: {result['sessions']} · Response events: {result['response_events']}\n\n"
                        "Tap below to see the full dashboard, or try /overview, /fastest, /ask." + ("" if keyboard else "\n\n(Dashboard link not configured yet — ask commands still work.)"),
                        reply_markup=keyboard,
                    )
                else:
                    # Couldn't auto-match "me" by Telegram id — ask explicitly.
                    buttons = [
                        [InlineKeyboardButton(f"This is me ({d['sender_name'] or d['sender_id']})", callback_data=f"pickme:{d['sender_id']}")]
                        for d in detected[:2]
                    ]
                    context.chat_data["detected_participants"] = detected[:2]
                    await status.edit_text(
                        f"Imported {report.valid_count} messages. I couldn't automatically tell which "
                        "sender is you — please pick:",
                        reply_markup=InlineKeyboardMarkup(buttons),
                    )
            finally:
                db.close()
        finally:
            tmp_path.unlink(missing_ok=True)
    except Exception:
        logger.exception("handle_document failed for chat %s", update.effective_chat.id if update.effective_chat else "?")
        try:
            await status.edit_text(
                "Something went wrong while importing that file. This has been logged — "
                "please try sending it again in a moment."
            )
        except Exception:
            pass


async def handle_pick_me(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    me_id = query.data.split(":", 1)[1]

    detected = context.chat_data.get("detected_participants", [])
    mine = next((d for d in detected if d["sender_id"] == me_id), None)
    other = next((d for d in detected if d["sender_id"] != me_id), None)
    if not mine or not other:
        await query.edit_message_text("Something went wrong — please resend the export file.")
        return

    db = _db_for(update)
    try:
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
        keyboard = _dashboard_keyboard()
        await query.edit_message_text(
            f"Set up! Sessions: {result['sessions']} · Response events: {result['response_events']}\n\n"
            "Tap below to see the full dashboard, or try /overview, /fastest, /ask.",
            reply_markup=keyboard,
        )
    finally:
        db.close()


async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = _dashboard_keyboard()
    if not keyboard:
        await update.message.reply_text("Dashboard isn't configured on this server yet.")
        return
    await update.message.reply_text("Tap below to open your dashboard:", reply_markup=keyboard)


async def overview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from app.services import statistics

    db = _db_for(update)
    try:
        cfg = config_service.get_or_create_config(db)
        if not cfg.me_user_id:
            await update.message.reply_text(EXPORT_INSTRUCTIONS)
            return
        ov = statistics.compute_overview(db)
        if not ov.total_messages:
            await update.message.reply_text("No conversation imported yet.")
            return
        other = cfg.other_display_name or "Other person"
        sessions = db.query(ConversationSession).count()
        text = (
            f"Total messages: {ov.total_messages}\n"
            f"{other}: {ov.other_messages} ({ov.other_percentage}%)\n"
            f"You: {ov.me_messages} ({ov.me_percentage}%)\n"
            f"Period: {ov.first_message_date} to {ov.last_message_date}\n"
            f"Active days: {ov.active_days}\n"
            f"Conversation sessions: {sessions}"
        )
        await update.message.reply_text(text)
    finally:
        db.close()


async def fastest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _db_for(update)
    try:
        event = db.query(ResponseEvent).filter_by(response_role="other").order_by(ResponseEvent.response_seconds.asc()).first()
        if event is None:
            await update.message.reply_text("No response events yet — send your export first.")
            return
        await update.message.reply_text(f"Fastest observed reply: {format_duration(event.response_seconds)}")
    finally:
        db.close()


async def slowest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = _db_for(update)
    try:
        event = db.query(ResponseEvent).filter_by(response_role="other").order_by(ResponseEvent.response_seconds.desc()).first()
        if event is None:
            await update.message.reply_text("No response events yet — send your export first.")
            return
        await update.message.reply_text(
            f"Slowest observed reply: {format_duration(event.response_seconds)}\n"
            "This is the longest observed delay in the imported history. "
            "The system cannot determine whether the delay was intentional."
        )
    finally:
        db.close()


async def sessions_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from app.routes.sessions import sessions_summary  # reuse the same aggregate logic

    db = _db_for(update)
    try:
        data = sessions_summary(db)
        if not data.get("count"):
            await update.message.reply_text("No conversation sessions yet — send your export first.")
            return
        text = (
            f"Sessions: {data['count']}\n"
            f"Average duration: {format_duration(data['average_duration_seconds'])}\n"
            f"Median duration: {format_duration(data['median_duration_seconds'])}\n"
            f"Longest session: {format_duration(data['longest_duration_seconds'])}\n"
            f"Avg. messages/session: {data['average_messages_per_session']}"
        )
        await update.message.reply_text(text)
    finally:
        db.close()


async def windows(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from app.routes.responses import historically_responsive

    db = _db_for(update)
    try:
        data = historically_responsive(top_n=5, db=db)
        if not data.get("windows"):
            await update.message.reply_text(data.get("note", "Not enough data yet."))
            return
        lines = [
            f"{i+1}. {w['weekday_name']} {w['start_label']}-{w['end_label']} (n={w['sample_size']})"
            for i, w in enumerate(data["windows"])
        ]
        await update.message.reply_text("Historically responsive windows:\n" + "\n".join(lines) + f"\n\n{data['note']}")
    finally:
        db.close()


async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    question = " ".join(context.args) if context.args else ""
    if not question:
        await update.message.reply_text("Usage: /ask <question>, e.g. /ask when is she usually most active?")
        return
    db = _db_for(update)
    try:
        result = ask_engine.answer(db, question)
        await update.message.reply_text(result.get("answer", "No answer available."))
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
    app.add_handler(CommandHandler("dashboard", dashboard))
    app.add_handler(CommandHandler("overview", overview))
    app.add_handler(CommandHandler("fastest", fastest))
    app.add_handler(CommandHandler("slowest", slowest))
    app.add_handler(CommandHandler("sessions", sessions_cmd))
    app.add_handler(CommandHandler("windows", windows))
    app.add_handler(CommandHandler("ask", ask))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(CallbackQueryHandler(handle_pick_me, pattern=r"^pickme:"))
    return app


def main() -> None:
    application = build_application()
    logger.info("Starting bot in multi_tenant=%s mode", settings.multi_tenant)
    application.run_polling()


if __name__ == "__main__":
    main()
