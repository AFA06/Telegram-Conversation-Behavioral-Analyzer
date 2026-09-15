from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.deps import get_current_db
from app.models import ConversationSession
from app.services.response_analyzer import response_events_dataframe
from app.services.statistics import messages_dataframe

router = APIRouter()


@router.get("/monthly")
def monthly_trends(db: Session = Depends(get_current_db)) -> list[dict]:
    """Section 21."""
    msgs = messages_dataframe(db)
    if msgs.empty:
        return []
    msgs["month"] = msgs["date"].dt.to_period("M")

    resp = response_events_dataframe(db, "other")
    if not resp.empty:
        resp["month"] = pd.to_datetime(resp["trigger_burst_end"]).dt.to_period("M")

    sessions = pd.read_sql("SELECT start_ts, duration_seconds FROM conversation_sessions", db.bind)
    if not sessions.empty:
        sessions["month"] = pd.to_datetime(sessions["start_ts"]).dt.to_period("M")

    months = sorted(msgs["month"].unique())
    result = []
    for month in months:
        m_msgs = msgs[msgs["month"] == month]
        m_resp = resp[resp["month"] == month] if not resp.empty else pd.DataFrame()
        m_sessions = sessions[sessions["month"] == month] if not sessions.empty else pd.DataFrame()

        result.append(
            {
                "month": str(month),
                "total_messages": int(len(m_msgs)),
                "other_messages": int((m_msgs["role"] == "other").sum()),
                "me_messages": int((m_msgs["role"] == "me").sum()),
                "average_response_seconds": float(m_resp["response_seconds"].mean()) if not m_resp.empty else None,
                "median_response_seconds": float(m_resp["response_seconds"].median()) if not m_resp.empty else None,
                "response_sample_size": int(len(m_resp)),
                "session_count": int(len(m_sessions)),
                "average_session_seconds": float(m_sessions["duration_seconds"].mean()) if not m_sessions.empty else None,
            }
        )
    return result


@router.get("/compare")
def compare_periods(n_months: int = Query(3, ge=1, le=24), db: Session = Depends(get_current_db)) -> dict:
    """Section 22: first N months vs. last N months, using neutral
    percentage-change language only — no psychological interpretation.
    """
    msgs = messages_dataframe(db)
    if msgs.empty:
        return {"note": "No data imported yet."}
    msgs["month"] = msgs["date"].dt.to_period("M")
    months = sorted(msgs["month"].unique())

    if len(months) < 2 * n_months:
        return {
            "note": f"Not enough distinct months ({len(months)}) to compare {n_months} vs {n_months}.",
        }

    first_months = set(months[:n_months])
    last_months = set(months[-n_months:])

    resp = response_events_dataframe(db, "other")
    if not resp.empty:
        resp["month"] = pd.to_datetime(resp["trigger_burst_end"]).dt.to_period("M")

    def period_stats(month_set: set) -> dict:
        sub = msgs[msgs["month"].isin(month_set)]
        r_sub = resp[resp["month"].isin(month_set)] if not resp.empty else pd.DataFrame()
        return {
            "months": sorted(str(m) for m in month_set),
            "total_messages": int(len(sub)),
            "active_days": int(sub["date"].dt.date.nunique()),
            "median_response_seconds": float(r_sub["response_seconds"].median()) if not r_sub.empty else None,
            "response_sample_size": int(len(r_sub)),
        }

    first = period_stats(first_months)
    last = period_stats(last_months)

    def pct_change(a: float | None, b: float | None) -> float | None:
        if a in (None, 0) or b is None:
            return None
        return round(100 * (b - a) / a, 1)

    return {
        "first_period": first,
        "last_period": last,
        "message_frequency_change_percent": pct_change(first["total_messages"], last["total_messages"]),
        "median_response_change_percent": pct_change(first["median_response_seconds"], last["median_response_seconds"]),
        "note": "Percentage changes describe observed message and response patterns only.",
    }
