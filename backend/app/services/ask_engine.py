"""Rule-based natural-language question answering for the /ask bot command
(spec sections 33-35).

Deliberately NOT an LLM call: this matches keywords in the question to one
of a fixed set of canonical queries against the already-computed local
statistics, then fills a template with the real numbers. No message content
or question text ever leaves the machine. If a future version wants true
LLM-based phrasing, it must only ever be handed these aggregated numbers —
never the raw conversation — and only when the user explicitly opts in.

Supports English and Uzbek questions/answers (``lang="en"|"uz"``) — keyword
matching checks both languages' phrasings regardless of the target reply
language, so a Uzbek-speaking user gets a sensible match even if they throw
in an English word, and vice versa.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import ConversationSession, ResponseEvent
from app.services import activity_analyzer, config_service, statistics
from app.services.response_analyzer import response_stats_by_weekday
from app.utils.formatting import format_duration

_KEYWORD_HANDLERS: list[tuple[tuple[str, ...], str]] = [
    (
        ("most active", "usually active", "when is she", "when is he", "when active", "eng faol", "qachon faol"),
        "most_active",
    ),
    (("fastest", "eng tez"), "fastest"),
    (("longest", "slowest", "eng uzoq", "eng sekin"), "longest_delay"),
    (("longest conversation", "longest session", "eng uzoq suhbat"), "longest_session"),
    (("best day", "which day", "eng yaxshi kun", "qaysi kun"), "best_day"),
    (("last month", "this month", "o'tgan oy", "bu oy", "otgan oy"), "recent_activity"),
    (("how active", "qanchalik faol"), "recent_activity"),
]

_STRINGS: dict[str, dict[str, str]] = {
    "not_enough_activity": {
        "en": "Not enough data yet to estimate activity windows.",
        "uz": "Faollik oynalarini baholash uchun hozircha yetarli ma'lumot yo'q.",
    },
    "most_active": {
        "en": (
            "Historically, {other_name}'s highest message activity is:\n{lines}\n\n"
            "These are based on {total} messages across {sessions} conversation sessions.\n"
            "This indicates historical activity, not guaranteed availability."
        ),
        "uz": (
            "Tarixan, {other_name}ning eng yuqori xabar faolligi:\n{lines}\n\n"
            "Bu ma'lumotlar {total} ta xabar va {sessions} ta suhbat sessiyasiga asoslangan.\n"
            "Bu tarixiy faollikni bildiradi, mavjudlikning kafolati emas."
        ),
    },
    "no_response_events": {
        "en": "No response events recorded yet — run the analysis step first.",
        "uz": "Hali javob hodisalari qayd etilmagan — avval tahlil bosqichini bajaring.",
    },
    "fastest": {
        "en": (
            "Fastest observed reply from {other_name}: {duration}\n"
            "Your message: {trigger_time}\n"
            "Their response: {response_time}"
        ),
        "uz": (
            "{other_name}dan kuzatilgan eng tez javob: {duration}\n"
            "Sizning xabaringiz: {trigger_time}\n"
            "Ularning javobi: {response_time}"
        ),
    },
    "longest_delay": {
        "en": (
            "Longest observed response delay: {duration}\n"
            "Your message: {trigger_time}\n"
            "Their response: {response_time}\n\n"
            "This is the longest observed delay in the imported history. "
            "The system cannot determine whether the delay was intentional."
        ),
        "uz": (
            "Kuzatilgan eng uzoq javob kechikishi: {duration}\n"
            "Sizning xabaringiz: {trigger_time}\n"
            "Ularning javobi: {response_time}\n\n"
            "Bu import qilingan tarixdagi eng uzoq kuzatilgan kechikish. "
            "Tizim bu kechikish ataylab bo'lganligini aniqlay olmaydi."
        ),
    },
    "no_sessions": {
        "en": "No conversation sessions recorded yet — run the analysis step first.",
        "uz": "Hali suhbat sessiyalari qayd etilmagan — avval tahlil bosqichini bajaring.",
    },
    "longest_session": {
        "en": (
            "Longest conversation: {start} -> {end}\n"
            "Duration: {duration}\n"
            "Messages: {count} ({me_count} from you, {other_count} from {other_name})"
        ),
        "uz": (
            "Eng uzoq suhbat: {start} -> {end}\n"
            "Davomiyligi: {duration}\n"
            "Xabarlar: {count} (sizdan {me_count}, {other_name}dan {other_count})"
        ),
    },
    "not_enough_weekday_data": {
        "en": "Not enough response data yet to compare weekdays reliably.",
        "uz": "Hafta kunlarini ishonchli taqqoslash uchun hozircha yetarli javob ma'lumoti yo'q.",
    },
    "best_day": {
        "en": (
            "Historically, {day} has the fastest median response time from {other_name}: "
            "{duration} (n={n}, confidence: {confidence})."
        ),
        "uz": (
            "Tarixan, {other_name}dan eng tez mediana javob vaqti {day} kuniga to'g'ri keladi: "
            "{duration} (n={n}, ishonch darajasi: {confidence})."
        ),
    },
    "no_data": {
        "en": "No data imported yet.",
        "uz": "Hali hech qanday ma'lumot import qilinmagan.",
    },
    "recent_activity": {
        "en": "In {month}, {other_name} sent {count} messages ({total} total in the conversation).",
        "uz": "{month} oyida {other_name} {count} ta xabar yubordi (suhbatda jami {total} ta).",
    },
    "overview_fallback": {
        "en": (
            "Total messages: {total} ({me_count} from you, {other_count} from {other_name}).\n"
            "Conversation period: {first} -> {last}.\n"
            "Try asking about the fastest/longest response, the longest conversation, "
            "the best day for quick replies, or when they're usually most active."
        ),
        "uz": (
            "Jami xabarlar: {total} (sizdan {me_count}, {other_name}dan {other_count}).\n"
            "Suhbat davri: {first} -> {last}.\n"
            "Eng tez/uzoq javob, eng uzoq suhbat, tez javoblar uchun eng yaxshi kun, "
            "yoki ular odatda qachon eng faol bo'lishi haqida so'rab ko'ring."
        ),
    },
    "other_person_default": {
        "en": "The other person",
        "uz": "Suhbatdosh",
    },
}


def _s(lang: str, key: str, **kwargs) -> str:
    template = _STRINGS.get(key, {}).get(lang) or _STRINGS.get(key, {}).get("en", key)
    return template.format(**kwargs) if kwargs else template


def _match_intent(question: str) -> str:
    q = question.lower()
    if ("conversation" in q or "suhbat" in q) and ("longest" in q or "biggest" in q or "eng uzoq" in q or "eng katta" in q):
        return "longest_session"
    for keywords, intent in _KEYWORD_HANDLERS:
        if any(k in q for k in keywords):
            return intent
    return "overview"


def _fmt_dt(dt_value, lang: str) -> str:
    # strftime weekday/month names are locale-dependent and unreliable to
    # set up portably; keep the (already-local) timestamp itself, which is
    # unambiguous in either language.
    return dt_value.strftime("%Y-%m-%d %H:%M")


def answer(db: Session, question: str, lang: str = "en") -> dict:
    lang = lang if lang in ("en", "uz") else "en"
    cfg = config_service.get_or_create_config(db)
    other_name = cfg.other_display_name or _s(lang, "other_person_default")
    intent = _match_intent(question)

    if intent == "most_active":
        df = statistics.messages_dataframe(db)
        windows = activity_analyzer.top_activity_windows(df, role="other", window_minutes=180, top_n=3)
        if not windows:
            return _reply(_s(lang, "not_enough_activity"))
        lines = "\n".join(
            f"{i+1}. {w['weekday_name']} — {w['start_label']}-{w['end_label']} ({w['message_count']} messages)"
            for i, w in enumerate(windows)
        )
        total = int(df[df["role"] == "other"].shape[0]) if not df.empty else 0
        sessions = db.query(ConversationSession).count()
        return _reply(_s(lang, "most_active", other_name=other_name, lines=lines, total=total, sessions=sessions))

    if intent == "fastest":
        event = db.query(ResponseEvent).filter_by(response_role="other").order_by(ResponseEvent.response_seconds.asc()).first()
        if event is None:
            return _reply(_s(lang, "no_response_events"))
        return _reply(
            _s(
                lang,
                "fastest",
                other_name=other_name,
                duration=format_duration(event.response_seconds),
                trigger_time=_fmt_dt(event.trigger_burst_end, lang),
                response_time=_fmt_dt(event.response_burst_start, lang),
            )
        )

    if intent == "longest_delay":
        event = db.query(ResponseEvent).filter_by(response_role="other").order_by(ResponseEvent.response_seconds.desc()).first()
        if event is None:
            return _reply(_s(lang, "no_response_events"))
        return _reply(
            _s(
                lang,
                "longest_delay",
                duration=format_duration(event.response_seconds),
                trigger_time=_fmt_dt(event.trigger_burst_end, lang),
                response_time=_fmt_dt(event.response_burst_start, lang),
            )
        )

    if intent == "longest_session":
        s = db.query(ConversationSession).order_by(ConversationSession.duration_seconds.desc()).first()
        if s is None:
            return _reply(_s(lang, "no_sessions"))
        return _reply(
            _s(
                lang,
                "longest_session",
                start=_fmt_dt(s.start_ts, lang),
                end=_fmt_dt(s.end_ts, lang),
                duration=format_duration(s.duration_seconds),
                count=s.message_count,
                me_count=s.me_count,
                other_count=s.other_count,
                other_name=other_name,
            )
        )

    if intent == "best_day":
        rows = response_stats_by_weekday(db, "other", cfg.min_sample_size)
        sufficient = [r for r in rows if r.get("sufficient_data")]
        if not sufficient:
            return _reply(_s(lang, "not_enough_weekday_data"))
        best = min(sufficient, key=lambda r: r["median_seconds"])
        return _reply(
            _s(
                lang,
                "best_day",
                day=best["name"],
                other_name=other_name,
                duration=format_duration(best["median_seconds"]),
                n=best["sample_size"],
                confidence=best["confidence"],
            )
        )

    if intent == "recent_activity":
        df = statistics.messages_dataframe(db)
        if df.empty:
            return _reply(_s(lang, "no_data"))
        last_month = df["date"].max().to_period("M")
        sub = df[df["date"].dt.to_period("M") == last_month]
        other_count = int((sub["role"] == "other").sum())
        return _reply(_s(lang, "recent_activity", month=str(last_month), other_name=other_name, count=other_count, total=len(sub)))

    overview = statistics.compute_overview(db)
    return _reply(
        _s(
            lang,
            "overview_fallback",
            total=overview.total_messages,
            me_count=overview.me_messages,
            other_count=overview.other_messages,
            other_name=other_name,
            first=overview.first_message_date,
            last=overview.last_message_date,
        )
    )


def _reply(text: str) -> dict:
    return {"answer": text}
