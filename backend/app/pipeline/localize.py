"""Localize: bind each extracted value to the SINGLE best OCR block box.

Mistral OCR returns one box per BLOCK (a table row / cell / paragraph) and
per-word confidence (no per-word box), so the on-screen rectangle is block-
granular. The job here is to pick the one best block for each field — never to
union every block that happens to contain a repeated value. The old union
behaviour produced page-tall smears (a date like "10.06.2026" repeats in many
signature rows) and made adjacent fields such as Bearbeitet/Geprüft share one
identical box.

Strategy, per page (so we can reserve blocks across same-page fields):
  1. value match — blocks whose text equals / digit-equals / tightly contains
     the value. Rank exact > digit-equal > digit-contains; break ties by
     not-already-used (so repeated dates land on distinct rows), then smallest
     area (a tight signature cell beats a whole-table block), then topmost.
  2. label anchor — if no value match (short values like "2", checkbox "Ja"),
     fall back to the block that contains the printed label, so the reviewer
     gets the right ROW instead of "no location".
A field with neither stays unlocalized (an honest "no location").

If the extractor already provided a bbox (e.g. the stub fixture), keep it.
"""
from __future__ import annotations

import re

from app.pipeline.model import BBox, Document
from app.pipeline.ocr.base import OcrResult, OcrWord


def _digits(s: str) -> str:
    return re.sub(r"[^0-9]", "", s or "")


def _norm(s: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace — for label matching."""
    s = re.sub(r"[^0-9a-zäöüß ]+", " ", (s or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def _area(b: BBox) -> float:
    return max(b.x1 - b.x0, 0.0) * max(b.y1 - b.y0, 0.0)


def localize(doc: Document, ocr_by_page: dict[int, OcrResult]) -> Document:
    by_page: dict[int, list] = {}
    for fld in doc.all_fields():
        by_page.setdefault(fld.page_no, []).append(fld)

    for page_no, fields in by_page.items():
        ocr = ocr_by_page.get(page_no)
        if not ocr or not ocr.words:
            continue
        blocks = ocr.words  # one OcrWord == one OCR block (box + full block text)
        used: set[int] = set()           # block indices already claimed on this page
        shared: dict[int, list] = {}     # block idx -> fields that landed on it

        for fld in fields:
            if fld.bbox is not None:
                continue  # extractor-provided geometry wins (stub fixture)
            picked = _best_block(fld, blocks, used)
            if picked is None:
                continue
            idx, block = picked
            fld.bbox = block.bbox
            if block.confidence:
                fld.ocr_confidence = block.confidence
            used.add(idx)
            shared.setdefault(idx, []).append(fld)

        # OCR sometimes returns a whole table as ONE block, so every field in it
        # collapses onto the same box. Split a shared, tall-enough block into
        # equal vertical bands in reading order so each field gets a distinct row.
        for idx, flds in shared.items():
            if len(flds) < 2:
                continue
            b = blocks[idx].bbox
            if (b.y1 - b.y0) < 0.05:
                continue  # too short to subdivide meaningfully
            step = (b.y1 - b.y0) / len(flds)
            for i, f in enumerate(flds):
                top = b.y0 + i * step
                f.bbox = BBox(b.x0, top, b.x1, top + step)
    return doc


def _best_block(fld, blocks: list[OcrWord], used: set[int]) -> tuple[int, OcrWord] | None:
    val = (fld.value_raw or "").strip()

    # 1. value match -----------------------------------------------------------
    if val:
        target = _digits(val)
        cands: list[tuple[int, int, float, float, int, OcrWord]] = []
        for idx, b in enumerate(blocks):
            bt = (b.text or "").strip()
            if not bt:
                continue
            rank: int | None = None
            if bt == val:
                rank = 0
            elif target and _digits(bt) == target:
                rank = 1
            elif len(target) >= 4 and target in _digits(bt):
                rank = 2
            if rank is not None:
                # sort key: rank, unused-first, smallest-area, topmost
                cands.append((rank, 1 if idx in used else 0, _area(b.bbox), b.bbox.y0, idx, b))
        if cands:
            cands.sort(key=lambda c: (c[0], c[1], c[2], c[3]))
            best = cands[0]
            return best[4], best[5]

    # 2. label anchor (short / unmatchable values) -----------------------------
    label = _norm(fld.label_raw)
    if len(label) >= 4:
        lcands: list[tuple[int, float, int, OcrWord]] = []
        for idx, b in enumerate(blocks):
            if label in _norm(b.text):
                lcands.append((1 if idx in used else 0, _area(b.bbox), idx, b))
        if lcands:
            lcands.sort(key=lambda c: (c[0], c[1]))  # unused first, then smallest
            best = lcands[0]
            return best[2], best[3]

    return None
