import datetime as dt

from app.services.config_service import detect_participants, matched_message_count
from tests.conftest import make_message

BASE = dt.datetime(2026, 1, 2, 20, 0, tzinfo=dt.timezone.utc)


def test_detect_participants_ranked_by_count(db):
    db.add_all(
        [
            make_message(1, 1, "userA", BASE, text="hi"),
            make_message(2, 2, "userA", BASE + dt.timedelta(minutes=1), text="hi again"),
            make_message(3, 3, "userB", BASE + dt.timedelta(minutes=2), text="hey"),
        ]
    )
    db.commit()

    detected = detect_participants(db)
    assert detected[0]["sender_id"] == "userA"
    assert detected[0]["message_count"] == 2
    assert detected[1]["sender_id"] == "userB"
    assert detected[1]["message_count"] == 1


def test_matched_message_count(db):
    db.add_all([make_message(1, 1, "userA", BASE, text="hi")])
    db.commit()

    assert matched_message_count(db, "userA") == 1
    assert matched_message_count(db, "userZ") == 0
    assert matched_message_count(db, None) == 0
