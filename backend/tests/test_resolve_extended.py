"""Unit tests for resolve.py (previously 0% coverage).

Covers: _edits, _split_sig, _name_initials, roster_persons, canonical_signers,
resolve_kuerzel.
"""
from __future__ import annotations
import pytest
from app.pipeline.model import Block, Document, Field
from app.pipeline.resolve import (
    _edits, _name_initials, _split_sig, canonical_signers,
    resolve_kuerzel, roster_persons,
)
from app.domain.roles import Role


# ── Helpers ───────────────────────────────────────────────────────────────────

def _f(label: str, value: str, role=None, **kw) -> Field:
    return Field(page_no=1, chapter="", role=role, label_raw=label, value_raw=value, **kw)

def _b(*fields: Field) -> Block:
    b = Block(chapter="", page_no=1, template="x")
    b.fields = list(fields)
    return b

def _doc(*fields: Field) -> Document:
    doc = Document(doc_no="d", title="t")
    doc.blocks = [_b(*fields)]
    return doc

def _sig(kz: str, date: str = "10.06.2026") -> Field:
    return _f("Bearbeitet", f"{date} / {kz}", role=Role.SIGNATURE_PROCESSED)

def _roster(*entries) -> Document:
    """entries = [(zeile, kuerzel, name)]"""
    fields = []
    for zeile, kz, name in entries:
        fields.append(_f(f"Kürzel (Zeile {zeile})", kz))
        fields.append(_f(f"Name Mitarbeiter (Zeile {zeile})", name))
    return _doc(*fields)


# ── _edits ────────────────────────────────────────────────────────────────────

def test_edits_identical():
    assert _edits("ohe", "ohe") == 0

def test_edits_one_substitution():
    assert _edits("ohe", "ohp") == 1   # e -> p

def test_edits_one_insertion():
    assert _edits("ohe", "ohep") == 1

def test_edits_one_deletion():
    assert _edits("ohep", "ohe") == 1

def test_edits_two_subs():
    assert _edits("ohe", "abc") == 3   # all three differ

def test_edits_length_diff_triggers_early_exit():
    # abs("a"-"abcde") = 4 > cap=2 -> returns cap+1 = 3
    assert _edits("a", "abcde", cap=2) == 3   # cap+1

def test_edits_empty_strings():
    assert _edits("", "") == 0
    assert _edits("", "abc") == 3
    assert _edits("abc", "") == 3

def test_edits_symmetric():
    assert _edits("han", "hau") == _edits("hau", "han")


# ── _split_sig ────────────────────────────────────────────────────────────────

def test_split_sig_full_signature():
    date, kz = _split_sig("10.06.2026 / ohe")
    assert date == "10.06.2026"
    assert kz == "ohe"

def test_split_sig_no_kuerzel():
    date, kz = _split_sig("10.06.2026")
    assert date == "10.06.2026"
    assert kz is None

def test_split_sig_empty():
    date, kz = _split_sig("")
    assert kz is None

def test_split_sig_whitespace():
    date, kz = _split_sig("   ")
    assert kz is None

def test_split_sig_two_char_kuerzel():
    _, kz = _split_sig("10.06.2026 / ab")
    assert kz == "ab"

def test_split_sig_numeric_kuerzel_rejected():
    _, kz = _split_sig("10.06.2026 / 123")
    assert kz is None   # digits not in [a-zäöüß]{2,5}

def test_split_sig_too_long_kuerzel_rejected():
    _, kz = _split_sig("10.06.2026 / toolongkz")
    assert kz is None

def test_split_sig_kuerzel_lowercased():
    # Code lowercases before matching regex, so "OHE" -> "ohe" (valid)
    _, kz = _split_sig("10.06.2026 / OHE")
    assert kz == "ohe"


# ── _name_initials ────────────────────────────────────────────────────────────

def test_name_initials_two_parts():
    assert _name_initials("Olga Herold") == "oh"

def test_name_initials_hyphenated():
    assert _name_initials("Olg Herold-Sithimic") == "ohs"

def test_name_initials_three_parts():
    assert _name_initials("Hans Albert Neumann") == "han"

def test_name_initials_single_name():
    assert _name_initials("Hans") == "h"

def test_name_initials_empty():
    assert _name_initials("") == ""

def test_name_initials_lowercase_input():
    assert _name_initials("anna beck") == "ab"


# ── roster_persons ────────────────────────────────────────────────────────────

def test_roster_persons_single_entry():
    doc = _roster(("1", "ohe", "Olga Herold"))
    assert roster_persons(doc) == {"ohe": "Olga Herold"}

def test_roster_persons_multiple_entries():
    doc = _roster(("1", "ohe", "Olga Herold"), ("2", "han", "Hans Neumann"))
    assert roster_persons(doc) == {"ohe": "Olga Herold", "han": "Hans Neumann"}

def test_roster_persons_empty_doc():
    doc = Document(doc_no="d", title="t"); doc.blocks = []
    assert roster_persons(doc) == {}

def test_roster_persons_missing_name_row_excluded():
    doc = _doc(_f("Kürzel (Zeile 1)", "ohe"))   # no matching Name row
    assert roster_persons(doc) == {}

