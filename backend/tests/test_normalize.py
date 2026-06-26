"""Unit tests for EU-format parsing and Soll ranges."""
from app.pipeline.normalize import (
    detect_value_type,
    is_zero_padded_date,
    parse_german_number,
    parse_soll,
)


def test_german_decimal_comma():
    assert parse_german_number("4,50") == (4.5, 2)
    assert parse_german_number("1,100") == (1.1, 3)
    assert parse_german_number("1.100") == (1100.0, 0)   # thousands dot
    assert parse_german_number("220") == (220.0, 0)
    assert parse_german_number("abc") == (None, None)


def test_zero_padded_date():
    assert is_zero_padded_date("10.06.2026") is True
    assert is_zero_padded_date("10.6.2026") is False     # the "06" rule
    assert is_zero_padded_date("1.6.2026") is False


def test_value_type():
    assert detect_value_type("10.06.2026") == "date"
    assert detect_value_type("14:46") == "time"
    assert detect_value_type("10.06.2026 14:46") == "datetime"
    assert detect_value_type("4,50") == "number"
    assert detect_value_type("Ja") == "bool"
    assert detect_value_type("hello") == "text"


def test_parse_soll():
    assert parse_soll("2 - 8") == {"min": 2.0, "max": 8.0, "target": None}
    assert parse_soll("20 - 30") == {"min": 20.0, "max": 30.0, "target": None}
    assert parse_soll("<= 3")["max"] == 3.0
    assert parse_soll(">= 5")["min"] == 5.0
    r = parse_soll("11,95 (8,56 - 23,30)")
    assert r["min"] == 8.56 and r["max"] == 23.3 and r["target"] == 11.95
