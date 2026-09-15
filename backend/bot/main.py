"""Optional Telegram bot (spec Phase 7 / sections 32-35).

Run with:  python -m bot.main

The bot never reads the Telegram export or the database directly. It only
calls the local FastAPI backend's REST API for already-computed, aggregated
statistics — so the bot process could in principle run anywhere, without
ever seeing a single message of the real conversation.
"""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from app.config import settings
from app.utils.formatting import format_duration
from bot.client import backend

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("analyzer-bot")

HELP_TEXT = (
    "Commands:\n"
    "/overview — totals and headline stats\n"
    "/activity — most active recurring windows\n"
    "/response — response-time summary\n"
    "/fastest — fastest observed reply\n"
    "/slowest — slowest observed reply\n"
    "/longest — top longest response delays\n"
    "/sessions — conversation session stats\n"
    "/windows — historically responsive windows\n"
    "/trends — recent monthly trend\n"
    "/ask <question> — ask in plain language\n\n"
    "Everything here describes historical communication patterns only — "
    "never a claim about intent or availability."
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Telegram Conversation Behavioral Analyzer bot.\n"
        "This bot reads only pre-computed statistics from your local backend — "
        "never the raw conversation.\n\n" + HELP_TEXT
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT)


async def overview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = await backend.get("/overview")
    if not data.get("total_messages"):
        await update.message.reply_text("No conversation imported yet.")
        return
    other = data.get("other_display_name") or "Other person"
    text = (
        f"Total messages: {data['total_messages']}\n"
        f"{other}: {data['other_messages']} ({data['other_percentage']}%)\n"
        f"You: {data['me_messages']} ({data['me_percentage']}%)\n"
        f"Period: {data['first_message_date']} to {data['last_message_date']}\n"
        f"Active days: {data['active_days']}\n"
        f"Conversation sessions: {data['conversation_sessions']}"
    )
    await update.message.reply_text(text)


async def activity(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    windows = await backend.get("/activity/top-windows", {"role": "other", "window_minutes": 180, "top_n": 5})
    if not windows:
        await update.message.reply_text("Not enough data yet.")
        return
    lines = [f"{i+1}. {w['weekday_name']} {w['start_label']}-{w['end_label']} ({w['message_count']} messages)" for i, w in enumerate(windows)]
    await update.message.reply_text("Most active recurring windows:\n" + "\n".join(lines))


async def response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = await backend.get("/responses/summary", {"role": "other"})
    stats = data.get("stats")
    if not stats:
        await update.message.reply_text("No response events yet.")
        return
    text = (
        f"Fastest: {format_duration(stats['fastest_seconds'])}\n"
        f"Median: {format_duration(stats['median_seconds'])}\n"
        f"Average: {format_duration(stats['average_seconds'])}\n"
        f"90th percentile: {format_duration(stats['p90_seconds'])}\n"
        f"Sample size: {stats['count']}"
    )
    await update.message.reply_text(text)


async def fastest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    events = await backend.get("/responses/fastest", {"role": "other", "limit": 1})
    if not events:
        await update.message.reply_text("No response events yet.")
        return
    e = events[0]
    await update.message.reply_text(f"Fastest observed reply: {e['response_formatted']}")


async def slowest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    events = await backend.get("/responses/longest", {"role": "other", "limit": 1})
    if not events:
        await update.message.reply_text("No response events yet.")
        return
    e = events[0]
    await update.message.reply_text(
        f"Slowest observed reply: {e['response_formatted']}\n"
        "This is the longest observed delay in the imported history. "
        "The system cannot determine whether the delay was intentional."
    )


async def longest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    events = await backend.get("/responses/longest", {"role": "other", "limit": 5})
    if not events:
        await update.message.reply_text("No response events yet.")
        return
    lines = [f"#{i+1} — {e['response_formatted']}" for i, e in enumerate(events)]
    await update.message.reply_text("Longest observed response delays:\n" + "\n".join(lines))


async def sessions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = await backend.get("/sessions/summary")
    if not data.get("count"):
        await update.message.reply_text("No conversation sessions yet.")
        return
    text = (
        f"Sessions: {data['count']}\n"
        f"Average duration: {format_duration(data['average_duration_seconds'])}\n"
        f"Median duration: {format_duration(data['median_duration_seconds'])}\n"
        f"Longest session: {format_duration(data['longest_duration_seconds'])}\n"
        f"Avg. messages/session: {data['average_messages_per_session']}"
    )
    await update.message.reply_text(text)


async def windows(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = await backend.get("/responses/historically-responsive", {"top_n": 5})
    if not data.get("windows"):
        await update.message.reply_text(data.get("note", "Not enough data yet."))
        return
    lines = [f"{i+1}. {w['weekday_name']} {w['start_label']}-{w['end_label']} (n={w['sample_size']})" for i, w in enumerate(data["windows"])]
    await update.message.reply_text("Historically responsive windows:\n" + "\n".join(lines) + f"\n\n{data['note']}")


async def trends(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = await backend.get("/trends/monthly")
    if not data:
        await update.message.reply_text("No data yet.")
        return
    last = data[-1]
    text = (
        f"{last['month']}: {last['total_messages']} messages "
        f"({last['other_messages']} from them, {last['me_messages']} from you)\n"
        f"Median response: {format_duration(last['median_response_seconds'])}\n"
        f"Sessions: {last['session_count']}"
    )
    await update.message.reply_text(text)


async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    question = " ".join(context.args) if context.args else ""
    if not question:
        await update.message.reply_text("Usage: /ask <question>, e.g. /ask when is she usually most active?")
        return
    data = await backend.post("/bot/ask", {"question": question})
    await update.message.reply_text(data.get("answer", "No answer available."))


def build_application() -> Application:
    if not settings.telegram_bot_token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. Put it in backend/.env (see .env.example) — never commit it."
        )
    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("overview", overview))
    app.add_handler(CommandHandler("activity", activity))
    app.add_handler(CommandHandler("response", response))
    app.add_handler(CommandHandler("fastest", fastest))
    app.add_handler(CommandHandler("slowest", slowest))
    app.add_handler(CommandHandler("longest", longest))
    app.add_handler(CommandHandler("sessions", sessions))
    app.add_handler(CommandHandler("windows", windows))
    app.add_handler(CommandHandler("trends", trends))
    app.add_handler(CommandHandler("ask", ask))
    return app


def main() -> None:
    application = build_application()
    logger.info("Starting bot (backend: %s)", settings.bot_backend_url)
    application.run_polling()


if __name__ == "__main__":
    main()
