"""Overview / basic statistics (spec section 6)."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AppConfig, Message
from app.services.config_service import role_for_sender


@dataclass
class OverviewStats:
    total_messages: int
    me_messages: int
    other_messages: int
    me_percentage: float
    other_percentage: float
    first_message_date: str | None
    last_message_date: str | None
    conversation_span_days: int
    active_days: int
    active_weeks: int
    active_months: int


def messages_dataframe(db: Session) -> pd.DataFrame:
    """Loads all messages as a DataFrame with a 'role' column (me/other/unknown).

    Uses a SQLAlchemy Core ``select()`` against the mapped Table rather than
    a raw SQL string: a Postgres tenant's session applies a
    ``schema_translate_map`` execution option to route queries to that
    tenant's own schema, but that rewriting only works for Core/ORM
    constructs — a bare SQL string bypasses it and would silently query the
    wrong (default) schema.
    """
    stmt = select(Message).order_by(Message.timestamp_utc)
    df = pd.read_sql(stmt, db.bind)
    if df.empty:
        return df
    df["timestamp_local"] = pd.to_datetime(df["timestamp_local"])
    df["date"] = pd.to_datetime(df["date"])

    cfg = db.get(AppConfig, 1)
    if cfg is not None:
        df["role"] = df["sender_id"].apply(lambda sid: role_for_sender(cfg, sid))
    else:
        df["role"] = "unknown"
    return df


def compute_overview(db: Session) -> OverviewStats:
    df = messages_dataframe(db)
    if df.empty:
        return OverviewStats(0, 0, 0, 0.0, 0.0, None, None, 0, 0, 0, 0)

    total = len(df)
    me = int((df["role"] == "me").sum())
    other = int((df["role"] == "other").sum())

    first_date = df["date"].min()
    last_date = df["date"].max()
    span_days = int((last_date - first_date).days) + 1

    active_days = df["date"].dt.date.nunique()
    active_weeks = df["date"].dt.to_period("W").nunique()
    active_months = df["date"].dt.to_period("M").nunique()

    return OverviewStats(
        total_messages=total,
        me_messages=me,
        other_messages=other,
        me_percentage=round(100 * me / total, 1) if total else 0.0,
        other_percentage=round(100 * other / total, 1) if total else 0.0,
        first_message_date=first_date.date().isoformat(),
        last_message_date=last_date.date().isoformat(),
        conversation_span_days=span_days,
        active_days=int(active_days),
        active_weeks=int(active_weeks),
        active_months=int(active_months),
    )
