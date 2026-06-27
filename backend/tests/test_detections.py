"""New detections: kaufmännische Rundung, identifier consistency, and the
solution-format export's Condition verdict mapping."""
from types import SimpleNamespace as NS

from app.pipeline.export import solution_condition, solution_text_value
from app.pipeline.model import Block, Document, Field
from app.pipeline.validate.rules import rule_formula, rule_identifier_consistency, rule_nks


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


# --- NKS / Nachkommastellen vs the form's required decimal places -----------

def test_nks_flags_dropped_decimal_place():
    # The form requires 2 decimals: '20,20' is right, '20,2' (1 dp) is flagged.
    bad = _f("m", "20,2"); bad.nks = 2
    assert any(fl.code == "FMT_NKS" for fl in rule_nks(bad))
    ok = _f("m", "20,20"); ok.nks = 2
    assert rule_nks(ok) == []
    # A calculated result must carry the required precision too: 585 vs '585,0'.
    calc = _f("V", "585"); calc.nks = 1
    assert any(fl.code == "FMT_NKS" for fl in rule_nks(calc))
    # No required NKS stated -> never flagged (avoids false positives like '220').
    free = _f("V", "220");
    assert rule_nks(free) == []


# --- crossed-out section consolidation --------------------------------------

def _struck(label, page, y):
    from app.pipeline.model import BBox
    from app.pipeline.validate.rules import rule_crossed_out
    fld = Field(page_no=page, chapter="", role=None, label_raw=label, value_raw="—")
    fld.bbox = BBox(0.1, y, 0.3, y + 0.03)
    fld.is_crossed_out = True
    for fl in rule_crossed_out(fld):
        fld.add_flag(fl)
    return fld


def test_crossed_out_section_collapses_to_one():
    from app.pipeline.validate.engine import consolidate_crossed_out
    b = Block(chapter="", page_no=4, template="x")
    b.fields = [_struck(f"cell{i}", 4, 0.2 + i * 0.05) for i in range(6)]
    doc = Document(doc_no="d", title="t"); doc.blocks = [b]
    consolidate_crossed_out(doc)
    n = sum(1 for x in doc.all_fields() for fl in x.flags if fl.code == "CROSSED_OUT")
    assert n == 1, f"a struck-through section should collapse to 1 flag, got {n}"


def test_crossed_out_keeps_individual_corrections():
    from app.pipeline.validate.engine import consolidate_crossed_out
    b = Block(chapter="", page_no=5, template="x")
    b.fields = [_struck("a", 5, 0.2), _struck("b", 5, 0.6)]  # only 2 -> left alone
    doc = Document(doc_no="d", title="t"); doc.blocks = [b]
    consolidate_crossed_out(doc)
    n = sum(1 for x in doc.all_fields() for fl in x.flags if fl.code == "CROSSED_OUT")
    assert n == 2


# --- verified (positive marker) ---------------------------------------------

def test_verified_marks_corroborated_handwritten_numbers():
    from app.pipeline.validate.engine import mark_verified

    def hw(label, raw, val, role=None):
        f = _f(label, raw); f.value = val; f.is_handwritten = True; f.role = role; return f

    a1 = hw("m", "12,6", 12.6, role="net_mass")
    a2 = hw("m", "12,6", 12.6, role="net_mass")          # same value twice -> 2nd-value
    c = hw("V", "220", 220.0); c.calc_expr = "200 * 1,1"  # calc result -> by calculation
    printed = _f("x", "5"); printed.value = 5.0; printed.is_handwritten = False
    b = Block(chapter="", page_no=1, template="x"); b.fields = [a1, a2, c, printed]
    doc = Document(doc_no="d", title="t"); doc.blocks = [b]
    mark_verified(doc)
    assert a1.is_verified and a2.is_verified and "second" in (a1.verified_reason or "")
    assert c.is_verified and "calc" in (c.verified_reason or "").lower()
    assert not printed.is_verified  # printed (black) numbers are not "verified"


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


# --- crossed-out (durchgestrichen) + handwritten focus ----------------------

def test_crossed_out_warns():
    from app.pipeline.validate.rules import rule_crossed_out
    f = _f("x", "10,5"); f.is_crossed_out = True
    assert any(fl.code == "CROSSED_OUT" for fl in rule_crossed_out(f))
    assert rule_crossed_out(_f("x", "10,5")) == []  # default not crossed out


def test_printed_clean_field_auto_accepts_handwritten_stays():
    from app.domain.severity import FieldStatus
    from app.pipeline.validate.uncertainty import score
    printed = _f("Production Code", "4756001"); printed.is_handwritten = False; printed.value = "4756001"
    hand = _f("m Netto", "200"); hand.is_handwritten = True; hand.value = 200; hand.reads = []
    b = Block(chapter="", page_no=1, template="x"); b.fields = [printed, hand]
    doc = Document(doc_no="d", title="t"); doc.blocks = [b]
    score(doc)
    assert printed.status == FieldStatus.AUTO_ACCEPTED       # printed (black) → out of the queue
    assert hand.status == FieldStatus.NEEDS_REVIEW           # handwritten (blue) → reviewed


# --- cross-document value history -------------------------------------------

def test_cross_doc_drift_flags_value_far_from_prior_records():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session as SASession
    from app.db.base import Base
    from app.db import models
    from app.pipeline import history

    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    db = SASession(eng)
    for v in (200.0, 201.0, 199.0, 200.0):  # this parameter has read ~200 before
        db.add(models.ParameterHistory(param_key="net_mass|m netto|kg", value=v, document_id="d_old"))
    db.commit()

    def doc_with(value):
        f = Field(page_no=1, chapter="", role="net_mass", label_raw="m Netto", value_raw=str(value), unit="kg")
        f.value = float(value)
        b = Block(chapter="", page_no=1, template="x"); b.fields = [f]
        d = Document(doc_no="d", title="t"); d.blocks = [b]
        return d, f

    drift_doc, drift_f = doc_with(350)
    history.check_consistency(drift_doc, db)
    assert any(fl.code == "CROSS_DOC_DRIFT" for fl in drift_f.flags)

    ok_doc, ok_f = doc_with(200)
    history.check_consistency(ok_doc, db)
    assert not ok_f.flags
    db.close()
