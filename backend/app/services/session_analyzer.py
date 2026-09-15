"""Conversation-session detection (spec section 16-17).

A new session starts whenever the gap since the previous message exceeds
``session_gap_hours`` (default 6h). This is independent of the smaller
message-burst grouping window used for response-time analysis.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from app.models import Message


@dataclass
class SessionData:
    start_ts: dt.datetime
    end_ts: dt.datetime
    message_count: int = 0
    me_count: int = 0
    other_count: int = 0

    @property
    def duration_seconds(self) -> float:
        return (self.end_ts - self.start_ts).total_seconds()


def build_sessions(messages: list[Message], roles: dict[int, str], session_gap_hours: float) -> list[SessionData]:
    """``messages`` must be sorted by timestamp_utc. ``roles`` maps
    Message.id -> 'me'/'other'/'unknown'.
    """
    if not messages:
        return []

    gap = dt.timedelta(hours=session_gap_hours)
    sessions: list[SessionData] = []
    current: SessionData | None = None
    prev_ts: dt.datetime | None = None

    for msg in messages:
        if current is None or (prev_ts is not None and msg.timestamp_utc - prev_ts > gap):
            current = SessionData(start_ts=msg.timestamp_utc, end_ts=msg.timestamp_utc)
            sessions.append(current)

        current.end_ts = msg.timestamp_utc
        current.message_count += 1
        role = roles.get(msg.id, "unknown")
        if role == "me":
            current.me_count += 1
        elif role == "other":
            current.other_count += 1

        prev_ts = msg.timestamp_utc

    return sessions


def find_session_index(sessions: list[SessionData], timestamp: dt.datetime) -> int | None:
    """Linear-ish lookup helper; callers should prefer bisecting on start_ts
    for large datasets (see response_analyzer for the bisect-based version).
    """
    for idx, s in enumerate(sessions):
        if s.start_ts <= timestamp <= s.end_ts:
            return idx
    return None
