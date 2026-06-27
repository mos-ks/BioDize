"""New detections: kaufmännische Rundung, identifier consistency, and the
solution-format export's Condition verdict mapping."""
from types import SimpleNamespace as NS

from app.pipeline.export import solution_condition, solution_text_value
from app.pipeline.model import Block, Document, Field
from app.pipeline.validate.rules import rule_formula, rule_identifier_consistency


def _f(label, value, **kw):
    return Field(page_no=1, chapter="", role=None, label_raw=label, value_raw=value, **kw)


# --- kaufmännische Rundung (round half away from zero) -----------------------

def test_kaufmaennische_rundung_flags_wrong_direction():
    # 3/2 = 1.5; kaufmännisch to 0 places = 2. Writing "1" is a Rundungsfehler.
    wrong = _f("x", "1", calc_expr="3 / 2"); wrong.value = 1.0; wrong.nks = 0
    assert any(fl.code == "CALC_ROUNDING" for fl in rule_formula(wrong))
    # The correct kaufmännisch value passes clean.
    ok = _f("x", "2", calc_expr="3 / 2"); ok.value = 2.0; ok.nks = 0
    assert rule_formula(ok) == []
    # A big mismatch is still a hard formula error.
    bad = _f("x", "9", calc_expr="3 / 2"); bad.value = 9.0; bad.nks = 0
    assert any(fl.code == "CALC_FORMULA" for fl in rule_formula(bad))


# --- identifier consistency across the record -------------------------------

def test_identifier_consistency_flags_the_drifting_one():
    b = Block(chapter="", page_no=1, template="x")
    b.fields = [_f("Batch No.", "1234567"), _f("Batch No.", "1234567"), _f("Batch No.", "1234568")]
    doc = Document(doc_no="d", title="t"); doc.blocks = [b]
    rule_identifier_consistency(doc)
    codes = [fl.code for x in doc.all_fields() for fl in x.flags]
    assert codes.count("CONSISTENCY_MISMATCH") == 1  # only the odd one out is flagged


def test_identifier_consistency_clean_when_all_equal():
    b = Block(chapter="", page_no=1, template="x")
    b.fields = [_f("Dok-Nr.", "AB-ABC-123456"), _f("Dok-Nr.", "AB-ABC-123456")]
    doc = Document(doc_no="d", title="t"); doc.blocks = [b]
    rule_identifier_consistency(doc)
    assert not any(x.flags for x in doc.all_fields())


# --- solution-format Condition verdict mapping ------------------------------

def _flag(code, sev):
    return NS(code=code, severity=sev)


def test_solution_condition_mapping():
    assert solution_condition(NS(flags=[], role="net_mass")) == "Online / confirmed by second value"
    assert solution_condition(NS(flags=[], role="text")) == "Online"
    assert solution_condition(NS(flags=[_flag("MISSING_SIGNATURE", "error")], role=None)) == "Suspect / missing"
    assert solution_condition(NS(flags=[_flag("CALC_NET_MASS", "error")], role="net_mass")) \
        == "Suspect / Value does not fit calculation"
    assert solution_condition(NS(flags=[_flag("CALC_VOLUME", "error")], role="volume")) \
        == "Suspect / Value does not fit volume calculation"
    assert solution_condition(NS(flags=[_flag("RANGE_SOLL", "error")], role=None)) == "Suspect / unexpected value"


def test_solution_text_value_checkbox_and_number():
    assert solution_text_value(NS(value_type="checkbox", value_raw="Ja", value_norm=None)) == ("Checked", None)
    assert solution_text_value(NS(value_type="checkbox", value_raw="", value_norm=None)) == ("Not checked", None)
    text, num = solution_text_value(NS(value_type=None, value_raw="200", value_norm="200"))
    assert num == 200.0
