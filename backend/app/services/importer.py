"""Persists parsed Telegram messages into the local database.

The tool is designed around a single imported conversation at a time
(matching the project's local-first, one-chat-at-a-time scope), so an
import replaces whatever was previously stored rather than merging.
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import ConversationSession, ImportReport, Message, ResponseEvent, UnansweredBurst
from app.services.telegram_parser import ParsedMessage, QualityReport, parse_export
from app.utils.time import to_local


def wipe_conversation_data(db: Session) -> None:
    """Clears messages and every derived table (sessions/response events)."""
    db.execute(delete(ResponseEvent))
    db.execute(delete(UnansweredBurst))
    db.execute(delete(ConversationSession))
    db.execute(delete(Message))
    db.commit()


def _to_row(pm: ParsedMessage, timezone_name: str) -> Message:
    local_ts = to_local(pm.timestamp_utc, timezone_name)
    return Message(
        telegram_message_id=pm.telegram_message_id,
        sender_id=pm.sender_id,
        sender_name=pm.sender_name,
        timestamp_utc=pm.timestamp_utc,
        timestamp_local=local_ts,
        date=local_ts.date(),
        year=local_ts.year,
        month=local_ts.month,
        day=local_ts.day,
        weekday=local_ts.weekday(),
        hour=local_ts.hour,
        minute=local_ts.minute,
        message_type=pm.message_type,
        text=pm.text or None,
        text_length=len(pm.text or ""),
        reply_to_message_id=pm.reply_to_message_id,
    )


def import_export_file(db: Session, file_path: str | Path, timezone_name: str) -> QualityReport:
    path = Path(file_path)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    parsed, report = parse_export(data, source_file=path.name)

    wipe_conversation_data(db)

    rows = [_to_row(pm, timezone_name) for pm in parsed]
    db.bulk_save_objects(rows)

    db.add(
        ImportReport(
            source_file=report.source_file,
            imported_count=report.imported_count,
            valid_count=report.valid_count,
            skipped_count=report.skipped_count,
            skipped_reasons_json=json.dumps(report.skipped_reasons),
        )
    )

    chat_name = data.get("name")
    if chat_name:
        from app.services.config_service import get_or_create_config

        cfg = get_or_create_config(db)
        cfg.chat_name = chat_name

    db.commit()
    return report
