"""Deterministic stub OCR engine.

Returns no words (the StubExtractor already carries its own bboxes). A real
engine — Azure Document Intelligence Read for the cloud dev phase, or dots.ocr /
PaddleOCR-VL / Surya on-prem — implements `recognize()` to emit word polygons +
confidence, and `localize.py` does the value->box binding.
"""
from __future__ import annotations

from app.pipeline.ocr.base import OcrEngine, OcrResult


class StubOcr(OcrEngine):
    name = "stub-ocr"

    def recognize(self, image_path: str | None, page_no: int) -> OcrResult:
        return OcrResult(page_no=page_no, words=[])
