from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.deps import get_current_db
from app.models import ResponseEvent, UnansweredBurst
from app.services import config_service
from app.services.response_analyzer import (
    best_response_windows,
    response_distribution,
    response_percentiles,
    response_stats_by_hour,
    response_stats_by_weekday,
)
from app.services import activity_analyzer
from app.services.statistics import messages_dataframe
from app.utils.formatting import format_duration

router = APIRouter()

RoleParam = Query("other", pattern="^(me|other)$")


def _events(db: Session, role: str) -> list[ResponseEvent]:
    return db.query(ResponseEvent).filter_by(response_role=role).all()


@router.get("/summary")
def summary(role: str = RoleParam, db: Session = Depends(get_current_db)) -> dict:
    """Section 13-14, 25: percentiles + the response-time histogram."""
    secs = [e.response_seconds for e in _events(db, role)]
    stats = response_percentiles(secs)
    if stats:
        stats = {**stats, **{f"{k}_formatted": format_duration(v) for k, v in stats.items() if k.endswith("_seconds")}}
    return {"stats": stats, "distribution": response_distribution(secs)}


@router.get("/fastest")
def fastest(role: str = RoleParam, limit: int = Query(10, ge=1, le=100), db: Session = Depends(get_current_db)) -> list[dict]:
    events = (
        db.query(ResponseEvent)
        .filter_by(response_role=role)
        .order_by(ResponseEvent.response_seconds.asc())
        .limit(limit)
        .all()
    )
    return [_event_out(e) for e in events]


@router.get("/longest")
def longest(role: str = RoleParam, limit: int = Query(20, ge=1, le=200), db: Session = Depends(get_current_db)) -> list[dict]:
    """Section 14: 'Longest observed response delays' — deliberately not
    called 'ignored' anywhere, since the data can't prove intent.
    """
    events = (
        db.query(ResponseEvent)
        .filter_by(response_role=role)
        .order_by(ResponseEvent.response_seconds.desc())
        .limit(limit)
        .all()
    )
    return [_event_out(e) for e in events]


def _event_out(e: ResponseEvent) -> dict:
    return {
        "id": e.id,
        "session_id": e.session_id,
        "trigger_role": e.trigger_role,
        "response_role": e.response_role,
        "trigger_burst_start": e.trigger_burst_start.isoformat(),
        "trigger_burst_end": e.trigger_burst_end.isoformat(),
        "response_burst_start": e.response_burst_start.isoformat(),
        "response_seconds": e.response_seconds,
        "response_formatted": format_duration(e.response_seconds),
        "weekday": e.weekday,
        "hour": e.hour,
    }


@router.get("/by-weekday")
def by_weekday(role: str = RoleParam, db: Session = Depends(get_current_db)) -> list[dict]:
    """Section 23."""
    cfg = config_service.get_or_create_config(db)
    return response_stats_by_weekday(db, role, cfg.min_sample_size)


@router.get("/by-hour")
def by_hour(role: str = RoleParam, db: Session = Depends(get_current_db)) -> list[dict]:
    """Section 24."""
    cfg = config_service.get_or_create_config(db)
    return response_stats_by_hour(db, role, cfg.min_sample_size)


@router.get("/best-windows")
def best_windows(
    role: str = RoleParam,
    window_hours: int = Query(3, ge=1, le=12),
    top_n: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_current_db),
) -> list[dict]:
    """Section 18: fastest *observed* response windows, gated by min sample size."""
    cfg = config_service.get_or_create_config(db)
    return best_response_windows(db, role, cfg.min_sample_size, window_hours, top_n)


@router.get("/historically-responsive")
def historically_responsive(top_n: int = Query(5, ge=1, le=20), db: Session = Depends(get_current_db)) -> dict:
    """Section 20: 'Historically Responsive Windows' — ranks (weekday,
    window) buckets using BOTH message volume and response speed, always
    gated by the configured minimum sample size. Explicitly framed as
    historical pattern, not availability or intent.
    """
    cfg = config_service.get_or_create_config(db)
    window_hours = 3
    speed_windows = best_response_windows(db, "other", cfg.min_sample_size, window_hours, top_n=50)
    if not speed_windows:
        return {
            "note": "Insufficient data to estimate historically responsive windows.",
            "windows": [],
        }

    df = messages_dataframe(db)
    volume_lookup = activity_analyzer.fixed_window_volume(df, role="other", window_hours=window_hours)

    max_count = max((w["sample_size"] for w in speed_windows), default=1)
    min_median = min((w["median_seconds"] for w in speed_windows), default=1)

    scored = []
    for w in speed_windows:
        start_hour = int(w["start_label"].split(":")[0])
        volume = volume_lookup.get((w["weekday"], start_hour), 0)
        speed_score = min_median / w["median_seconds"] if w["median_seconds"] else 0
        volume_score = w["sample_size"] / max_count if max_count else 0
        composite = 0.5 * speed_score + 0.5 * volume_score
        scored.append({**w, "message_volume": volume, "composite_score": round(composite, 3)})

    scored.sort(key=lambda w: w["composite_score"], reverse=True)
    return {
        "note": (
            "Based on historical conversations, these are the windows where the other "
            "person has most often been active and responded relatively quickly. "
            "This describes past patterns, not guaranteed availability."
        ),
        "windows": scored[:top_n],
    }


@router.get("/unanswered")
def unanswered(
    role: str = Query("me", pattern="^(me|other)$"),
    classification: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_current_db),
) -> dict:
    """Section 15: messages without a subsequent response, bucketed by
    likely explanation. Never labeled as intentional ignoring.
    """
    q = db.query(UnansweredBurst).filter_by(sender_role=role)
    if classification:
        q = q.filter_by(classification=classification)
    total = q.count()
    rows = q.order_by(UnansweredBurst.burst_end.desc()).limit(limit).all()

    by_classification = {}
    for row in db.query(UnansweredBurst).filter_by(sender_role=role).all():
        by_classification[row.classification] = by_classification.get(row.classification, 0) + 1

    return {
        "total": total,
        "by_classification": by_classification,
        "explanation": (
            "A message without a later reply can happen for many reasons: the "
            "conversation ended naturally, the topic changed, the export window "
            "ended, or the message simply wasn't the kind that expects a reply. "
            "This cannot indicate intentional ignoring."
        ),
        "items": [
            {
                "id": r.id,
                "session_id": r.session_id,
                "burst_start": r.burst_start.isoformat(),
                "burst_end": r.burst_end.isoformat(),
                "message_count": r.message_count,
                "classification": r.classification,
                "hours_since": r.hours_since,
            }
            for r in rows
        ],
    }
