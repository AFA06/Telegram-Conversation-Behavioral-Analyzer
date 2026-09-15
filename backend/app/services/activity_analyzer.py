"""Hour-of-day / weekday / heatmap / recurring-activity-window analysis
(spec sections 7-10).

All "top windows" here describe *recurring* weekday+time-of-day patterns
aggregated across the whole imported history (e.g. "Saturday 20:00-23:00"),
not single calendar-date events — this is what makes them useful as
"historically active" windows rather than one-off spikes.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _filter_role(df: pd.DataFrame, role: str) -> pd.DataFrame:
    if role == "both":
        return df
    return df[df["role"] == role]


def hourly_activity(df: pd.DataFrame, role: str = "both") -> list[dict]:
    sub = _filter_role(df, role)
    counts = sub.groupby("hour").size().reindex(range(24), fill_value=0)
    total = int(counts.sum())
    return [
        {
            "hour": h,
            "label": f"{h:02d}:00-{h:02d}:59",
            "count": int(counts[h]),
            "percentage": round(100 * counts[h] / total, 2) if total else 0.0,
        }
        for h in range(24)
    ]


def weekday_activity(df: pd.DataFrame, role: str = "both") -> list[dict]:
    sub = _filter_role(df, role)
    counts = sub.groupby("weekday").size().reindex(range(7), fill_value=0)
    total = int(counts.sum())
    return [
        {
            "weekday": d,
            "name": WEEKDAY_NAMES[d],
            "count": int(counts[d]),
            "percentage": round(100 * counts[d] / total, 2) if total else 0.0,
        }
        for d in range(7)
    ]


def heatmap(df: pd.DataFrame, role: str = "both") -> dict:
    sub = _filter_role(df, role)
    pivot = sub.pivot_table(index="weekday", columns="hour", values="id", aggfunc="count", fill_value=0)
    pivot = pivot.reindex(index=range(7), columns=range(24), fill_value=0)
    grid = pivot.values.astype(int).tolist()
    return {
        "weekdays": WEEKDAY_NAMES,
        "hours": list(range(24)),
        "grid": grid,  # grid[weekday][hour] = message count
        "max_count": int(pivot.values.max()) if pivot.size else 0,
    }


def daily_activity(df: pd.DataFrame, year: int, month: int) -> list[dict]:
    """Per-day message counts for a given month (used by the Calendar page)."""
    if df.empty:
        return []
    sub = df[(df["year"] == year) & (df["month"] == month)]
    counts = sub.groupby(["day", "role"]).size().unstack(fill_value=0)
    import calendar

    days_in_month = calendar.monthrange(year, month)[1]
    result = []
    for day in range(1, days_in_month + 1):
        me = int(counts.loc[day, "me"]) if day in counts.index and "me" in counts.columns else 0
        other = int(counts.loc[day, "other"]) if day in counts.index and "other" in counts.columns else 0
        result.append({"day": day, "me_count": me, "other_count": other, "total": me + other})
    return result


def top_activity_windows(
    df: pd.DataFrame,
    role: str = "both",
    window_minutes: int = 60,
    top_n: int = 5,
) -> list[dict]:
    """Ranks recurring (weekday, start_time) windows by total historical
    message volume, using a sliding search with a 15-minute step and greedy
    non-overlapping selection per weekday so results aren't dominated by
    near-duplicate overlapping windows.
    """
    sub = _filter_role(df, role)
    if sub.empty:
        return []

    sub = sub.copy()
    sub["minute_of_day"] = sub["hour"] * 60 + sub["minute"]

    day_minute_counts = np.zeros((7, 1440), dtype=int)
    grouped = sub.groupby(["weekday", "minute_of_day"]).size()
    for (weekday, minute), count in grouped.items():
        day_minute_counts[int(weekday), int(minute)] = count

    step = min(30, window_minutes)
    candidates: list[tuple[int, int, int]] = []  # (count, weekday, start_minute)

    for weekday in range(7):
        cumsum = np.concatenate([[0], np.cumsum(day_minute_counts[weekday])])
        for start in range(0, 1440 - window_minutes + 1, step):
            end = start + window_minutes
            count = int(cumsum[end] - cumsum[start])
            if count > 0:
                candidates.append((count, weekday, start))

    candidates.sort(key=lambda c: c[0], reverse=True)

    selected: list[dict] = []
    taken_ranges: dict[int, list[tuple[int, int]]] = {d: [] for d in range(7)}

    for count, weekday, start in candidates:
        end = start + window_minutes
        if any(not (end <= s or start >= e) for s, e in taken_ranges[weekday]):
            continue
        taken_ranges[weekday].append((start, end))
        selected.append(
            {
                "weekday": weekday,
                "weekday_name": WEEKDAY_NAMES[weekday],
                "start_label": f"{start // 60:02d}:{start % 60:02d}",
                "end_label": f"{(end // 60) % 24:02d}:{end % 60:02d}",
                "message_count": count,
                "window_minutes": window_minutes,
            }
        )
        if len(selected) >= top_n:
            break

    return selected
