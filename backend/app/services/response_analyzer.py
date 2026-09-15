"""Message-burst grouping, response-time analysis, and no-response
detection (spec sections 11-15).

Core rule: consecutive messages from the *same* participant within
``grouping_window_minutes`` (default 5) are merged into one outgoing
"burst" before any response time is computed, so a burst of "Hey" / "How
are you?" / "What are you doing?" counts as a single trigger, not three.

A response event exists only between two *adjacent* bursts that belong to
different participants. If the same participant produces two bursts in a
row (they messaged again without getting a reply), the earlier burst is
recorded as an "unanswered burst" rather than fabricating a response time
for it — see section 15's "no-response messages" requirement.
"""
from __future__ import annotations

import bisect
import datetime as dt
import statistics
from dataclasses import dataclass, field

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import AppConfig, ConversationSession, Message, ResponseEvent, UnansweredBurst
from app.services.config_service import get_or_create_config, role_for_sender
from app.services.session_analyzer import SessionData, build_sessions

UNANSWERED_QUICK_FOLLOWUP_HOURS = 3.0


@dataclass
class Burst:
    role: str  # "me" | "other"
    start_ts: dt.datetime
    end_ts: dt.datetime
    message_ids: list[int] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.message_ids)


def build_bursts(messages: list[Message], roles: dict[int, str], grouping_window_minutes: float) -> list[Burst]:
    """``messages`` must be sorted by timestamp_utc. Messages with an
    'unknown' role (sender doesn't match either configured participant)
    are excluded.
    """
    window = dt.timedelta(minutes=grouping_window_minutes)
    bursts: list[Burst] = []
    current: Burst | None = None

    for msg in messages:
        role = roles.get(msg.id, "unknown")
        if role == "unknown":
            continue

        if (
            current is not None
            and current.role == role
            and msg.timestamp_utc - current.end_ts <= window
        ):
            current.end_ts = msg.timestamp_utc
            current.message_ids.append(msg.id)
            continue

        current = Burst(role=role, start_ts=msg.timestamp_utc, end_ts=msg.timestamp_utc, message_ids=[msg.id])
        bursts.append(current)

    return bursts


def _session_index_for(session_starts: list[dt.datetime], sessions: list[SessionData], ts: dt.datetime) -> int | None:
    i = bisect.bisect_right(session_starts, ts) - 1
    if 0 <= i < len(sessions) and sessions[i].start_ts <= ts <= sessions[i].end_ts:
        return i
    return None


def classify_unanswered(burst_end: dt.datetime, next_same_role_start: dt.datetime | None) -> tuple[str, float]:
    """Returns (classification, hours_since). ``hours_since`` is measured to
    the next message from the same person, or is None-equivalent (0.0) when
    this is the last burst in the whole export.
    """
    if next_same_role_start is None:
        return "no_response_before_export_ended", 0.0
    hours = (next_same_role_start - burst_end).total_seconds() / 3600
    if hours < UNANSWERED_QUICK_FOLLOWUP_HOURS:
        return "conversation_likely_ended", round(hours, 2)
    return "long_unresolved_delay", round(hours, 2)


