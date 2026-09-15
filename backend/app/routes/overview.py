from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ConversationSession, ResponseEvent
from app.services import config_service, statistics
from app.services.response_analyzer import response_percentiles

router = APIRouter()


@router.get("")
def get_overview(db: Session = Depends(get_db)) -> dict:
    """Section 6 + 29: totals, span, and the headline overview cards."""
    cfg = config_service.get_or_create_config(db)
    overview = statistics.compute_overview(db)

    session_count = db.query(ConversationSession).count()

    other_times = [e.response_seconds for e in db.query(ResponseEvent).filter_by(response_role="other").all()]
    me_times = [e.response_seconds for e in db.query(ResponseEvent).filter_by(response_role="me").all()]

    return {
        "chat_name": cfg.chat_name,
        "me_display_name": cfg.me_display_name,
        "other_display_name": cfg.other_display_name,
        "timezone": cfg.timezone,
        "total_messages": overview.total_messages,
        "me_messages": overview.me_messages,
        "other_messages": overview.other_messages,
        "me_percentage": overview.me_percentage,
        "other_percentage": overview.other_percentage,
        "first_message_date": overview.first_message_date,
        "last_message_date": overview.last_message_date,
        "conversation_span_days": overview.conversation_span_days,
        "active_days": overview.active_days,
        "active_weeks": overview.active_weeks,
        "active_months": overview.active_months,
        "conversation_sessions": session_count,
        "other_response": response_percentiles(other_times),
        "me_response": response_percentiles(me_times),
    }
