"""Unit tests for EU-format parsing and Soll ranges."""
from app.pipeline.normalize import (
    _doc_reference_year,
    detect_value_type,
    is_zero_padded_date,
    normalize,
    parse_german_number,
    parse_soll,
)
from app.pipeline.model import Block, Document, Field


def test_year_correction_is_doc_derived_not_hardcoded():
    """Generalization guard: the batch year must come from the DOCUMENT, never a
    constant. A 2027 record with one misread 2037 must snap to 2027 — not 2026."""
    doc = Document(doc_no="x", title="x")
    b = Block(chapter="", page_no=1, template="t")
    b.fields = [
        Field(page_no=1, chapter="", role=None, label_raw="Datum", value_raw=v)
        for v in ("01.03.2027", "05.03.2027", "09.03.2027", "10.03.2037")
    ]
    doc.blocks = [b]
    assert _doc_reference_year(doc) == 2027         # modal year of the doc's own dates
    normalize(doc)
    assert b.fields[3].value is not None
    assert b.fields[3].value.year == 2027           # snapped to 2027, NOT the old 2026


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
