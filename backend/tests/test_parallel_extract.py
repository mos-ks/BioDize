"""Per-page VLM reads run concurrently (ThreadPoolExecutor), but the assembled
Document stays deterministic: blocks come out in page order regardless of completion
order, and one failing page degrades to empty instead of aborting the whole record.

Guards the concurrency added in "Parallelize VLM page reads and OCR across pages".
Mocks the network calls (_fetch_identity / _read_page), so no API key is needed.
"""
from __future__ import annotations

from app.pipeline.extract.vlm_exhaustive import VlmExhaustiveExtractor
from app.pipeline.ingest import PageImage


def _raw(pn: int) -> list[dict]:
    return [{"label": f"L{pn}", "kind": "value", "value": str(pn), "options": [], "selected": [],
             "unit": None, "nks": None, "soll": None, "calc_expr": None, "confidence": 0.9,
             "ypos": 0.5, "xpos": 0.5, "handwritten": True, "crossed_out": False, "is_blank": False}]


def _extractor() -> VlmExhaustiveExtractor:
    ex = VlmExhaustiveExtractor.__new__(VlmExhaustiveExtractor)  # skip the OpenAI client init
    ex._model = "test"
    return ex


def _pages(nums) -> list[PageImage]:
    return [PageImage(page_no=i, image_path=f"page{i}", is_blank=False) for i in nums]


def test_parallel_extract_assembles_in_page_order(monkeypatch):
    ex = _extractor()
    monkeypatch.setattr(ex, "_fetch_identity", lambda image_path: {})
    monkeypatch.setattr(ex, "_read_page", lambda image_path: _raw(int(image_path[4:])))
    doc = ex.extract(None, _pages((3, 1, 2)))  # deliberately out of order
    assert [b.page_no for b in doc.blocks] == [1, 2, 3]
    assert [b.fields[0].value_raw for b in doc.blocks] == ["1", "2", "3"]


def test_parallel_extract_one_failing_page_does_not_abort(monkeypatch):
    ex = _extractor()
    monkeypatch.setattr(ex, "_fetch_identity", lambda image_path: {})

    def read(image_path):
        pn = int(image_path[4:])
        if pn == 2:
            raise RuntimeError("model 500")
        return _raw(pn)

    monkeypatch.setattr(ex, "_read_page", read)
    doc = ex.extract(None, _pages((1, 2, 3)))
    assert [b.page_no for b in doc.blocks] == [1, 3]  # page 2 failed -> dropped, rest fine
