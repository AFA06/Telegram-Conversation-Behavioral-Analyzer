"""Parses a Telegram Desktop JSON export into normalized ``ParsedMessage``
records, plus a data-quality report.

This module is pure and has no database or FastAPI dependency, which keeps
it easy to unit test with small synthetic exports (see ``backend/tests``).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from app.utils.time import is_reasonable_timestamp, parse_export_timestamp

# Telegram "type": "service" actions we still care about the timing of.
# Most service messages (pinned, group name changes, etc.) are noise for a
# 1:1 conversation-behavior analysis and are skipped.
USEFUL_SERVICE_ACTIONS: set[str] = set()


@dataclass
class ParsedMessage:
    telegram_message_id: int
    sender_id: str
    sender_name: str | None
    timestamp_utc: dt.datetime
    message_type: str
    text: str
    reply_to_message_id: int | None
    timestamp_was_assumed: bool = False


@dataclass
class QualityReport:
    source_file: str | None = None
    imported_count: int = 0
    valid_count: int = 0
    skipped_count: int = 0
    skipped_reasons: dict[str, int] = field(default_factory=dict)
    assumed_timezone_count: int = 0

    def skip(self, reason: str) -> None:
        self.skipped_count += 1
        self.skipped_reasons[reason] = self.skipped_reasons.get(reason, 0) + 1


def normalize_text(text_field: object) -> str:
    """Telegram's ``text`` field is either a plain string or a list mixing
    plain strings with rich-entity objects like ``{"type": "bold", "text": "world"}``.
    """
    if text_field is None:
        return ""
    if isinstance(text_field, str):
        return text_field
    if isinstance(text_field, list):
        parts: list[str] = []
        for item in text_field:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text", "")))
        return "".join(parts)
    return str(text_field)


def detect_message_type(raw: dict) -> str:
    """Best-effort classification of a Telegram export message record."""
    if raw.get("type") == "service":
        return "service"

    media_type = raw.get("media_type")
    if media_type:
        # Telegram uses e.g. "sticker", "video_message", "voice_message",
        # "animation", "audio_file", "video_file"
        return media_type

    if raw.get("photo") is not None:
        return "photo"
    if raw.get("poll") is not None:
        return "poll"
    if raw.get("contact_information") is not None:
        return "contact"
    if raw.get("location_information") is not None:
        return "location"
    if raw.get("file") is not None:
        # Generic file/document without a more specific media_type
        mime = str(raw.get("mime_type", ""))
        if mime.startswith("audio"):
            return "audio"
        if mime.startswith("video"):
            return "video"
        return "file"

    text = normalize_text(raw.get("text"))
    if text.strip():
        return "text"
    return "empty"


def parse_export(data: dict, source_file: str | None = None) -> tuple[list[ParsedMessage], QualityReport]:
    """Parse a full Telegram export dict (the 'messages' array) into
    ``ParsedMessage`` records plus a data-quality report.
    """
    report = QualityReport(source_file=source_file)
    raw_messages = data.get("messages", [])
    parsed: list[ParsedMessage] = []
    seen_ids: set[int] = set()

    for raw in raw_messages:
        report.imported_count += 1

        if not isinstance(raw, dict):
            report.skip("malformed_record")
            continue

        msg_type_field = raw.get("type")
        if msg_type_field == "service" and raw.get("action") not in USEFUL_SERVICE_ACTIONS:
            report.skip("service_message_ignored")
            continue

        msg_id = raw.get("id")
        if not isinstance(msg_id, int):
            report.skip("missing_or_invalid_message_id")
            continue
        if msg_id in seen_ids:
            report.skip("duplicate_message_id")
            continue

        sender_id = raw.get("from_id") or raw.get("actor_id")
        if not sender_id:
            report.skip("missing_sender")
            continue

        timestamp_utc, was_assumed = parse_export_timestamp(raw.get("date"), raw.get("date_unixtime"))
        if timestamp_utc is None:
            report.skip("invalid_timestamp")
            continue
        if not is_reasonable_timestamp(timestamp_utc):
            report.skip("timestamp_out_of_range")
            continue

        message_type = detect_message_type(raw)
        text = normalize_text(raw.get("text"))

        reply_to = raw.get("reply_to_message_id")
        if not isinstance(reply_to, int):
            reply_to = None

        seen_ids.add(msg_id)
        if was_assumed:
            report.assumed_timezone_count += 1

        parsed.append(
            ParsedMessage(
                telegram_message_id=msg_id,
                sender_id=str(sender_id),
                sender_name=raw.get("from") or raw.get("actor"),
                timestamp_utc=timestamp_utc,
                message_type=message_type,
                text=text,
                reply_to_message_id=reply_to,
                timestamp_was_assumed=was_assumed,
            )
        )
        report.valid_count += 1

    return parsed, report
