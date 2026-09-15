import datetime as dt

from app.services.response_analyzer import (
    build_bursts,
    classify_unanswered,
    response_distribution,
    response_percentiles,
    run_full_analysis,
)
from app.models import Message, ResponseEvent, UnansweredBurst
from tests.conftest import make_message

BASE = dt.datetime(2026, 1, 2, 20, 0, tzinfo=dt.timezone.utc)  # a Friday


def test_burst_grouping_collapses_message_bursts():
    # spec example: three quick messages from "me", then one reply from "other"
    messages = [
        make_message(1, 1, "user1000", BASE),
        make_message(2, 2, "user1000", BASE + dt.timedelta(minutes=1)),
        make_message(3, 3, "user1000", BASE + dt.timedelta(minutes=2)),
        make_message(4, 4, "user2000", BASE + dt.timedelta(minutes=5)),
    ]
    roles = {1: "me", 2: "me", 3: "me", 4: "other"}

    bursts = build_bursts(messages, roles, grouping_window_minutes=5)

    assert len(bursts) == 2
    assert bursts[0].role == "me"
    assert bursts[0].count == 3
    assert bursts[0].end_ts == BASE + dt.timedelta(minutes=2)
    assert bursts[1].role == "other"
    assert bursts[1].start_ts == BASE + dt.timedelta(minutes=5)


def test_burst_grouping_breaks_on_gap_exceeding_window():
    messages = [
        make_message(1, 1, "user1000", BASE),
        make_message(2, 2, "user1000", BASE + dt.timedelta(minutes=10)),  # > 5 min gap
    ]
    roles = {1: "me", 2: "me"}
    bursts = build_bursts(messages, roles, grouping_window_minutes=5)
    assert len(bursts) == 2


def test_classify_unanswered_quick_followup_vs_long_delay():
    end = BASE
    label, hours = classify_unanswered(end, end + dt.timedelta(hours=1))
    assert label == "conversation_likely_ended"

    label, hours = classify_unanswered(end, end + dt.timedelta(hours=20))
    assert label == "long_unresolved_delay"
    assert hours == 20.0

    label, hours = classify_unanswered(end, None)
    assert label == "no_response_before_export_ended"


def test_response_percentiles():
    stats = response_percentiles([10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
    assert stats["count"] == 10
    assert stats["fastest_seconds"] == 10
    assert stats["slowest_seconds"] == 100
    assert stats["median_seconds"] == 55


def test_response_percentiles_empty():
    assert response_percentiles([]) == {}


def test_response_distribution_buckets():
    dist = response_distribution([30, 90, 600, 25 * 3600])
    by_bucket = {d["bucket"]: d["count"] for d in dist}
    assert by_bucket["< 1 minute"] == 1
    assert by_bucket["1-5 minutes"] == 1
    assert by_bucket["5-15 minutes"] == 1
    assert by_bucket["24h+"] == 1


def test_run_full_analysis_end_to_end(configured_db):
    db = configured_db
    messages = [
        make_message(1, 1, "user1000", BASE, text="Hey"),
        make_message(2, 2, "user1000", BASE + dt.timedelta(minutes=1), text="How are you?"),
        make_message(3, 3, "user2000", BASE + dt.timedelta(minutes=5), text="Heyy"),
        # a big gap -> new session
        make_message(4, 4, "user1000", BASE + dt.timedelta(hours=20), text="Hi again"),
    ]
    db.add_all(messages)
    db.commit()

    result = run_full_analysis(db)

    assert result["sessions"] == 2
    # burst(me: 1,2) -> burst(other: 3)  AND  burst(other: 3) -> burst(me: 4)
    assert result["response_events"] == 2
    # burst 4 (my last message) is itself still unanswered at the end of history
    assert result["unanswered_bursts"] == 1

    her_response = db.query(ResponseEvent).filter_by(response_role="other").one()
    assert her_response.response_seconds == dt.timedelta(minutes=4).total_seconds()

    my_response = db.query(ResponseEvent).filter_by(response_role="me").one()
    assert my_response.response_seconds == dt.timedelta(hours=19, minutes=55).total_seconds()

    unanswered = db.query(UnansweredBurst).one()
    assert unanswered.sender_role == "me"
    assert unanswered.classification == "no_response_before_export_ended"


def test_run_full_analysis_flags_unanswered_burst(configured_db):
    db = configured_db
    # a single burst with nothing after it in the whole export
    messages = [make_message(1, 1, "user1000", BASE, text="Hey")]
    db.add_all(messages)
    db.commit()

    result = run_full_analysis(db)

    assert result["response_events"] == 0
    assert result["unanswered_bursts"] == 1
    unanswered = db.query(UnansweredBurst).one()
    assert unanswered.sender_role == "me"
    assert unanswered.classification == "no_response_before_export_ended"


def test_run_full_analysis_classifies_same_role_followup_as_long_delay(configured_db):
    db = configured_db
    messages = [
        make_message(1, 1, "user1000", BASE, text="Hey"),
        # same sender, 30h later, still no reply from the other person
        make_message(2, 2, "user1000", BASE + dt.timedelta(hours=30), text="You there?"),
    ]
    db.add_all(messages)
    db.commit()

    run_full_analysis(db)

    unanswered = db.query(UnansweredBurst).order_by(UnansweredBurst.burst_start).all()
    assert len(unanswered) == 2
    assert unanswered[0].classification == "long_unresolved_delay"
    assert unanswered[1].classification == "no_response_before_export_ended"
