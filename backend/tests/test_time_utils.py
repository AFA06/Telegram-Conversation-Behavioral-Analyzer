import datetime as dt

from app.utils.time import is_reasonable_timestamp, parse_export_timestamp, to_local


def test_parse_export_timestamp_prefers_unixtime():
    ts, assumed = parse_export_timestamp("2026-01-01T20:31:12", "1767299472")
    assert assumed is False
    assert ts.tzinfo is not None
    assert ts == dt.datetime.fromtimestamp(1767299472, tz=dt.timezone.utc)


def test_parse_export_timestamp_falls_back_to_naive_date():
    ts, assumed = parse_export_timestamp("2026-01-01T20:31:12", None)
    assert assumed is True
    assert ts.year == 2026 and ts.hour == 20


def test_parse_export_timestamp_invalid_returns_none():
    ts, assumed = parse_export_timestamp(None, None)
    assert ts is None


def test_to_local_conversion_tashkent():
    utc_ts = dt.datetime(2026, 1, 1, 15, 0, tzinfo=dt.timezone.utc)
    local = to_local(utc_ts, "Asia/Tashkent")
    # Asia/Tashkent is UTC+5 year-round (no DST)
    assert local.hour == 20
    assert local.utcoffset() == dt.timedelta(hours=5)


def test_is_reasonable_timestamp_bounds():
    assert is_reasonable_timestamp(dt.datetime(2025, 6, 1, tzinfo=dt.timezone.utc)) is True
    assert is_reasonable_timestamp(dt.datetime(2005, 1, 1, tzinfo=dt.timezone.utc)) is False
    assert is_reasonable_timestamp(dt.datetime(2099, 1, 1, tzinfo=dt.timezone.utc)) is False
