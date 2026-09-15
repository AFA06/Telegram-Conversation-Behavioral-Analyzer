from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ConversationSession, Message
from app.utils.formatting import format_duration

router = APIRouter()


def _session_out(s: ConversationSession) -> dict:
    return {
        "id": s.id,
        "start_ts": s.start_ts.isoformat(),
        "end_ts": s.end_ts.isoformat(),
        "duration_seconds": s.duration_seconds,
        "duration_formatted": format_duration(s.duration_seconds),
        "message_count": s.message_count,
        "me_count": s.me_count,
        "other_count": s.other_count,
    }


@router.get("")
def list_sessions(
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    """Section 16: paginated session list, most recent first."""
    total = db.query(ConversationSession).count()
    rows = (
        db.query(ConversationSession)
        .order_by(ConversationSession.start_ts.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"total": total, "items": [_session_out(s) for s in rows]}


@router.get("/summary")
def sessions_summary(db: Session = Depends(get_db)) -> dict:
    """Section 16: session-level aggregate stats."""
    rows = db.query(ConversationSession).all()
    if not rows:
        return {"count": 0}

    durations = sorted(s.duration_seconds for s in rows)
    counts = [s.message_count for s in rows]
    mid = len(durations) // 2
    median_duration = durations[mid] if len(durations) % 2 else (durations[mid - 1] + durations[mid]) / 2

    return {
        "count": len(rows),
        "average_duration_seconds": sum(durations) / len(durations),
        "median_duration_seconds": median_duration,
        "longest_duration_seconds": durations[-1],
        "average_messages_per_session": round(sum(counts) / len(counts), 1),
    }


@router.get("/longest")
def longest_sessions(
    by: str = Query("duration", pattern="^(duration|messages)$"),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Section 17."""
    order_col = ConversationSession.duration_seconds if by == "duration" else ConversationSession.message_count
    rows = db.query(ConversationSession).order_by(order_col.desc()).limit(limit).all()
    return [_session_out(s) for s in rows]


@router.get("/{session_id}")
def session_detail(session_id: int, db: Session = Depends(get_db)) -> dict:
    s = db.get(ConversationSession, session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = (
        db.query(Message)
        .filter(Message.timestamp_utc >= s.start_ts, Message.timestamp_utc <= s.end_ts)
        .order_by(Message.timestamp_utc)
        .all()
    )
    return {
        **_session_out(s),
        "messages": [
            {
                "id": m.id,
                "sender_id": m.sender_id,
                "sender_name": m.sender_name,
                "timestamp_local": m.timestamp_local.isoformat(),
                "message_type": m.message_type,
                "text": m.text,
            }
            for m in messages
        ],
    }
