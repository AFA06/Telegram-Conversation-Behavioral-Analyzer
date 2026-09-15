"""Timestamp handling.

Telegram Desktop's JSON export writes each message's wall-clock time in
whatever timezone the exporting device had at the time (``date``), which is
ambiguous. Modern exports also include ``date_unixtime``, an unambiguous
UTC epoch — we always prefer that when present. Local display time is then
derived from the *user-selected* timezone (default ``Asia/Tashkent``),
never guessed from the export itself.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo


def parse_export_timestamp(date_str: str | None, date_unixtime: str | int | None) -> tuple[dt.datetime | None, bool]:
    """Return (timestamp_utc, was_assumed) for a raw Telegram message.

    ``was_assumed`` is True when we had to fall back to parsing the naive
    ``date`` string and treat it as UTC, which is flagged in the data
    quality report rather than silently trusted.
    """
    if date_unixtime not in (None, "", "0"):
        try:
            epoch = int(date_unixtime)
            return dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc), False
        except (TypeError, ValueError):
            pass

    if date_str:
        try:
            naive = dt.datetime.fromisoformat(date_str)
            return naive.replace(tzinfo=dt.timezone.utc), True
        except ValueError:
            return None, True

    return None, True


def to_local(timestamp_utc: dt.datetime, timezone_name: str) -> dt.datetime:
    return timestamp_utc.astimezone(ZoneInfo(timezone_name))


def weekday_name(weekday_index: int) -> str:
    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return names[weekday_index]


def is_reasonable_timestamp(timestamp_utc: dt.datetime) -> bool:
    """Telegram launched in 2013; reject obviously broken dates."""
    lower_bound = dt.datetime(2013, 1, 1, tzinfo=dt.timezone.utc)
    upper_bound = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)
    return lower_bound <= timestamp_utc <= upper_bound
