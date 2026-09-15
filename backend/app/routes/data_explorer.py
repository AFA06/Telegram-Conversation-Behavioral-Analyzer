from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ConversationSession, Message, ResponseEvent
from app.services import config_service
from app.services.config_service import role_for_sender
from app.utils.formatting import format_duration

router = APIRouter()


@router.get("")
def browse_messages(
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    sender: str | None = Query(None, pattern="^(me|other)$"),
    weekday: int | None = Query(None, ge=0, le=6),
    hour: int | None = Query(None, ge=0, le=23),
    message_type: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    """Section 30: browse raw messages with filters."""
    cfg = config_service.get_or_create_config(db)
    q = db.query(Message)

    if date_from:
        q = q.filter(Message.date >= date_from)
    if date_to:
        q = q.filter(Message.date <= date_to)
    if weekday is not None:
        q = q.filter(Message.weekday == weekday)
    if hour is not None:
        q = q.filter(Message.hour == hour)
    if message_type:
        q = q.filter(Message.message_type == message_type)
    if sender:
        sender_id = cfg.me_user_id if sender == "me" else cfg.other_user_id
        q = q.filter(Message.sender_id == sender_id)

    total = q.count()
    rows = q.order_by(Message.timestamp_utc.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "items": [
            {
                "id": m.id,
                "sender_id": m.sender_id,
                "sender_role": role_for_sender(cfg, m.sender_id),
                "sender_name": m.sender_name,
                "timestamp_local": m.timestamp_local.isoformat(),
                "weekday": m.weekday,
                "hour": m.hour,
                "message_type": m.message_type,
                "text": m.text,
                "text_length": m.text_length,
            }
            for m in rows
        ],
    }


@router.get("/response-events/{event_id}")
def response_event_detail(event_id: int, db: Session = Depends(get_db)) -> dict:
    """Section 30: clicking a response event shows both messages, the
    delay, and which conversation session it belongs to.
    """
    event = db.get(ResponseEvent, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Response event not found")

    trigger_msg = db.get(Message, event.trigger_last_message_id)
    response_msg = db.get(Message, event.response_first_message_id)
    session = db.get(ConversationSession, event.session_id) if event.session_id else None

    return {
        "id": event.id,
        "trigger_role": event.trigger_role,
        "response_role": event.response_role,
        "trigger_message": {
            "id": trigger_msg.id,
            "timestamp_local": trigger_msg.timestamp_local.isoformat(),
            "text": trigger_msg.text,
        }
        if trigger_msg
        else None,
        "response_message": {
            "id": response_msg.id,
            "timestamp_local": response_msg.timestamp_local.isoformat(),
            "text": response_msg.text,
        }
        if response_msg
        else None,
        "response_seconds": event.response_seconds,
        "response_formatted": format_duration(event.response_seconds),
        "session_id": session.id if session else None,
    }
