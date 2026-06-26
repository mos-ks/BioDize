"""Integration test: the stub pipeline catches the planted errors."""
from app.pipeline.extract.stub import StubExtractor
from app.pipeline.normalize import normalize
from app.pipeline.validate.engine import validate
from app.pipeline.validate.uncertainty import score


def _run():
    doc = StubExtractor().extract(None)
    normalize(doc)
    validate(doc)
    score(doc)
    return doc


def _codes(doc):
    return {fl.code for f in doc.all_fields() for fl in f.flags}


def test_planted_errors_are_caught():
    codes = _codes(_run())
    # p40: net 200 but gross - tare = 0
    assert "CALC_NET_MASS" in codes
    # p10 §5.2: Gepruft before Bearbeitet + same Kuerzel
    assert "4EYES_ORDER" in codes
    assert "4EYES_DISTINCT" in codes
    # p17: 32 above Soll 20-30
    assert "RANGE_SOLL" in codes
    # p40: "10.6.2026" not zero-padded
    assert "FMT_DATE_PADDING" in codes
    # p36: printed formula (6,6*45 - 4,3*0,75 = 293.775) vs recorded 2021,78
    assert "CALC_FORMULA" in codes
    # p36: signature dated 2016, before the record's print date (2026-06-09)
    assert "DATE_BEFORE_PRINT" in codes
    # p36: signature Kuerzel 'abc' is not in the personnel registry {han, ohe}
    assert "KUERZEL_UNKNOWN" in codes
    # p38: 'Uebertrag Kapitel 5.3.1' carried value mismatches the source on p11
    assert "XREF_MISMATCH" in codes


def test_clean_block_has_no_flags():
    doc = _run()
    # p11 mass balance is internally consistent (net=gross-tare, V=net*rho).
    p11 = [b for b in doc.blocks if b.page_no == 11][0]
    net = p11.role("net_mass")
    vol = p11.role("volume")
    assert not net.flags
    assert not vol.flags


def test_severity_two_categories_only():
    doc = _run()
    severities = {fl.severity.value for f in doc.all_fields() for fl in f.flags}
    assert severities <= {"error", "warning"}


def test_confidence_gate_sets_status():
    doc = _run()
    statuses = {f.status.value for f in doc.all_fields()}
    assert "needs_review" in statuses        # flagged/low-confidence fields
    # a clean, confident field should be auto-accepted
    assert "auto_accepted" in statuses
