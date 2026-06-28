"""Extended rule unit tests for previously untested validation rules:
rule_date_format, rule_time_format, rule_range, rule_net_mass, rule_volume,
rule_end_after_start, rule_duration, rule_presence, safe_arith."""
from __future__ import annotations
import pytest
from datetime import date, time, datetime

from app.pipeline.model import Block, Document, Field
from app.pipeline.validate.rules import (
    rule_date_format,
    rule_duration,
    rule_end_after_start,
    rule_net_mass,
    rule_presence,
    rule_range,
    rule_time_format,
    rule_volume,
    safe_arith,
)
from app.domain.roles import Role


# ── Helpers ───────────────────────────────────────────────────────────────────

def _f(label: str, value: str, role=None, **kw) -> Field:
    return Field(page_no=1, chapter="", role=role, label_raw=label, value_raw=value, **kw)

def _b(*fields: Field) -> Block:
    b = Block(chapter="", page_no=1, template="x")
    b.fields = list(fields)
    return b


# ── safe_arith ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("expr, expected", [
    ("2 + 3",             5.0),
    ("10 - 4",            6.0),
    ("3 * 4",            12.0),
    ("10 / 4",            2.5),
    ("(4 + 6) * 2",      20.0),
    # German decimal comma
    ("6,6 * 45",         297.0),
    ("6,6 * 45 - 4,3 * 0,75", 6.6 * 45 - 4.3 * 0.75),
    # RHS of equation (after =)
    ("result = 6 * 7",   42.0),
    # Unary minus
    ("-5 + 10",            5.0),
])
def test_safe_arith_valid(expr, expected):
    result = safe_arith(expr)
    assert result is not None, f"safe_arith({expr!r}) returned None"
    assert abs(result - expected) < 1e-6, f"{result} != {expected}"

@pytest.mark.parametrize("expr", [
    None, "", "abc", "import os", "x**2", "os.system('ls')",
])
def test_safe_arith_invalid_returns_none(expr):
    assert safe_arith(expr) is None

def test_safe_arith_division_by_zero():
    assert safe_arith("1 / 0") is None

def test_safe_arith_nested_parens():
    assert abs(safe_arith("(2 + 3) * (4 - 1)") - 15.0) < 1e-6


# ── rule_date_format ──────────────────────────────────────────────────────────

def test_date_format_correctly_padded_clean():
    f = _f("Datum", "10.06.2026"); f.value_type = "date"
    assert rule_date_format(f) == []

def test_date_format_non_padded_month_flagged():
    f = _f("Datum", "10.6.2026"); f.value_type = "date"
    assert any(fl.code == "FMT_DATE_PADDING" for fl in rule_date_format(f))

def test_date_format_non_padded_day_flagged():
    f = _f("Datum", "1.06.2026"); f.value_type = "date"
    assert any(fl.code == "FMT_DATE_PADDING" for fl in rule_date_format(f))

def test_date_format_both_non_padded_flagged():
    f = _f("Datum", "1.6.2026"); f.value_type = "date"
    assert any(fl.code == "FMT_DATE_PADDING" for fl in rule_date_format(f))

def test_date_format_signature_padded_clean():
    f = _f("Bearbeitet", "10.06.2026 / ohe", role=Role.SIGNATURE_PROCESSED)
    assert rule_date_format(f) == []

def test_date_format_signature_non_padded_flagged():
    f = _f("Bearbeitet", "10.6.2026 / ohe", role=Role.SIGNATURE_PROCESSED)
    assert any(fl.code == "FMT_DATE_PADDING" for fl in rule_date_format(f))

def test_date_format_signature_text_only_skipped():
    # "Ja" as signature value: no digit in the date part -> not flagged
    f = _f("Bearbeitet", "Ja", role=Role.SIGNATURE_PROCESSED)
    assert rule_date_format(f) == []

def test_date_format_text_field_ignored():
    f = _f("Bemerkung", "some text"); f.value_type = "text"
    assert rule_date_format(f) == []

def test_date_format_datetime_non_padded_flagged():
    f = _f("Datum+Zeit", "1.6.2026 14:30"); f.value_type = "datetime"
    assert any(fl.code == "FMT_DATE_PADDING" for fl in rule_date_format(f))


# ── rule_time_format ──────────────────────────────────────────────────────────

