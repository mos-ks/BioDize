"""Ground-truth accuracy test.

Run:  pytest tests/test_ground_truth.py -v
      python -m pytest tests/test_ground_truth.py --tb=short
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

GROUND_TRUTH_DIR = Path(__file__).parent.parent.parent / "ground_truth"
RESULTS_DIR      = Path(__file__).parent.parent.parent / "results"


def _run_stub_pipeline():
    """Run the full pipeline with the stub extractor and return Document."""
    from app.pipeline.extract.stub import StubExtractor
    from app.pipeline.normalize import normalize
    from app.pipeline.resolve import resolve
    from app.pipeline.validate.engine import validate
    from app.pipeline.validate.uncertainty import score

    doc = StubExtractor().extract()
    normalize(doc)
    resolve(doc)
    validate(doc)
    score(doc)
    return doc


def _run_results_pipeline():
    """Re-validate the pre-extracted real results JSON (no LLM needed)."""
    from app.pipeline.model import Block, BBox, Document, Field, Read
    from app.pipeline.normalize import normalize
    from app.pipeline.resolve import resolve
    from app.pipeline.validate.engine import validate
    from app.pipeline.validate.uncertainty import score

    data = json.loads((RESULTS_DIR / "extracted_fields.json").read_text(encoding="utf-8"))
    entries = data["fields"]
    doc = Document(doc_no="real", title="real", page_count=46)
    bmap: dict = {}
    for e in entries:
        chap = (e.get("chapter") or "").strip()
        pno  = e["page_no"]
        key  = (chap, pno)
        if key not in bmap:
            bmap[key] = Block(chapter=chap, page_no=pno, template="real")
        b = bmap[key]
        bbox_raw = e.get("bbox")
        bbox     = BBox(*bbox_raw) if bbox_raw and len(bbox_raw) == 4 else None
        val_raw  = str(e.get("value_raw") or e.get("value") or "")
        f = Field(page_no=pno, chapter=chap, role=e.get("role"),
                  label_raw=e.get("label") or "", value_raw=val_raw, bbox=bbox)
        # NOTE: the JSON "confidence" is the post-validation UNCERTAINTY SCORE
        # (a flagged field is dragged to ~0.4 *because* it was flagged) — NOT the
        # reader's legibility confidence. Feeding it back as Read.confidence is
        # circular (it would suppress every originally-flagged rule on re-validation).
        # The lossy export doesn't carry the original read confidence, so assume
        # legible here; the live pipeline uses the reader's real per-field value.
        f.reads = [Read(model="real", value_raw=val_raw, confidence=1.0)]
        b.fields.append(f); f.block_key = b.key
    doc.blocks = list(bmap.values())
    normalize(doc); resolve(doc); validate(doc); score(doc)
    return doc


@pytest.mark.skipif(not GROUND_TRUTH_DIR.exists(),
                    reason="ground_truth/ not found")
class TestGroundTruth:

    @pytest.fixture(scope="class")
    def report(self):
        from app.evaluation.scorer import score_ground_truth
        if RESULTS_DIR.joinpath("extracted_fields.json").exists():
            doc = _run_results_pipeline()
        else:
            doc = _run_stub_pipeline()
        return score_ground_truth(doc, GROUND_TRUTH_DIR)

    def test_rule_recall_ge_80(self, report):
        """At least 80% of expected violations must be detected."""
        a = report._agg()
        print(f"\nRule recall: {a['rule_recall']:.1%}")
        assert a["rule_recall"] >= 0.80, (
            f"Rule recall {a['rule_recall']:.1%} < 80%\n{report.summary()}"
        )

    def test_rule_precision_ge_50(self, report):
        """False-positive rate must stay manageable (>50% precision)."""
        a = report._agg()
        print(f"Rule precision: {a['rule_precision']:.1%}")
        assert a["rule_precision"] >= 0.50, (
            f"Rule precision {a['rule_precision']:.1%} < 50%\n{report.summary()}"
        )

    def test_value_accuracy_ge_80(self, report):
        a = report._agg()
        if a["value_acc"] is None:
            pytest.skip("No value fields to compare")
        print(f"Value accuracy: {a['value_acc']:.1%}")
        assert a["value_acc"] >= 0.80

    def test_checkbox_accuracy_ge_90(self, report):
        a = report._agg()
        if a["checkbox_acc"] is None:
            pytest.skip("No checkboxes to compare")
        print(f"Checkbox accuracy: {a['checkbox_acc']:.1%}")
        assert a["checkbox_acc"] >= 0.90

    def test_signature_accuracy_ge_90(self, report):
        a = report._agg()
        if a["signature_acc"] is None:
            pytest.skip("No signatures to compare")
        print(f"Signature accuracy (signed/blank): {a['signature_acc']:.1%}")
        assert a["signature_acc"] >= 0.90

    def test_print_full_report(self, report):
        """Always print the full report for visibility in CI."""
        print("\n" + report.summary())
        # save JSON result next to test
        out = Path(__file__).parent / "ground_truth_result.json"
        out.write_text(json.dumps(report.as_dict(), indent=2), encoding="utf-8")
        assert True   # always pass; metrics are in the other tests
