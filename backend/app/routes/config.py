from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_current_db
from app.schemas import AppConfigOut, ParticipantConfigIn, SettingsIn
from app.services import config_service

router = APIRouter()


@router.get("", response_model=AppConfigOut)
def get_config(db: Session = Depends(get_current_db)) -> AppConfigOut:
    return AppConfigOut.model_validate(config_service.get_or_create_config(db))


@router.put("/participants", response_model=AppConfigOut)
def set_participants(payload: ParticipantConfigIn, db: Session = Depends(get_current_db)) -> AppConfigOut:
    cfg = config_service.set_participants(
        db,
        me_user_id=payload.me_user_id,
        me_display_name=payload.me_display_name,
        other_user_id=payload.other_user_id,
        other_display_name=payload.other_display_name,
    )
    return AppConfigOut.model_validate(cfg)


@router.put("/settings", response_model=AppConfigOut)
def update_settings(payload: SettingsIn, db: Session = Depends(get_current_db)) -> AppConfigOut:
    cfg = config_service.get_or_create_config(db)
    if payload.timezone is not None:
        cfg.timezone = payload.timezone
    if payload.grouping_window_minutes is not None:
        cfg.grouping_window_minutes = payload.grouping_window_minutes
    if payload.session_gap_hours is not None:
        cfg.session_gap_hours = payload.session_gap_hours
    if payload.min_sample_size is not None:
        cfg.min_sample_size = payload.min_sample_size
    db.commit()
    db.refresh(cfg)
    return AppConfigOut.model_validate(cfg)