def run_full_analysis(db: Session) -> dict:
    """Rebuilds sessions, response events, and unanswered bursts from the
    currently-imported messages. Safe to re-run after changing settings
    (grouping window, session gap, participant identities) in the Settings
    page — it always recomputes from scratch.
    """
    cfg: AppConfig = get_or_create_config(db)
    if not cfg.me_user_id or not cfg.other_user_id:
        raise ValueError("Participants are not configured yet (set 'me' and 'other' user ids first).")

    messages: list[Message] = db.query(Message).order_by(Message.timestamp_utc).all()
    roles: dict[int, str] = {m.id: role_for_sender(cfg, m.sender_id) for m in messages}

    if messages and not any(r != "unknown" for r in roles.values()):
        from app.services.config_service import detect_participants

        detected = detect_participants(db, limit=5)
        detected_str = "; ".join(f"{d['sender_name'] or '?'} ({d['sender_id']}): {d['message_count']} msgs" for d in detected)
        raise ValueError(
            "The configured 'me' and 'other' ids don't match any imported message senders "
            "(0 messages matched). Telegram exports store sender ids in a prefixed form "
            "(e.g. 'user938613594', not bare '938613594') — check GET /api/import/participants "
            "or `python -m analyzer participants` for the exact ids found in your export. "
            f"Detected senders: {detected_str or 'none'}"
        )

    db.execute(delete(ResponseEvent))
    db.execute(delete(UnansweredBurst))
    db.execute(delete(ConversationSession))
    db.commit()

    if not messages:
        return {"sessions": 0, "response_events": 0, "unanswered_bursts": 0}

    # --- sessions ---
    sessions = build_sessions(messages, roles, cfg.session_gap_hours)
    session_rows = [
        ConversationSession(
            start_ts=s.start_ts,
            end_ts=s.end_ts,
            duration_seconds=s.duration_seconds,
            message_count=s.message_count,
            me_count=s.me_count,
            other_count=s.other_count,
        )
        for s in sessions
    ]
    db.add_all(session_rows)
    db.commit()
    for row in session_rows:
        db.refresh(row)
    session_starts = [s.start_ts for s in sessions]

    # --- bursts -> response events + unanswered bursts ---
    bursts = build_bursts(messages, roles, cfg.grouping_window_minutes)

    response_rows: list[ResponseEvent] = []
    unanswered_rows: list[UnansweredBurst] = []

    for i, burst in enumerate(bursts):
        session_idx = _session_index_for(session_starts, sessions, burst.start_ts)
        session_id = session_rows[session_idx].id if session_idx is not None else None

        next_burst = bursts[i + 1] if i + 1 < len(bursts) else None

        if next_burst is not None and next_burst.role != burst.role:
            response_seconds = (next_burst.start_ts - burst.end_ts).total_seconds()
            if response_seconds < 0:
                continue  # defensive: should not happen with sorted input
            response_rows.append(
                ResponseEvent(
                    session_id=session_id,
                    trigger_role=burst.role,
                    response_role=next_burst.role,
                    trigger_burst_start=burst.start_ts,
                    trigger_burst_end=burst.end_ts,
                    trigger_message_count=burst.count,
                    trigger_first_message_id=burst.message_ids[0],
                    trigger_last_message_id=burst.message_ids[-1],
                    response_burst_start=next_burst.start_ts,
                    response_first_message_id=next_burst.message_ids[0],
                    response_seconds=response_seconds,
                    weekday=burst.end_ts.weekday(),
                    hour=burst.end_ts.hour,
                )
            )
        else:
            # find the next burst from the SAME role (may be further ahead
            # than i+1 if next_burst was None, i.e. this IS the last burst)
            next_same_role_start = next_burst.start_ts if next_burst is not None else None
            classification, hours_since = classify_unanswered(burst.end_ts, next_same_role_start)
            unanswered_rows.append(
                UnansweredBurst(
                    session_id=session_id,
                    sender_role=burst.role,
                    burst_start=burst.start_ts,
                    burst_end=burst.end_ts,
                    message_count=burst.count,
                    first_message_id=burst.message_ids[0],
                    last_message_id=burst.message_ids[-1],
                    classification=classification,
                    hours_since=hours_since,
                )
            )

    db.add_all(response_rows)
    db.add_all(unanswered_rows)
    db.commit()

    return {
        "sessions": len(session_rows),
        "response_events": len(response_rows),
        "unanswered_bursts": len(unanswered_rows),
    }


# --- read-side aggregate helpers (used by the API routes) ---


def response_percentiles(seconds_list: list[float]) -> dict:
    if not seconds_list:
        return {}
    s = sorted(seconds_list)
    return {
        "count": len(s),
        "fastest_seconds": s[0],
        "slowest_seconds": s[-1],
        "median_seconds": statistics.median(s),
        "average_seconds": statistics.mean(s),
        "p25_seconds": statistics.quantiles(s, n=4)[0] if len(s) >= 4 else s[0],
        "p75_seconds": statistics.quantiles(s, n=4)[2] if len(s) >= 4 else s[-1],
        "p90_seconds": statistics.quantiles(s, n=10)[8] if len(s) >= 10 else s[-1],
    }


DISTRIBUTION_BUCKETS = [
    ("< 1 minute", 0, 60),
    ("1-5 minutes", 60, 5 * 60),
    ("5-15 minutes", 5 * 60, 15 * 60),
    ("15-30 minutes", 15 * 60, 30 * 60),
    ("30-60 minutes", 30 * 60, 60 * 60),
    ("1-3 hours", 60 * 60, 3 * 3600),
    ("3-6 hours", 3 * 3600, 6 * 3600),
    ("6-12 hours", 6 * 3600, 12 * 3600),
    ("12-24 hours", 12 * 3600, 24 * 3600),
    ("24h+", 24 * 3600, float("inf")),
]


