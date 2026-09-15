"""Reads/writes the single-row AppConfig (participant identities, timezone,
and analysis parameters). Nothing here is hardcoded to any specific chat —
identities are always supplied by the user via the CLI or the Settings page.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import settings
from app.models import AppConfig

CONFIG_ROW_ID = 1


def get_or_create_config(db: Session) -> AppConfig:
    cfg = db.get(AppConfig, CONFIG_ROW_ID)
    if cfg is None:
        cfg = AppConfig(
            id=CONFIG_ROW_ID,
            timezone=settings.default_timezone,
            grouping_window_minutes=settings.default_grouping_window_minutes,
            session_gap_hours=settings.default_session_gap_hours,
            min_sample_size=settings.default_min_sample_size,
        )
        db.add(cfg)
        db.commit()
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


def role_for_sender(cfg: AppConfig, sender_id: str) -> str:
    """Maps a raw Telegram sender id to 'me' / 'other' / 'unknown'."""
    sender_id = str(sender_id)
    if cfg.me_user_id and sender_id == cfg.me_user_id:
        return "me"
    if cfg.other_user_id and sender_id == cfg.other_user_id:
        return "other"
    return "unknown"
