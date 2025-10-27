import pytest

from apps.dialog.normalization import normalize_text


def test_normalization_arabic_digits():
    eastern_digits = "٠١٢٣٤٥٦٧٨٩"  # Arabic-Indic digits
    assert normalize_text(eastern_digits) == "0123456789"


def test_normalization_diacritics():
    assert normalize_text("أُحِبُّ") == "احب"  # "I love" with diacritics -> normalized


def test_relative_day_and_service_synonyms():
    normalized = normalize_text("بكرة أريد تنضيف")
    tokens = set(normalized.split())
    assert "غد" in tokens
    assert "تنظيف" in tokens


def test_intent_tokens_appended():
    normalized = normalize_text("بكم تنظيف الأسنان")
    tokens = set(normalized.split())
    assert "intent_price" in tokens
    assert "intent_service" in tokens
