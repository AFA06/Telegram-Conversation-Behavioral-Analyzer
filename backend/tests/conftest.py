import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Message  # noqa: F401  (register all models on Base.metadata)
from app.services.config_service import set_participants


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def configured_db(db):
    """DB with 'me' (id=1000) and 'other' (id=2000) participants set, in
    Asia/Tashkent, using the spec's default analysis parameters.
    """
    set_participants(db, me_user_id="user1000", me_display_name="Me", other_user_id="user2000", other_display_name="Them")
    return db


def make_message(id: int, telegram_message_id: int, sender_id: str, ts: dt.datetime, text: str = "hi", message_type: str = "text") -> Message:
    local = ts  # tests use naive UTC==local for simplicity unless stated otherwise
    return Message(
        id=id,
        telegram_message_id=telegram_message_id,
        sender_id=sender_id,
        sender_name=sender_id,
        timestamp_utc=ts,
        timestamp_local=local,
        date=local.date(),
        year=local.year,
        month=local.month,
        day=local.day,
        weekday=local.weekday(),
        hour=local.hour,
        minute=local.minute,
        message_type=message_type,
        text=text,
        text_length=len(text or ""),
        reply_to_message_id=None,
    )
