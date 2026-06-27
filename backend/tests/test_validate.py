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
    # p36: signature dated 05.06.2026, before the record's print date (2026-06-09)
    assert "DATE_BEFORE_PRINT" in codes
    # p36: signature Kuerzel 'abc' is not in the personnel registry {han, ohe}
    assert "KUERZEL_UNKNOWN" in codes
    # p38: 'Uebertrag Kapitel 5.3.1' carried value mismatches the source on p11
    assert "XREF_CARRIED_MATCH" in codes


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


def _sig(role, kuerzel, conf):
    from app.pipeline.model import Field, Read
    f = Field(page_no=1, chapter="", role=role, label_raw="Bearbeitet: (Datum/Kürzel)",
              value_raw=f"10.06.2026 / {kuerzel}")
    f.reads = [Read(model="x", value_raw=f.value_raw, confidence=conf)]
    return f


def test_four_eyes_requires_legible_reads():
    """Two sign-offs matching the same Kürzel = a violation ONLY when both are
    legibly read. A low-confidence match is likely an OCR collision (two different
    scrawls flattened onto one Kürzel), so it must NOT assert 'same person'."""
    from app.domain.roles import Role
    from app.pipeline.model import Block
    from app.pipeline.validate.rules import rule_four_eyes

    legible = Block(chapter="", page_no=1, template="signature")
    legible.fields = [_sig(Role.SIGNATURE_PROCESSED, "ohe", 0.92),
                      _sig(Role.SIGNATURE_CHECKED, "ohe", 0.90)]
    rule_four_eyes(legible)
    assert any(fl.code == "4EYES_DISTINCT" for f in legible.fields for fl in f.flags)

    illegible = Block(chapter="", page_no=1, template="signature")
    illegible.fields = [_sig(Role.SIGNATURE_PROCESSED, "ohe", 0.92),
                        _sig(Role.SIGNATURE_CHECKED, "ohe", 0.40)]   # Geprüft illegible
    rule_four_eyes(illegible)
    assert not any(fl.code == "4EYES_DISTINCT" for f in illegible.fields for fl in f.flags)


def test_cross_field_label_formula():
    """A result whose formula is in its LABEL and references sibling fields is
    evaluated by substituting their values. Fires on mismatch, silent when it
    matches, and bails (no flag) when a variable can't be resolved."""
    from app.pipeline.model import Block, Document, Field
    from app.pipeline.normalize import normalize
    from app.pipeline.validate.rules import rule_cross_formula

    def nf(label, val):
        return Field(page_no=1, chapter="", role=None, label_raw=label, value_raw=val)

    FORMULA = "m Z1 [g] = m Cake [kg] / 2 kg/L × c Z1 [g/L]"   # 50/2*4 = 100

    def run(result_val, with_inputs=True):
        fs = [nf(FORMULA, result_val)]
        if with_inputs:
            fs += [nf("m Cake [kg]", "50"), nf("c Z1 [g/L]", "4")]
        b = Block(chapter="", page_no=1, template="t"); b.fields = fs
        doc = Document(doc_no="x", title="x"); doc.blocks = [b]
        normalize(doc); rule_cross_formula(b)
        return {fl.code for f in b.fields for fl in f.flags}

    assert "CALC_FORMULA" in run("120")                         # 120 != 100 -> error
    assert not (run("100") & {"CALC_FORMULA", "CALC_ROUNDING"})  # matches -> silent
    assert not run("120", with_inputs=False)                    # unresolved vars -> no flag


def test_stat_outlier_flags_value_far_from_peers():
    """Anomaly detection: a numeric value beyond k std of its role-peers is flagged
    STAT_OUTLIER (leave-one-out, so the outlier can't mask itself). Normal values
    and small samples are left alone."""
    from app.domain.roles import Role
    from app.pipeline.model import Block, Document, Field
    from app.pipeline.validate.rules import rule_stat_outlier

    def vol(val):
        f = Field(page_no=1, chapter="", role=Role.VOLUME, label_raw="V Netto", value_raw=str(val))
        f.value = float(val)
        f.value_type = "number"
        return f

    b = Block(chapter="", page_no=1, template="t")
    b.fields = [vol(180), vol(185), vol(190), vol(195), vol(700)]   # 700 is the outlier
    doc = Document(doc_no="x", title="x"); doc.blocks = [b]
    rule_stat_outlier(doc)
    flagged = {f.value_raw for f in b.fields for fl in f.flags if fl.code == "STAT_OUTLIER"}
    assert flagged == {"700"}, flagged


def test_date_year_suspect_without_print_date():
    """A lone wrong-year date (2025 among 2026) must be caught even when the doc has
    NO print date — using the document's own modal batch year as the reference."""
    from app.domain.roles import Role
    from app.pipeline.model import Block, Document, Field
    from app.pipeline.normalize import normalize
    from app.pipeline.validate.engine import validate

    def sig(role, v):
        return Field(page_no=1, chapter="", role=role,
                     label_raw="Bearbeitet: (Datum/Kürzel)", value_raw=v)

    b = Block(chapter="", page_no=1, template="signature")
    b.fields = [
        sig(Role.SIGNATURE_PROCESSED, "10.06.2026 / ole"),
        sig(Role.SIGNATURE_CHECKED, "10.06.2026 / han"),
        sig(Role.SIGNATURE_PROCESSED, "10.06.2025 / ole"),   # wrong year
    ]
    doc = Document(doc_no="x", title="x")                     # generated_at=None -> no print date
    doc.blocks = [b]
    normalize(doc)
    validate(doc)
    codes = {fl.code for f in doc.all_fields() for fl in f.flags}
    assert "DATE_YEAR_SUSPECT" in codes


def test_kuerzel_resolves_by_name_initials():
    """'hm' is equidistant from registered 'han' and 'ohe' — pure edit distance
    can't choose. The name 'Hans Mustermann' (initials hm) breaks the tie -> han,
    so it is NOT collapsed onto Olg Herold's 'ohe' (which would be a false 4-eyes)."""
    from app.domain.roles import Role
    from app.pipeline.model import Block, Document, Field
    from app.pipeline.resolve import resolve

    def rf(page, label, val, role=None):
        return Field(page_no=page, chapter="", role=role, label_raw=label, value_raw=val)

    roster = Block(chapter="", page_no=4, template="roster")
    roster.fields = [rf(4, "Name Mitarbeiter (Zeile 1)", "Hans Mustermann"),
                     rf(4, "Kürzel (Zeile 1)", "han"),
                     rf(4, "Name Mitarbeiter (Zeile 2)", "Olg Herold-Sithimic"),
                     rf(4, "Kürzel (Zeile 2)", "ohe")]
    sig = Block(chapter="", page_no=25, template="signature")
    g = rf(25, "Geprüft: (Datum/Kürzel)", "10.06.2026 / hm", role=Role.SIGNATURE_CHECKED)
    sig.fields = [g]

    doc = Document(doc_no="x", title="x")
    doc.blocks = [roster, sig]
    resolve(doc)
    assert g.value_raw.strip().endswith("/ han"), g.value_raw
