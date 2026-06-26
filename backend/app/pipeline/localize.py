"""Localize: bind each extracted value to OCR word polygons → the field bbox.

General VLMs cannot box reliably, so the on-screen rectangle for the review UI
comes from the OCR engine's geometry. We match the field's value against the OCR
words and union the matched polygons.

Matching ladder (handwritten numbers need this — exact substring fails on
comma/dot and split tokens):
  1. exact text equality
  2. digit-normalized equality ("4,50" == "4.50" == "450")
  3. guarded digit containment (only for >=3 digits, to avoid "4,50" in "14,50")

If the extractor already provided a bbox (e.g. the stub fixture), keep it.
"""
from __future__ import annotations

import re

from app.pipeline.model import BBox, Document
from app.pipeline.ocr.base import OcrResult


def _digits(s: str) -> str:
    return re.sub(r"[^0-9]", "", s or "")


def localize(doc: Document, ocr_by_page: dict[int, OcrResult]) -> Document:
    for fld in doc.all_fields():
        if fld.bbox is not None:
            continue
        ocr = ocr_by_page.get(fld.page_no)
        if not ocr or not ocr.words or not fld.value_raw:
            continue

        val = fld.value_raw.strip()
        target = _digits(val)
        matched = [w for w in ocr.words if w.text and val == w.text.strip()]
        if not matched and target:
            matched = [w for w in ocr.words if _digits(w.text) == target]
        if not matched and len(target) >= 3:
            matched = [w for w in ocr.words if target in _digits(w.text)]
        if matched:
            fld.bbox = _union([w.bbox for w in matched])
            confs = [w.confidence for w in matched if w.confidence]
            if confs:
                fld.ocr_confidence = sum(confs) / len(confs)
    return doc


def _union(boxes: list[BBox]) -> BBox:
    return BBox(
        x0=min(b.x0 for b in boxes), y0=min(b.y0 for b in boxes),
        x1=max(b.x1 for b in boxes), y1=max(b.y1 for b in boxes),
    )
