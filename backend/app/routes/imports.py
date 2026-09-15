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

    analysis: dict | None = None
    analysis_error: str | None = None
    if cfg.me_user_id and cfg.other_user_id:
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
        "participants_configured": bool(cfg.me_user_id and cfg.other_user_id),
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