def test_time_format_valid_times_clean():
    for raw in ("08:30", "00:00", "23:59", "12:00"):
        h, m = map(int, raw.split(":"))
        f = _f("Zeit", raw); f.value_type = "time"; f.value = time(h, m)
        assert rule_time_format(f) == [], f"Expected no flag for {raw!r}"

def test_time_format_non_time_field_ignored():
    f = _f("Datum", "10.06.2026"); f.value_type = "date"
    assert rule_time_format(f) == []

def test_time_format_missing_value_ignored():
    f = _f("Start", "08:30"); f.value_type = "time"; f.value = None
    assert rule_time_format(f) == []


# ── rule_range ────────────────────────────────────────────────────────────────

def test_range_within_bounds_clean():
    f = _f("Temp", "25"); f.soll = "20 - 30"; f.value = 25.0
    assert rule_range(f) == []

def test_range_at_lower_bound_clean():
    f = _f("Temp", "20"); f.soll = "20 - 30"; f.value = 20.0
    assert rule_range(f) == []

def test_range_at_upper_bound_clean():
    f = _f("Temp", "30"); f.soll = "20 - 30"; f.value = 30.0
    assert rule_range(f) == []

def test_range_below_min_flagged():
    f = _f("Temp", "15"); f.soll = "20 - 30"; f.value = 15.0
    assert any(fl.code == "RANGE_SOLL" for fl in rule_range(f))

def test_range_above_max_flagged():
    f = _f("Temp", "35"); f.soll = "20 - 30"; f.value = 35.0
    assert any(fl.code == "RANGE_SOLL" for fl in rule_range(f))

def test_range_max_only():
    f = _f("x", "4"); f.soll = "<= 3"; f.value = 4.0
    assert any(fl.code == "RANGE_SOLL" for fl in rule_range(f))
    f2 = _f("x", "3"); f2.soll = "<= 3"; f2.value = 3.0
    assert rule_range(f2) == []

def test_range_min_only():
    f = _f("x", "4"); f.soll = ">= 5"; f.value = 4.0
    assert any(fl.code == "RANGE_SOLL" for fl in rule_range(f))

def test_range_setpoint_mismatch_flagged():
    f = _f("Wert", "5"); f.soll = "3"; f.value = 5.0
    assert any(fl.code == "RANGE_SETPOINT" for fl in rule_range(f))

def test_range_setpoint_match_clean():
    f = _f("Wert", "3"); f.soll = "3"; f.value = 3.0
    assert rule_range(f) == []

def test_range_no_soll_skipped():
    f = _f("Wert", "999"); f.value = 999.0
    assert rule_range(f) == []

def test_range_bool_value_skipped():
    f = _f("Check", "Ja"); f.soll = "1"; f.value = True
    assert rule_range(f) == []

def test_range_non_numeric_value_skipped():
    f = _f("x", "text"); f.soll = "1 - 5"; f.value = "text"
    assert rule_range(f) == []

def test_range_setpoint_formula_soll_not_flagged():
    # Soll containing letters (formula blob) -> setpoint check skipped
    f = _f("V", "100"); f.soll = "V = m / rho, rho = 1,81 kg/L"; f.value = 100.0
    flags = rule_range(f)
    assert not any(fl.code == "RANGE_SETPOINT" for fl in flags)


# ── rule_net_mass ─────────────────────────────────────────────────────────────

def _mass_block(gross: float, tare: float, net: float) -> Block:
    g = _f("m Brutto", str(gross), role=Role.GROSS_MASS); g.value = gross
    t = _f("m Tara",   str(tare),  role=Role.TARE_MASS);  t.value = tare
    n = _f("m Netto",  str(net),   role=Role.NET_MASS);   n.value = net
    return _b(g, t, n)

def test_net_mass_correct():
    block = _mass_block(200.0, 50.0, 150.0)
    rule_net_mass(block)
    assert not any(fl.code == "CALC_NET_MASS" for fl in block.role(Role.NET_MASS).flags)

def test_net_mass_wrong_flagged():
    block = _mass_block(200.0, 50.0, 140.0)   # 200 - 50 = 150, got 140
    rule_net_mass(block)
    assert any(fl.code == "CALC_NET_MASS" for fl in block.role(Role.NET_MASS).flags)

def test_net_mass_within_tolerance():
    # tolerance = max(0.5, 0.01 * 150) = max(0.5, 1.5) = 1.5
    block = _mass_block(200.0, 50.0, 149.0)   # off by 1.0 < 1.5 -> clean
    rule_net_mass(block)
    assert not any(fl.code == "CALC_NET_MASS" for fl in block.role(Role.NET_MASS).flags)

