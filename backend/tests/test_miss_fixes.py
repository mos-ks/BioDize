"""Regression tests for two recall fixes (host-Excel misses):

  #3  an empty box/circle glyph transcribed before an option ("O Ja") is "not
      checked" -> MISSING_CHECKMARK.
  #1  a recorded elapsed time must equal Ende - Start (rule_duration); a
      Prozessverzögerung of 11:27->12:27 logged as 2:00 is a calculation error.
"""
from __future__ import annotations

from datetime import time

from app.pipeline.model import Block, Field
from app.pipeline.validate.rules import _checkbox_unmarked, rule_duration, rule_presence


# --- #3: empty-box option = unmarked ----------------------------------------

def test_empty_circle_option_is_unmarked():
    for v in ["O Ja", "○ 931", "□ Nein", "0 Ja", ""]:
        assert _checkbox_unmarked(v), f"{v!r} should read as unmarked"


def test_real_marks_and_values_stay_marked():
    # a real value or a filled mark must NOT be read as unmarked
    for v in ["Ja", "X Ja", "✓ Ja", "● Ja", "Ofen", "O2 Sensor", "931"]:
        assert not _checkbox_unmarked(v), f"{v!r} should NOT read as unmarked"


# --- #1: duration consistency -----------------------------------------------

def _time_block(start, end, dur):
    b = Block(chapter="", page_no=23, template="t")
    for label, t in [("Start Prozessverzögerung", start),
                     ("Ende Prozessverzögerung", end),
                     ("Tatsächliche Prozessverzögerung", dur)]:
        f = Field(page_no=23, chapter="", role=None, label_raw=label, value_raw=str(t))
        f.value = t
        f.value_type = "time"
        b.fields.append(f)
    return b


def _dur_field(b):
    return next(f for f in b.fields if "tatsächlich" in f.label_raw.lower())


def test_duration_mismatch_flags():
    b = _time_block(time(11, 27), time(12, 27), time(2, 0))  # real=1:00, recorded 2:00
    rule_duration(b)
    codes = [fl.code for fl in _dur_field(b).flags]
    assert "CALC_DURATION" in codes


def test_duration_correct_is_clean():
    b = _time_block(time(11, 27), time(12, 27), time(1, 0))  # 1:00 == Ende-Start
    rule_duration(b)
    assert _dur_field(b).flags == []


def test_duration_needs_all_three_times():
    b = Block(chapter="", page_no=23, template="t")
    f = Field(page_no=23, chapter="", role=None, label_raw="Start Prozessverzögerung", value_raw="11:27")
    f.value = time(11, 27)
    b.fields.append(f)
    rule_duration(b)  # only a start present -> no crash, no flag
    assert all(not fl for fl in (fld.flags for fld in b.fields))


# --- #4/#5: blank deviation-row checkbox in an active table ------------------

def _checkbox(label, value):
    f = Field(page_no=44, chapter="", role=None, label_raw=label, value_raw=value)
    f.value_type = "checkbox"
    return f


def test_blank_deviation_row_flagged_when_table_active():
    b = Block(chapter="", page_no=44, template="t")
    b.fields = [
        _checkbox("Abweichungen vorhanden.", "Ja"),                                   # active deviation
        _checkbox("Weitere Abweichungen", "Nein, restliches Kapitel findet keine Anwendung"),
        _checkbox("Weitere Abweichungen", ""),                                        # blank -> missing
        _checkbox("Weitere Abweichungen", ""),                                        # blank -> missing
    ]
    rule_presence(b)
    missing = [f for f in b.fields if any(fl.code == "MISSING_CHECKMARK" for fl in f.flags)]
    assert len(missing) == 2


def test_blank_deviation_not_flagged_when_table_inactive():
    # No row marked "Ja" -> not an active table; "keine Anwendung" guard applies.
    b = Block(chapter="", page_no=44, template="t")
    b.fields = [
        _checkbox("Weitere Abweichungen", "Nein, restliches Kapitel findet keine Anwendung"),
        _checkbox("Weitere Abweichungen", ""),
    ]
    rule_presence(b)
    assert all(not f.flags for f in b.fields)
