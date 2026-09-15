import datetime as dt

from app.services.session_analyzer import build_sessions
from tests.conftest import make_message

BASE = dt.datetime(2026, 1, 2, 18, 0, tzinfo=dt.timezone.utc)


def test_session_detection_default_gap():
    messages = [
        make_message(1, 1, "user1000", BASE),
        make_message(2, 2, "user2000", BASE + dt.timedelta(minutes=15)),
        make_message(3, 3, "user1000", BASE + dt.timedelta(hours=2, minutes=31)),
        # gap > 6h -> new session
        make_message(4, 4, "user2000", BASE + dt.timedelta(hours=17, minutes=45)),
    ]
    roles = {1: "me", 2: "other", 3: "me", 4: "other"}

    sessions = build_sessions(messages, roles, session_gap_hours=6)

    assert len(sessions) == 2
    assert sessions[0].message_count == 3
    assert sessions[0].me_count == 2
    assert sessions[0].other_count == 1
    assert sessions[1].message_count == 1


def test_session_duration_within_gap_stays_one_session():
    messages = [
        make_message(1, 1, "user1000", BASE),
        make_message(2, 2, "user2000", BASE + dt.timedelta(hours=5, minutes=59)),
    ]
    roles = {1: "me", 2: "other"}
    sessions = build_sessions(messages, roles, session_gap_hours=6)
    assert len(sessions) == 1
    assert sessions[0].duration_seconds == dt.timedelta(hours=5, minutes=59).total_seconds()


def test_session_gap_exceeding_threshold_splits_sessions():
    messages = [
        make_message(1, 1, "user1000", BASE),
        make_message(2, 2, "user2000", BASE + dt.timedelta(hours=6, minutes=1)),
    ]
    roles = {1: "me", 2: "other"}
    sessions = build_sessions(messages, roles, session_gap_hours=6)
    assert len(sessions) == 2


def test_empty_messages_returns_no_sessions():
    assert build_sessions([], {}, session_gap_hours=6) == []
