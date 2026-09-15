"""Reads/writes the single-row AppConfig (participant identities, timezone,
and analysis parameters). Nothing here is hardcoded to any specific chat —
identities are always supplied by the user via the CLI or the Settings page.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AppConfig, Message

CONFIG_ROW_ID = 1


def get_or_create_config(db: Session) -> AppConfig:
    cfg = db.get(AppConfig, CONFIG_ROW_ID)
    if cfg is not None:
        return cfg

    cfg = AppConfig(
        id=CONFIG_ROW_ID,
        timezone=settings.default_timezone,
        grouping_window_minutes=settings.default_grouping_window_minutes,
        session_gap_hours=settings.default_session_gap_hours,
        min_sample_size=settings.default_min_sample_size,
    )
    db.add(cfg)
    try:
        db.commit()
    except IntegrityError:
        # Another concurrent request (different thread/session) won the
        # race to create the single config row first — this is expected
        # under concurrency (e.g. two webhook deliveries for a brand-new
        # tenant), not an error: just use the row it created.
        db.rollback()
        cfg = db.get(AppConfig, CONFIG_ROW_ID)
    else:
        db.refresh(cfg)
    return cfg


def set_participants(db: Session, me_user_id: str, me_display_name: str, other_user_id: str, other_display_name: str) -> AppConfig:
    cfg = get_or_create_config(db)
    cfg.me_user_id = str(me_user_id)
    cfg.me_display_name = me_display_name
    cfg.other_user_id = str(other_user_id)
    cfg.other_display_name = other_display_name
    db.commit()
    db.refresh(cfg)
    return cfg


def detect_participants(db: Session, limit: int = 10) -> list[dict]:
    """Lists the actual sender ids present in the imported messages, ranked
    by message count. Telegram exports store ``from_id`` in a prefixed form
    (e.g. ``user938613594``, not bare ``938613594``), so this is the
    reliable way to find the exact id string to configure — rather than
    guessing at the format.
    """
    rows = (
        db.query(Message.sender_id, Message.sender_name, func.count(Message.id).label("count"))
        .group_by(Message.sender_id, Message.sender_name)
        .order_by(func.count(Message.id).desc())
        .limit(limit)
        .all()
    )
    return [{"sender_id": r.sender_id, "sender_name": r.sender_name, "message_count": r.count} for r in rows]


def matched_message_count(db: Session, sender_id: str | None) -> int:
    if not sender_id:
        return 0
    return db.query(Message).filter(Message.sender_id == sender_id).count()


def role_for_sender(cfg: AppConfig, sender_id: str) -> str:
    """Maps a raw Telegram sender id to 'me' / 'other' / 'unknown'."""
    sender_id = str(sender_id)
    if cfg.me_user_id and sender_id == cfg.me_user_id:
        return "me"
    if cfg.other_user_id and sender_id == cfg.other_user_id:
        return "other"
    return "unknown"
