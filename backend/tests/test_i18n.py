import pytest

pytest.importorskip("telegram", reason="python-telegram-bot not installed (see backend/bot/requirements.txt)")

from unittest.mock import MagicMock

from bot.i18n import detect_language, t


def test_detect_language_uzbek_variants():
    assert detect_language("uz") == "uz"
    assert detect_language("uz-UZ") == "uz"
    assert detect_language("UZ") == "uz"


def test_detect_language_defaults_to_english():
    assert detect_language("en") == "en"
    assert detect_language("ru") == "en"
    assert detect_language(None) == "en"
    assert detect_language("") == "en"


def test_detect_language_ignores_non_string_input():
    """Regression test: a Mock (or any non-string) must not be treated as
    truthy Uzbek — this exact bug made every bot test default to Uzbek
    before the fixtures explicitly set language_code.
    """
    assert detect_language(MagicMock()) == "en"
    assert detect_language(123) == "en"


def test_t_formats_and_falls_back():
    assert "Fastest" in t("en", "fastest_reply", duration="5s")
    assert "5s" in t("en", "fastest_reply", duration="5s")
    assert t("uz", "fastest_reply", duration="5s") != t("en", "fastest_reply", duration="5s")
    # unknown language falls back to English rather than raising
    assert t("fr", "dashboard_button") == t("en", "dashboard_button")