def test_net_mass_outside_tolerance():
    block = _mass_block(200.0, 50.0, 147.0)   # off by 3.0 > 1.5 -> flagged
    rule_net_mass(block)
    assert any(fl.code == "CALC_NET_MASS" for fl in block.role(Role.NET_MASS).flags)

def test_net_mass_missing_tare_skipped():
    g = _f("m Brutto", "200", role=Role.GROSS_MASS); g.value = 200.0
    n = _f("m Netto",  "150", role=Role.NET_MASS);   n.value = 150.0
    block = _b(g, n)
    rule_net_mass(block)
    assert not n.flags

def test_net_mass_missing_gross_skipped():
    t = _f("m Tara",  "50",  role=Role.TARE_MASS); t.value = 50.0
    n = _f("m Netto", "150", role=Role.NET_MASS);  n.value = 150.0
    block = _b(t, n)
    rule_net_mass(block)
    assert not n.flags

def test_net_mass_multiple_groups():
    # Two gross/net pairs sharing one tare
    g1 = _f("m Brutto vPz", "427", role=Role.GROSS_MASS); g1.value = 427.0
    g2 = _f("m Brutto nPZ", "527", role=Role.GROSS_MASS); g2.value = 527.0
    t  = _f("m Tara",       "127", role=Role.TARE_MASS);  t.value  = 127.0
    n1 = _f("m Netto vPz",  "300", role=Role.NET_MASS);   n1.value = 300.0
    n2 = _f("m Netto nPZ",  "395", role=Role.NET_MASS);   n2.value = 395.0   # should be 400
    block = _b(g1, g2, t, n1, n2)
    rule_net_mass(block)
    assert not any(fl.code == "CALC_NET_MASS" for fl in n1.flags)    # 427-127=300 correct
    assert any(fl.code == "CALC_NET_MASS" for fl in n2.flags)        # 527-127=400 != 395


# ── rule_volume ───────────────────────────────────────────────────────────────

def _vol_block(net: float, rho: float, vol: float) -> Block:
    n = _f("m Netto",  str(net),  role=Role.NET_MASS); n.value = net
    r = _f("Dichte",   str(rho).replace(".", ","), role=Role.DENSITY); r.value = rho
    v = _f("V Netto",  str(vol),  role=Role.VOLUME);  v.value = vol
    return _b(n, r, v)

def test_volume_correct_with_density_field():
    # Code checks: V_expected = net * rho
    block = _vol_block(net=100.0, rho=1.81, vol=181.0)   # 100 * 1.81 = 181
    rule_volume(block)
    assert not any(fl.code == "CALC_VOLUME" for fl in block.role(Role.VOLUME).flags)

def test_volume_wrong_flagged():
    block = _vol_block(net=100.0, rho=1.81, vol=55.0)    # 100 * 1.81 = 181 ≠ 55
    rule_volume(block)
    assert any(fl.code == "CALC_VOLUME" for fl in block.role(Role.VOLUME).flags)

def test_volume_missing_net_skipped():
    r = _f("Dichte", "1,81", role=Role.DENSITY); r.value = 1.81
    v = _f("V Netto", "181", role=Role.VOLUME);  v.value = 181.0
    block = _b(r, v)
    rule_volume(block)
    assert not v.flags

def test_volume_missing_vol_skipped():
    n = _f("m Netto", "100", role=Role.NET_MASS); n.value = 100.0
    block = _b(n)
    rule_volume(block)
    assert not n.flags

def test_volume_zero_density_skipped():
    block = _vol_block(net=100.0, rho=0.0, vol=0.0)
    rule_volume(block)
    assert not block.role(Role.VOLUME).flags

def test_volume_density_from_label():
    n = _f("m Netto", "100", role=Role.NET_MASS); n.value = 100.0
    # No explicit density field; density in label (ρ = 1,81 kg/L)
    v = _f("V Netto (V = m / ρ; ρ = 1,81 kg/L)", "181", role=Role.VOLUME); v.value = 181.0
    block = _b(n, v)
    rule_volume(block)
    # 100 * 1.81 = 181 -> no flag
    assert not any(fl.code == "CALC_VOLUME" for fl in v.flags)


# ── rule_end_after_start ──────────────────────────────────────────────────────

