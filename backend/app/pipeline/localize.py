"""Localize: bind each extracted value to OCR word polygons → the field bbox.

General VLMs cannot box reliably, so the on-screen rectangle for the review UI
comes from the OCR engine's geometry. We string-match the field's value against
OCR `words[].text` and union the matched polygons.

If the extractor already provided a bbox (e.g. the stub fixture), keep it.
"""
from __future__ import annotations

from app.pipeline.model import BBox, Document
from app.pipeline.ocr.base import OcrResult


def localize(doc: Document, ocr_by_page: dict[int, OcrResult]) -> Document:
    for fld in doc.all_fields():
        if fld.bbox is not None:
            continue
        ocr = ocr_by_page.get(fld.page_no)
        if not ocr or not ocr.words:
            continue
        matched = [w for w in ocr.words if fld.value_raw and fld.value_raw in w.text]
        if matched:
            fld.bbox = _union([w.bbox for w in matched])
    return doc


def _union(boxes: list[BBox]) -> BBox:
    return BBox(
        x0=min(b.x0 for b in boxes), y0=min(b.y0 for b in boxes),
        x1=max(b.x1 for b in boxes), y1=max(b.y1 for b in boxes),
    )