def response_distribution(seconds_list: list[float]) -> list[dict]:
    total = len(seconds_list)
    result = []
    for label, lo, hi in DISTRIBUTION_BUCKETS:
        count = sum(1 for s in seconds_list if lo <= s < hi)
        result.append(
            {
                "bucket": label,
                "count": count,
                "percentage": round(100 * count / total, 2) if total else 0.0,
            }
        )
    return result


def _events_for_role(db: Session, response_role: str) -> list[ResponseEvent]:
    return (
        db.query(ResponseEvent)
        .filter(ResponseEvent.response_role == response_role)
        .all()
    )


def response_events_dataframe(db: Session, response_role: str):
    import pandas as pd

    events = _events_for_role(db, response_role)
    if not events:
        return pd.DataFrame(columns=["trigger_burst_end", "response_seconds"])
    return pd.DataFrame(
        {
            "trigger_burst_end": [e.trigger_burst_end for e in events],
            "response_seconds": [e.response_seconds for e in events],
        }
    )


def response_stats_by_weekday(db: Session, response_role: str, min_sample_size: int) -> list[dict]:
    from app.services.activity_analyzer import WEEKDAY_NAMES
    from app.utils.formatting import confidence_label

    events = _events_for_role(db, response_role)
    by_day: dict[int, list[float]] = {d: [] for d in range(7)}
    for e in events:
        by_day[e.weekday].append(e.response_seconds)

    result = []
    for d in range(7):
        secs = by_day[d]
        if len(secs) < min_sample_size:
            result.append({"weekday": d, "name": WEEKDAY_NAMES[d], "sample_size": len(secs), "sufficient_data": False})
            continue
        stats = response_percentiles(secs)
        result.append(
            {
                "weekday": d,
                "name": WEEKDAY_NAMES[d],
                "sample_size": len(secs),
                "sufficient_data": True,
                "median_seconds": stats["median_seconds"],
                "average_seconds": stats["average_seconds"],
                "fastest_seconds": stats["fastest_seconds"],
                "slowest_seconds": stats["slowest_seconds"],
                "confidence": confidence_label(len(secs)),
            }
        )
    return result


def response_stats_by_hour(db: Session, response_role: str, min_sample_size: int) -> list[dict]:
    from app.utils.formatting import confidence_label

    events = _events_for_role(db, response_role)
    by_hour: dict[int, list[float]] = {h: [] for h in range(24)}
    for e in events:
        by_hour[e.hour].append(e.response_seconds)

    result = []
    for h in range(24):
        secs = by_hour[h]
        if len(secs) < min_sample_size:
            result.append({"hour": h, "sample_size": len(secs), "sufficient_data": False})
            continue
        stats = response_percentiles(secs)
        result.append(
            {
                "hour": h,
                "sample_size": len(secs),
                "sufficient_data": True,
                "median_seconds": stats["median_seconds"],
                "average_seconds": stats["average_seconds"],
                "fastest_seconds": stats["fastest_seconds"],
                "slowest_seconds": stats["slowest_seconds"],
                "confidence": confidence_label(len(secs)),
            }
        )
    return result


def best_response_windows(
    db: Session,
    response_role: str,
    min_sample_size: int,
    window_hours: int = 3,
    top_n: int = 5,
) -> list[dict]:
    """Ranks (weekday, N-hour window) buckets by *median response speed*
    among buckets with at least ``min_sample_size`` observed response
    events. Buckets below the threshold are simply excluded rather than
    shown with a misleadingly precise median (spec section 18).
    """
    from app.services.activity_analyzer import WEEKDAY_NAMES
    from app.utils.formatting import confidence_label

    events = _events_for_role(db, response_role)
    buckets: dict[tuple[int, int], list[float]] = {}
    for e in events:
        window_start = (e.hour // window_hours) * window_hours
        key = (e.weekday, window_start)
        buckets.setdefault(key, []).append(e.response_seconds)

    ranked = []
    for (weekday, start_hour), secs in buckets.items():
        if len(secs) < min_sample_size:
            continue
        stats = response_percentiles(secs)
        ranked.append(
            {
                "weekday": weekday,
                "weekday_name": WEEKDAY_NAMES[weekday],
                "start_label": f"{start_hour:02d}:00",
                "end_label": f"{(start_hour + window_hours) % 24:02d}:00",
                "sample_size": len(secs),
                "median_seconds": stats["median_seconds"],
                "average_seconds": stats["average_seconds"],
                "confidence": confidence_label(len(secs)),
            }
        )

    ranked.sort(key=lambda r: r["median_seconds"])
    return ranked[:top_n]
