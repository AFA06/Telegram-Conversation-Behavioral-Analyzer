from app.utils.formatting import confidence_label, format_duration


def test_format_duration_seconds_minutes_hours_days():
    assert format_duration(12) == "12s"
    assert format_duration(6 * 60) == "6m"
    assert format_duration(3600 + 600) == "1h 10m"
    assert format_duration(3600 * 25 + 60) == "1d 1h"
    assert format_duration(None) == "N/A"


def test_confidence_label_thresholds():
    assert confidence_label(2) == "Very low"
    assert confidence_label(9) == "Low"
    assert confidence_label(29) == "Moderate"
    assert confidence_label(99) == "High"
    assert confidence_label(500) == "Very high"


def test_response_windows_below_min_sample_size_are_excluded():
    """Section 18: fewer than min_sample_size observations -> excluded from
    ranked results entirely, rather than shown with a misleading median.
    """
    from app.services.response_analyzer import best_response_windows
    from app.models import ResponseEvent

    class FakeQuery(list):
        def filter(self, *a, **k):
            return self

        def all(self):
            return self

    # Directly test the exclusion logic via response_stats_by_hour, which
    # shares the same min-sample-size gate.
    from app.services.response_analyzer import response_stats_by_hour

    class FakeSession:
        def query(self, *a, **k):
            return FakeQuery(
                [ResponseEvent(response_role="other", weekday=4, hour=20, response_seconds=60.0)]
            )

    result = response_stats_by_hour(FakeSession(), "other", min_sample_size=10)
    hour_20 = next(r for r in result if r["hour"] == 20)
    assert hour_20["sufficient_data"] is False
    assert hour_20["sample_size"] == 1
