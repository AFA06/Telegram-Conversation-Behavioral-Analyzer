import pandas as pd

from app.services.activity_analyzer import daily_activity, heatmap, hourly_activity, top_activity_windows, weekday_activity


def _df(rows):
    return pd.DataFrame(rows)


def test_hourly_activity_counts_and_percentages():
    df = _df(
        [
            {"id": 1, "hour": 20, "weekday": 4, "minute": 0, "role": "other"},
            {"id": 2, "hour": 20, "weekday": 4, "minute": 5, "role": "other"},
            {"id": 3, "hour": 9, "weekday": 4, "minute": 0, "role": "me"},
        ]
    )
    result = hourly_activity(df, role="other")
    hour_20 = next(r for r in result if r["hour"] == 20)
    assert hour_20["count"] == 2
    assert hour_20["percentage"] == 100.0
    assert len(result) == 24


def test_weekday_activity_both_roles():
    df = _df(
        [
            {"id": 1, "hour": 20, "weekday": 4, "minute": 0, "role": "other"},
            {"id": 2, "hour": 9, "weekday": 0, "minute": 0, "role": "me"},
        ]
    )
    result = weekday_activity(df, role="both")
    friday = next(r for r in result if r["name"] == "Friday")
    monday = next(r for r in result if r["name"] == "Monday")
    assert friday["count"] == 1
    assert monday["count"] == 1


def test_heatmap_shape_and_values():
    df = _df([{"id": 1, "hour": 20, "weekday": 4, "minute": 0, "role": "other"}])
    hm = heatmap(df, role="both")
    assert len(hm["grid"]) == 7
    assert len(hm["grid"][0]) == 24
    assert hm["grid"][4][20] == 1
    assert hm["max_count"] == 1


def test_top_activity_windows_picks_highest_volume_non_overlapping():
    rows = []
    msg_id = 1
    # heavy activity Friday 20:00-21:00, light activity elsewhere
    for _ in range(20):
        rows.append({"id": msg_id, "hour": 20, "weekday": 4, "minute": 0, "role": "both"})
        msg_id += 1
    rows.append({"id": msg_id, "hour": 9, "weekday": 0, "minute": 0, "role": "both"})

    df = _df(rows)
    windows = top_activity_windows(df, role="both", window_minutes=60, top_n=2)
    assert windows[0]["weekday_name"] == "Friday"
    assert windows[0]["message_count"] == 20


def test_top_activity_windows_empty_df_returns_empty_list():
    assert top_activity_windows(pd.DataFrame(), role="both") == []


def test_daily_activity_covers_full_month():
    df = _df(
        [
            {"id": 1, "year": 2026, "month": 2, "day": 5, "role": "me"},
            {"id": 2, "year": 2026, "month": 2, "day": 5, "role": "other"},
            {"id": 3, "year": 2026, "month": 2, "day": 5, "role": "other"},
        ]
    )
    result = daily_activity(df, 2026, 2)
    assert len(result) == 28  # Feb 2026 is not a leap year
    day5 = next(r for r in result if r["day"] == 5)
    assert day5 == {"day": 5, "me_count": 1, "other_count": 2, "total": 3}
    assert result[0]["total"] == 0


def test_daily_activity_empty_df():
    assert daily_activity(pd.DataFrame(), 2026, 1) == []