def _time_block(start: time, end: time) -> tuple[Block, Field]:
    sf = _f("Start", start.strftime("%H:%M"), role=Role.HOLD_START); sf.value = start
    ef = _f("Ende",  end.strftime("%H:%M"),   role=Role.HOLD_END);   ef.value = end
    return _b(sf, ef), ef

def test_end_after_start_clean():
    block, ef = _time_block(time(8, 0), time(10, 0))
    rule_end_after_start(block)
    assert not any(fl.code == "TIME_END_AFTER_START" for fl in ef.flags)

def test_end_before_start_flagged():
    block, ef = _time_block(time(10, 0), time(8, 0))
    rule_end_after_start(block)
    assert any(fl.code == "TIME_END_AFTER_START" for fl in ef.flags)

def test_end_equal_start_flagged():
    block, ef = _time_block(time(10, 0), time(10, 0))
    rule_end_after_start(block)
    assert any(fl.code == "TIME_END_AFTER_START" for fl in ef.flags)

def test_end_after_start_dates():
    sf = _f("Start", "2026-06-10", role=Role.HOLD_START); sf.value = date(2026, 6, 10)
    ef = _f("Ende",  "2026-06-11", role=Role.HOLD_END);   ef.value = date(2026, 6, 11)
    block = _b(sf, ef)
    rule_end_after_start(block)
    assert not ef.flags

def test_end_after_start_missing_start_skipped():
    ef = _f("Ende", "10:00", role=Role.HOLD_END); ef.value = time(10, 0)
    block = _b(ef)
    rule_end_after_start(block)
    assert not ef.flags

def test_end_after_start_type_mismatch_skipped():
    # start=time, end=date -> different types -> no check
    sf = _f("Start", "08:00", role=Role.HOLD_START); sf.value = time(8, 0)
    ef = _f("Ende",  "2026-06-11", role=Role.HOLD_END); ef.value = date(2026, 6, 11)
    block = _b(sf, ef)
    rule_end_after_start(block)
    assert not ef.flags


# ── rule_duration ─────────────────────────────────────────────────────────────

def _dur_block(start: time, end: time, duration: time) -> tuple[Block, Field]:
    sf  = _f("Start",             start.strftime("%H:%M")); sf.value  = start
    ef  = _f("Ende",              end.strftime("%H:%M"));   ef.value  = end
    df  = _f("Dauer tatsächlich", duration.strftime("%H:%M")); df.value = duration
    return _b(sf, ef, df), df

def test_duration_correct():
    block, df = _dur_block(time(11, 27), time(12, 27), time(1, 0))
    rule_duration(block)
    assert not any(fl.code == "CALC_DURATION" for fl in df.flags)

def test_duration_wrong_flagged():
    block, df = _dur_block(time(11, 27), time(12, 27), time(2, 0))   # 2h, should be 1h
    rule_duration(block)
    assert any(fl.code == "CALC_DURATION" for fl in df.flags)

def test_duration_midnight_crossing():
    # 23:00 -> 01:00 = 2 hours
    block, df = _dur_block(time(23, 0), time(1, 0), time(2, 0))
    rule_duration(block)
    assert not any(fl.code == "CALC_DURATION" for fl in df.flags)

def test_duration_1min_tolerance():
    # 1-minute tolerance is allowed
    block, df = _dur_block(time(11, 0), time(12, 0), time(0, 59))   # 1 min short
    rule_duration(block)
    assert not any(fl.code == "CALC_DURATION" for fl in df.flags)

def test_duration_missing_end_skipped():
    sf = _f("Start",             "08:00"); sf.value = time(8, 0)
    df = _f("Dauer tatsächlich", "01:00"); df.value = time(1, 0)
    block = _b(sf, df)
    rule_duration(block)
    assert not df.flags


# ── rule_presence ─────────────────────────────────────────────────────────────

def test_presence_blank_sig_flagged():
    f = _f("Bearbeitet", "", role=Role.SIGNATURE_PROCESSED)
    block = _b(f)
    rule_presence(block)
    assert any(fl.code == "MISSING_SIGNATURE" for fl in f.flags)

def test_presence_full_sig_clean():
    f = _f("Bearbeitet", "10.06.2026 / ohe", role=Role.SIGNATURE_PROCESSED)
    block = _b(f)
    rule_presence(block)
    assert not any(fl.code == "MISSING_SIGNATURE" for fl in f.flags)

