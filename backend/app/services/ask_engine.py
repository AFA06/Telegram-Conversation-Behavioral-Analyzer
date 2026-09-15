"""Rule-based natural-language question answering for the /ask bot command
(spec sections 33-35).

Deliberately NOT an LLM call: this matches keywords in the question to one
of a fixed set of canonical queries against the already-computed local
statistics, then fills a template with the real numbers. No message content
or question text ever leaves the machine. If a future version wants true
LLM-based phrasing, it must only ever be handed these aggregated numbers —
never the raw conversation — and only when the user explicitly opts in.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import ConversationSession, ResponseEvent
from app.services import activity_analyzer, config_service, session_analyzer, statistics
from app.services.response_analyzer import best_response_windows, response_percentiles, response_stats_by_weekday
from app.utils.formatting import format_duration

_KEYWORD_HANDLERS: list[tuple[tuple[str, ...], str]] = [
    (("most active", "usually active", "when is she", "when is he", "when active"), "most_active"),
    (("fastest",), "fastest"),
    (("longest", "slowest"), "longest_delay"),
    (("longest conversation", "longest session"), "longest_session"),
    (("best day", "which day"), "best_day"),
    (("last month", "this month"), "recent_activity"),
    (("how active",), "recent_activity"),
]


def _match_intent(question: str) -> str:
    q = question.lower()
    if "conversation" in q and ("longest" in q or "biggest" in q):
        return "longest_session"
    for keywords, intent in _KEYWORD_HANDLERS:
        if any(k in q for k in keywords):
            return intent
    return "overview"


def answer(db: Session, question: str) -> dict:
    cfg = config_service.get_or_create_config(db)
    other_name = cfg.other_display_name or "The other person"
    intent = _match_intent(question)

    if intent == "most_active":
        df = statistics.messages_dataframe(db)
        windows = activity_analyzer.top_activity_windows(df, role="other", window_minutes=180, top_n=3)
        if not windows:
            return _reply("Not enough data yet to estimate activity windows.")
        lines = [
            f"{i+1}. {w['weekday_name']} — {w['start_label']}-{w['end_label']} ({w['message_count']} messages)"
            for i, w in enumerate(windows)
        ]
        total = int(df[df["role"] == "other"].shape[0]) if not df.empty else 0
        sessions = db.query(ConversationSession).count()
        text = (
            f"Historically, {other_name}'s highest message activity is:\n" + "\n".join(lines) +
            f"\n\nThese are based on {total} messages across {sessions} conversation sessions.\n"
            "This indicates historical activity, not guaranteed availability."
        )
        return _reply(text)

    if intent == "fastest":
        event = db.query(ResponseEvent).filter_by(response_role="other").order_by(ResponseEvent.response_seconds.asc()).first()
        if event is None:
            return _reply("No response events recorded yet — run the analysis step first.")
        text = (
            f"Fastest observed reply from {other_name}: {format_duration(event.response_seconds)}\n"
            f"Your message: {event.trigger_burst_end.strftime('%A, %H:%M')}\n"
            f"Their response: {event.response_burst_start.strftime('%A, %H:%M')}"
        )
        return _reply(text)

    if intent == "longest_delay":
        event = db.query(ResponseEvent).filter_by(response_role="other").order_by(ResponseEvent.response_seconds.desc()).first()
        if event is None:
            return _reply("No response events recorded yet — run the analysis step first.")
        text = (
            f"Longest observed response delay: {format_duration(event.response_seconds)}\n"
            f"Your message: {event.trigger_burst_end.strftime('%A, %H:%M')}\n"
            f"Their response: {event.response_burst_start.strftime('%A, %H:%M')}\n\n"
            "This is the longest observed delay in the imported history. "
            "The system cannot determine whether the delay was intentional."
        )
        return _reply(text)

    if intent == "longest_session":
        s = db.query(ConversationSession).order_by(ConversationSession.duration_seconds.desc()).first()
        if s is None:
            return _reply("No conversation sessions recorded yet — run the analysis step first.")
        text = (
            f"Longest conversation: {s.start_ts.strftime('%A %H:%M')} -> {s.end_ts.strftime('%A %H:%M')}\n"
            f"Duration: {format_duration(s.duration_seconds)}\n"
            f"Messages: {s.message_count} ({s.me_count} from you, {s.other_count} from {other_name})"
        )
        return _reply(text)

    if intent == "best_day":
        rows = response_stats_by_weekday(db, "other", cfg.min_sample_size)
        sufficient = [r for r in rows if r.get("sufficient_data")]
        if not sufficient:
            return _reply("Not enough response data yet to compare weekdays reliably.")
        best = min(sufficient, key=lambda r: r["median_seconds"])
        text = (
            f"Historically, {best['name']} has the fastest median response time from {other_name}: "
            f"{format_duration(best['median_seconds'])} (n={best['sample_size']}, confidence: {best['confidence']})."
        )
        return _reply(text)

    if intent == "recent_activity":
        df = statistics.messages_dataframe(db)
        if df.empty:
            return _reply("No data imported yet.")
        last_month = df["date"].max().to_period("M")
        sub = df[df["date"].dt.to_period("M") == last_month]
        other_count = int((sub["role"] == "other").sum())
        text = f"In {last_month}, {other_name} sent {other_count} messages ({len(sub)} total in the conversation)."
        return _reply(text)

    overview = statistics.compute_overview(db)
    text = (
        f"Total messages: {overview.total_messages} "
        f"({overview.me_messages} from you, {overview.other_messages} from {other_name}).\n"
        f"Conversation period: {overview.first_message_date} -> {overview.last_message_date}.\n"
        "Try asking about the fastest/longest response, the longest conversation, "
        "the best day for quick replies, or when they're usually most active."
    )
    return _reply(text)


def _reply(text: str) -> dict:
    return {"answer": text}
