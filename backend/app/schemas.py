"""Pydantic request/response models. Kept deliberately small: most GET
endpoints return plain dicts built by the services layer (documented in the
route docstrings) — these models cover the payloads clients actually send
us, where validation matters.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ParticipantConfigIn(BaseModel):
    me_user_id: str
    me_display_name: str = "Me"
    other_user_id: str
    other_display_name: str = "Other person"


class SettingsIn(BaseModel):
    timezone: str | None = None
    grouping_window_minutes: int | None = Field(default=None, ge=1, le=120)
    session_gap_hours: int | None = Field(default=None, ge=1, le=72)
    min_sample_size: int | None = Field(default=None, ge=1, le=1000)
    language: str | None = Field(default=None, pattern="^(en|uz)$")


class AppConfigOut(BaseModel):
    chat_name: str | None
    me_user_id: str | None
    me_display_name: str | None
    other_user_id: str | None
    other_display_name: str | None
    timezone: str
    grouping_window_minutes: int
    session_gap_hours: int
    min_sample_size: int
    language: str

    model_config = {"from_attributes": True}


class AskIn(BaseModel):
    question: str
    lang: str = Field(default="en", pattern="^(en|uz)$")