def test_presence_date_only_sig_incomplete():
    f = _f("Bearbeitet", "10.06.2026", role=Role.SIGNATURE_PROCESSED)
    block = _b(f)
    rule_presence(block)
    assert any(fl.code == "SIG_INCOMPLETE" for fl in f.flags)

def test_presence_kuerzel_only_sig_incomplete():
    f = _f("Bearbeitet", "/ ohe", role=Role.SIGNATURE_PROCESSED)
    block = _b(f)
    rule_presence(block)
    assert any(fl.code == "SIG_INCOMPLETE" for fl in f.flags)

def test_presence_ja_sig_not_flagged():
    # "Ja" in a sig-role field (checkbox-style) -> not a missing signature
    f = _f("GMP geprüft", "Ja", role=Role.SIGNATURE_PROCESSED)
    block = _b(f)
    rule_presence(block)
    assert not any(fl.code in ("MISSING_SIGNATURE", "SIG_INCOMPLETE") for fl in f.flags)

def test_presence_unmarked_checkbox_flagged():
    f = _f("GMP Check", ""); f.value_type = "checkbox"
    block = _b(f)
    rule_presence(block)
    assert any(fl.code == "MISSING_CHECKMARK" for fl in f.flags)

def test_presence_void_marks_flagged():
    for void in ("/", "-", "—", ".", "()", "[]", "n/a"):
        f = _f("Check", void); f.value_type = "checkbox"
        rule_presence(_b(f))
        assert any(fl.code == "MISSING_CHECKMARK" for fl in f.flags), f"void {void!r} not flagged"

def test_presence_marked_checkbox_clean():
    for marked in ("Ja", "Nein", "931", "x", "✓"):
        f = _f("Check", marked); f.value_type = "checkbox"
        rule_presence(_b(f))
        assert not any(fl.code == "MISSING_CHECKMARK" for fl in f.flags), f"{marked!r} should be clean"

def test_presence_empty_box_glyph_flagged():
    # "O Ja" = empty circle in front -> NOT checked
    f = _f("Proben", "O Ja"); f.value_type = "checkbox"
    block = _b(f)
    rule_presence(block)
    assert any(fl.code == "MISSING_CHECKMARK" for fl in f.flags)

def test_presence_blank_required_value_flagged():
    # The keyword regex uses \b word boundaries; "Datum" is standalone -> matches
    f = _f("Datum", "")   # 'datum' keyword, blank value -> expects value
    block = _b(f)
    rule_presence(block)
    assert any(fl.code == "MISSING_VALUE" for fl in f.flags)

def test_presence_blank_charge_number_flagged():
    f = _f("Charge Nummer", "")   # 'charge' keyword standalone -> expects value
    block = _b(f)
    rule_presence(block)
    assert any(fl.code == "MISSING_VALUE" for fl in f.flags)

def test_presence_blank_with_soll_flagged():
    f = _f("Beliebiges Feld", ""); f.soll = "8 - 12"   # has Soll -> expects value
    block = _b(f)
    rule_presence(block)
    assert any(fl.code == "MISSING_VALUE" for fl in f.flags)

def test_presence_blank_optional_value_clean():
    f = _f("Bemerkung", "")   # no keyword, no Soll -> not required
    block = _b(f)
    rule_presence(block)
    assert not any(fl.code == "MISSING_VALUE" for fl in f.flags)

def test_presence_na_chapter_skips_all():
    sig = _f("Bearbeitet", "", role=Role.SIGNATURE_PROCESSED)
    na  = _f("Kapitel", "Abschnitt findet keine Anwendung")
    block = _b(sig, na)
    rule_presence(block)
    # "keine anwendung" in any field value -> entire presence check skipped
    assert not any(fl.code == "MISSING_SIGNATURE" for fl in sig.flags)

def test_presence_section_already_signed_suppresses_duplicate():
    # If one sig field is signed, another blank with same role is a dup (artifact)
    signed = _f("Bearbeitet row 1", "10.06.2026 / ohe", role=Role.SIGNATURE_PROCESSED)
    blank  = _f("Bearbeitet row 2", "",                  role=Role.SIGNATURE_PROCESSED)
    block = _b(signed, blank)
    rule_presence(block)
    # The blank duplicate is suppressed because the role is already satisfied
    assert not any(fl.code == "MISSING_SIGNATURE" for fl in blank.flags)
