"""SQLAlchemy ORM models.

Design notes
------------
* ``Message.sender_id`` stores the raw Telegram id/hash for the sender.
  Whether a sender is "me" or "the other person" is a *configuration*
  choice (see :class:`AppConfig`), never baked into the schema, so the
  same code works for any two-person export.
* ``ResponseEvent`` and ``ConversationSession`` are derived tables,
  populated by the analysis services (Phase 2-4) so expensive aggregates
  don't need to be recomputed on every API call.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


class AppConfig(Base):
    """Single-row table holding the user's setup choices."""

    __tablename__ = "app_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    chat_name: Mapped[str | None] = mapped_column(String, nullable=True)

    me_user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    me_display_name: Mapped[str | None] = mapped_column(String, nullable=True)

    other_user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    other_display_name: Mapped[str | None] = mapped_column(String, nullable=True)

    timezone: Mapped[str] = mapped_column(String, default="Asia/Tashkent")

    grouping_window_minutes: Mapped[int] = mapped_column(Integer, default=5)
    session_gap_hours: Mapped[int] = mapped_column(Integer, default=6)
    min_sample_size: Mapped[int] = mapped_column(Integer, default=10)

    updated_at: Mapped[dt.datetime] = mapped_column(default=_utcnow, onupdate=_utcnow)


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("telegram_message_id", name="uq_messages_telegram_id"),
        Index("ix_messages_weekday_hour", "weekday", "hour"),
        Index("ix_messages_sender_ts", "sender_id", "timestamp_utc"),
        Index("ix_messages_date", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_message_id: Mapped[int] = mapped_column(Integer, index=True)

    sender_id: Mapped[str] = mapped_column(String, index=True)
    sender_name: Mapped[str | None] = mapped_column(String, nullable=True)

    timestamp_utc: Mapped[dt.datetime] = mapped_column(index=True)
    timestamp_local: Mapped[dt.datetime]

    date: Mapped[dt.date]
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    day: Mapped[int] = mapped_column(Integer)
    weekday: Mapped[int] = mapped_column(Integer)  # 0=Monday .. 6=Sunday
    hour: Mapped[int] = mapped_column(Integer, index=True)
    minute: Mapped[int] = mapped_column(Integer)

    message_type: Mapped[str] = mapped_column(String, index=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_length: Mapped[int] = mapped_column(Integer, default=0)

    reply_to_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ConversationSession(Base):
    __tablename__ = "conversation_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    start_ts: Mapped[dt.datetime] = mapped_column(index=True)
    end_ts: Mapped[dt.datetime]
    duration_seconds: Mapped[float] = mapped_column(Float)

    message_count: Mapped[int] = mapped_column(Integer)
    me_count: Mapped[int] = mapped_column(Integer)
    other_count: Mapped[int] = mapped_column(Integer)

    response_events: Mapped[list["ResponseEvent"]] = relationship(back_populates="session")


class ResponseEvent(Base):
    """One 'burst A -> burst B' response, after message-burst grouping."""

    __tablename__ = "response_events"
    __table_args__ = (
        Index("ix_response_events_response_role_ts", "response_role", "trigger_burst_end"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    session_id: Mapped[int | None] = mapped_column(ForeignKey("conversation_sessions.id"), nullable=True)
    session: Mapped[ConversationSession | None] = relationship(back_populates="response_events")

    # who sent the burst that got a reply, and who replied
    trigger_role: Mapped[str] = mapped_column(String)  # "me" | "other"
    response_role: Mapped[str] = mapped_column(String)  # "me" | "other"

    trigger_burst_start: Mapped[dt.datetime]
    trigger_burst_end: Mapped[dt.datetime]
    trigger_message_count: Mapped[int] = mapped_column(Integer, default=1)
    trigger_first_message_id: Mapped[int] = mapped_column(Integer)
    trigger_last_message_id: Mapped[int] = mapped_column(Integer)

    response_burst_start: Mapped[dt.datetime] = mapped_column(index=True)
    response_first_message_id: Mapped[int] = mapped_column(Integer)

    response_seconds: Mapped[float] = mapped_column(Float, index=True)

    weekday: Mapped[int] = mapped_column(Integer, index=True)  # weekday of the trigger burst end
    hour: Mapped[int] = mapped_column(Integer, index=True)  # hour of the trigger burst end


class UnansweredBurst(Base):
    """A message burst with no opposite-sender burst after it (yet)."""

    __tablename__ = "unanswered_bursts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("conversation_sessions.id"), nullable=True)

    sender_role: Mapped[str] = mapped_column(String)  # "me" | "other"
    burst_start: Mapped[dt.datetime]
    burst_end: Mapped[dt.datetime] = mapped_column(index=True)
    message_count: Mapped[int] = mapped_column(Integer, default=1)
    first_message_id: Mapped[int] = mapped_column(Integer)
    last_message_id: Mapped[int] = mapped_column(Integer)

    # classification, filled in by the response analyzer:
    # "conversation_likely_ended" | "long_unresolved_delay" | "end_of_history"
    classification: Mapped[str] = mapped_column(String)
    hours_since: Mapped[float] = mapped_column(Float)  # hours between burst_end and end of export


class ImportReport(Base):
    """Data-quality report produced by the last import run."""

    __tablename__ = "import_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[dt.datetime] = mapped_column(default=_utcnow)
    source_file: Mapped[str | None] = mapped_column(String, nullable=True)
    imported_count: Mapped[int] = mapped_column(Integer, default=0)
    valid_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_reasons_json: Mapped[str | None] = mapped_column(Text, nullable=True)