def test_roster_persons_kuerzel_variant_spelling():
    # "Kuerzel" (no umlaut) should also be picked up
    doc = _doc(
        _f("Kuerzel (Zeile 1)", "ohe"),
        _f("Name Mitarbeiter (Zeile 1)", "Olga Herold"),
    )
    assert roster_persons(doc) == {"ohe": "Olga Herold"}

def test_roster_persons_ignores_datum_kuerzel_labels():
    # "Bearbeitet (Datum/Kürzel)" must NOT be treated as a roster entry
    doc = _doc(
        _f("Bearbeitet (Datum/Kürzel)", "10.06.2026 / ohe"),
        _f("Kürzel (Zeile 1)", "ohe"),
        _f("Name Mitarbeiter (Zeile 1)", "Olga Herold"),
    )
    mapping = roster_persons(doc)
    assert mapping == {"ohe": "Olga Herold"}   # only one entry, not two


# ── canonical_signers ────────────────────────────────────────────────────────

def test_canonical_signers_roster_only():
    doc = _roster(("1", "ohe", "Olga Herold"), ("2", "han", "Hans Neumann"))
    signers = canonical_signers(doc)
    assert set(signers) == {"ohe", "han"}

def test_canonical_signers_deduplicates_misread():
    # "ohp" edit-distance 1 from "ohe" -> same cluster; roster label "ohe" wins
    doc = _doc(
        _f("Kürzel (Zeile 1)", "ohe"),
        _sig("ohp"),
    )
    signers = canonical_signers(doc)
    assert len(signers) == 1
    assert "ohe" in signers

def test_canonical_signers_two_distinct_people():
    doc = _doc(
        _f("Kürzel (Zeile 1)", "ohe"),
        _f("Kürzel (Zeile 2)", "han"),
        _sig("ohe"),
        _sig("han"),
    )
    signers = canonical_signers(doc)
    assert len(signers) == 2

def test_canonical_signers_no_fields():
    doc = Document(doc_no="d", title="t"); doc.blocks = []
    assert canonical_signers(doc) == []

def test_canonical_signers_prefers_three_letter_kuerzel():
    # If no roster entry, prefer the most-frequent 3-letter reading
    doc = _doc(_sig("ohe"), _sig("ohe"), _sig("oh"))
    signers = canonical_signers(doc)
    assert "ohe" in signers   # 3-letter, more frequent


# ── resolve_kuerzel ───────────────────────────────────────────────────────────

def _resolve_with(roster_kz: list[str], raw_kz: str) -> Field:
    """Helper: build a doc, run resolve, return the signature field."""
    roster_fields = [_f(f"Kürzel (Zeile {i})", kz) for i, kz in enumerate(roster_kz, 1)]
    sig = _sig(raw_kz)
    doc = _doc(*roster_fields, sig)
    resolve_kuerzel(doc)
    return sig


def test_resolve_exact_match_unchanged():
    sig = _resolve_with(["ohe", "han"], "ohe")
    assert "ohe" in sig.value_raw
    assert not any(fl.code == "KUERZEL_UNRESOLVED" for fl in sig.flags)

def test_resolve_one_edit_snaps_to_roster():
    sig = _resolve_with(["ohe", "han"], "ohp")   # ohp -> ohe (1 edit)
    assert "ohe" in sig.value_raw
    assert not any(fl.code == "KUERZEL_UNRESOLVED" for fl in sig.flags)

def test_resolve_two_edits_snaps_when_unambiguous():
    sig = _resolve_with(["ohe", "zzz"], "ohx")   # ohx -> ohe (2), zzz (3) -> unambiguous
    assert "ohe" in sig.value_raw

def test_resolve_ambiguous_kuerzel_flagged():
    # "abyz" is edit-distance 2 from "abcd" (y!=c, z!=d) AND 2 from "wxyz" (a!=w, b!=x).
    # canonical_signers merges "abyz" into "abcd"'s cluster (first match, dist=2<=2),
    # leaving signers = ["abcd", "wxyz"]. resolve sees tied best_d=2, second_d=2,
    # second_d - best_d = 0 < 1 -> KUERZEL_UNRESOLVED.
    sig = _resolve_with(["abcd", "wxyz"], "abyz")
    assert any(fl.code == "KUERZEL_UNRESOLVED" for fl in sig.flags)

def test_resolve_no_roster_leaves_value_unchanged():
    sig = _sig("ohe")
    doc = _doc(sig)   # no Kürzel roster fields
    resolve_kuerzel(doc)
    assert "ohe" in sig.value_raw
    assert not sig.flags

def test_resolve_checked_field_not_in_sig_roles_ignored():
    # A field without a signature role should not be processed
    f = _f("GMP Bereich", "10.06.2026 / ohe", role=None)
    roster = _f("Kürzel (Zeile 1)", "ohe")
    doc = _doc(roster, f)
    resolve_kuerzel(doc)
    assert not f.flags   # not a sig role -> skipped

def test_resolve_confidence_lifted_on_registry_match():
    sig = _resolve_with(["ohe", "han"], "ohp")   # 1-edit match
    assert (sig.ocr_confidence or 0) >= 0.90
