from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.deps import get_current_db
from app.services import config_service
from app.services.importer import import_export_file
from app.services.response_analyzer import run_full_analysis

router = APIRouter()


@router.post("")
async def import_file(file: UploadFile, db: Session = Depends(get_current_db)) -> dict:
    """Uploads a Telegram Desktop JSON export, replacing any previously
    imported conversation. If participants are already configured,
    re-analyzes automatically.
    """
    raw = await file.read()
    try:
        json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Not valid JSON: {exc}") from exc

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp.write(raw)
        tmp_path = Path(tmp.name)

    try:
        cfg = config_service.get_or_create_config(db)
        report = import_export_file(db, tmp_path, cfg.timezone)
    finally:
        tmp_path.unlink(missing_ok=True)

    detected = config_service.detect_participants(db)

    # Participants configured for a *previous* import don't necessarily
    # apply to this one — importing a different conversation entirely
    # (a different chat, or the same slot re-imported from a different
    # export) means the old me_user_id/other_user_id may not match any
    # sender in the new data at all. Blindly trusting them here silently
    # ran analysis against a stale mapping: the new "other" person's
    # messages resolved to role "unknown" (excluded from every stat) while
    # other_display_name kept showing the *previous* conversation's name.
    # Re-verify against the freshly imported data on every import, not
    # just the first one.
    participants_still_valid = bool(cfg.me_user_id) and bool(cfg.other_user_id)
    if participants_still_valid:
        me_matches = config_service.matched_message_count(db, cfg.me_user_id)
        other_matches = config_service.matched_message_count(db, cfg.other_user_id)
        participants_still_valid = me_matches > 0 and other_matches > 0

    if not participants_still_valid and (cfg.me_user_id or cfg.other_user_id):
        cfg.me_user_id = None
        cfg.me_display_name = None
        cfg.other_user_id = None
        cfg.other_display_name = None
        db.commit()

    analysis: dict | None = None
    analysis_error: str | None = None
    if participants_still_valid:
        try:
            analysis = run_full_analysis(db)
        except ValueError as exc:
            analysis_error = str(exc)

    return {
        "imported_count": report.imported_count,
        "valid_count": report.valid_count,
        "skipped_count": report.skipped_count,
        "skipped_reasons": report.skipped_reasons,
        "analysis": analysis,
        "analysis_error": analysis_error,
        "participants_configured": participants_still_valid,
        "detected_participants": detected,
    }


@router.get("/participants")
def detected_participants(db: Session = Depends(get_current_db)) -> list[dict]:
    """Sender ids actually found in the imported messages, ranked by
    message count — use this instead of guessing the id format.
    """
    return config_service.detect_participants(db)


@router.post("/analyze")
def reanalyze(db: Session = Depends(get_current_db)) -> dict:
    """Re-runs session/response-time analysis (e.g. after changing
    participants, timezone, grouping window, or session gap in Settings).
    """
    try:
        return run_full_analysis(db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
