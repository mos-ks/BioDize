"""Regression tests for checkbox scoring semantics (app/evaluation/scorer.py).

Locks in the fixes that lifted checkbox accuracy 74% -> 96% without a reprocess:
  1. "Nein" / "Kein Einsatz" are valid SELECTED options (a checked box), never
     "unchecked" — the scorer must compare the captured option, not truthiness.
  2. A parenthetical hint like "(Soll: Pre)" / "(GMP)" is NOT a checkbox option and
     must not be parsed as one.
  3. A per-option split group ("294/869/931/…" plus a separate "Ja") matches the
     sibling whose VALUE holds the gold option, not whichever row is closest in
     label length.
And the safety net: a genuinely blank box that we read as "Ja" is still scored wrong.
"""
from __future__ import annotations

import json

from app.evaluation.scorer import _label_option, score_ground_truth
from app.pipeline.model import Block, Document, Field


def _doc(fields):
    b = Block(chapter="", page_no=1, template="t")
    for label, value, vtype in fields:
        f = Field(page_no=1, chapter="", role=None, label_raw=label, value_raw=value)
        f.value_type = vtype
        b.fields.append(f)
    d = Document(doc_no="d", title="t")
    d.blocks = [b]
    return d


def _cb(label, value, state):
    return {"label": label, "kind": "checkbox", "value": value,
            "checkbox_state": state, "signature_status": None, "is_blank": value == ""}


def _gold(tmp_path, fields):
    page = {"page": 1, "section": "", "fields": fields, "expected_violations": []}
    (tmp_path / "page_001.json").write_text(json.dumps(page), encoding="utf-8")
    return tmp_path


def _cb_acc(doc, gold_dir):
    return score_ground_truth(doc, gold_dir).as_dict()["aggregate"]["checkbox_acc"]


def test_label_option_ignores_parenthetical_hint():
    assert _label_option("Virusbereich (Soll: Pre)") is None
    assert _label_option("GMP-Bereich (GMP)") is None
    # A real trailing option suffix is still picked up.
    assert _label_option("GMP-Bereich (Pre) GMP - Ja") == "ja"


def test_negative_options_count_as_checked(tmp_path):
    gold = _gold(tmp_path, [
        _cb("Floor Scale - Einsatzbereit gemäß RL-SOP-00796", "Kein Einsatz", "checked"),
        _cb("Temperierung erforderlich", "Nein, Kapitel 5.4 findet keine Anwendung", "checked"),
    ])
    doc = _doc([
        ("Floor Scale - Einsatzbereit gemäß RL-SOP-00796", "Kein Einsatz", "checkbox"),
        ("Temperierung erforderlich", "Nein, Kapitel 5.4 findet keine Anwendung", "checkbox"),
    ])
    assert _cb_acc(doc, gold) == 1.0


def test_soll_hint_not_treated_as_option(tmp_path):
    gold = _gold(tmp_path, [_cb("Virusbereich (Soll: Pre)", "Ja", "checked")])
    doc = _doc([("Virusbereich", "Ja", "checkbox")])
    assert _cb_acc(doc, gold) == 1.0


def test_per_option_group_matches_by_value(tmp_path):
    # 'GMP-Bereich aktiv'=Ja is the label-length-closest row to the gold "931"
    # field; the correct match must instead use the sibling holding "931".
    gold = _gold(tmp_path, [
        _cb("GMP-Bereich (Pre) - Auswahl (294/869/931/281)", "931", "checked"),
        _cb("GMP-Bereich aktiv", "Ja", "checked"),
    ])
    doc = _doc([
        ("GMP-Bereich (Pre)", "931", "checkbox"),
        ("GMP-Bereich aktiv", "Ja", "checkbox"),
    ])
    assert _cb_acc(doc, gold) == 1.0


def test_blank_box_read_as_checked_is_still_wrong(tmp_path):
    gold = _gold(tmp_path, [_cb("Homogenisieren durchgeführt", "", "unchecked")])
    doc = _doc([("Homogenisieren durchgeführt", "Ja", "checkbox")])
    assert _cb_acc(doc, gold) == 0.0
