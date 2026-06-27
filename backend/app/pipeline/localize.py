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

from app.domain.severity import Category, Severity
from app.pipeline.model import BBox, Document, Flag
from app.pipeline.ocr.base import OcrResult, OcrWord


def ocr_crosscheck(doc: Document, ocr_by_page: dict[int, OcrResult]) -> Document:
    """Ensemble cross-read: the VLM read the value, the OCR engine read the page
    independently. Where a numeric value is contradicted by the OCR — the OCR has
    a same-length near-miss (e.g. VLM '123' but OCR '127') — flag it for a human.
    Conservative on purpose (only clear, corroborated disagreements)."""
    for f in doc.all_fields():
        v = (f.value_raw or "").strip().replace(" ", "")
        if not re.fullmatch(r"\d{3,}([.,]\d+)?", v):     # pure number, 3+ digits
            continue
        target = re.sub(r"\D", "", v)
        ocr = ocr_by_page.get(f.page_no)
        if not ocr or not ocr.words:
            continue
        nums = {m for w in ocr.words for m in re.findall(r"\d{2,}", w.text or "")}
        if target in nums:
            continue                                     # OCR corroborates the VLM
        near = [n for n in nums if len(n) == len(target)
                and sum(a != b for a, b in zip(n, target)) == 1]
        if near:
            f.add_flag(Flag(Severity.WARNING, Category.EXTRACTION, "EXTRACT_DISAGREEMENT",
                            f"VLM read '{f.value_raw}' but OCR read '{near[0]}' — readers disagree, verify",
                            expected=near[0], actual=f.value_raw))
    return doc


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
            b = block.bbox
            yp = fld.vlm_ypos
            # Mistral often returns a whole TABLE as one (tall) block, so the block
            # box alone would draw a page-tall smear. When we have the reader's
            # vertical estimate, narrow a tall block down to a thin row band centered
            # on that field's actual row — keeps the block's reliable x extent, fixes
            # the y. Short blocks (a tight cell) are already exact, so trust them.
            if yp is not None and (b.y1 - b.y0) > _ROW_TALL:
                cy = min(max(yp, b.y0 + _ROW_HALF), b.y1 - _ROW_HALF)
                fld.bbox = BBox(b.x0, cy - _ROW_HALF, b.x1, cy + _ROW_HALF)
            else:
                fld.bbox = b
            if block.confidence:
                fld.ocr_confidence = block.confidence
            used.add(idx)
            shared.setdefault(idx, []).append(fld)

        for idx, flds in shared.items():
            b = blocks[idx].bbox
            # X-split: a FULL-WIDTH row that several cells collapsed onto (a table
            # row) — narrow each cell's box to its COLUMN using the reader's xpos,
            # so the box sits on the value, not across the whole row.
            if len(flds) >= 2 and (b.x1 - b.x0) > _COL_WIDE:
                for f in flds:
                    if f.vlm_xpos is None or f.bbox is None:
                        continue
                    hw = _col_half(f.value_raw)
                    cx = min(max(f.vlm_xpos, b.x0 + hw), b.x1 - hw)
                    f.bbox = BBox(cx - hw, f.bbox.y0, cx + hw, f.bbox.y1)

            # Y fallback: fields with NO vertical estimate that still collapsed onto a
            # shared tall block — split it into equal vertical bands in reading order.
            no_yp = [f for f in flds if f.vlm_ypos is None]
            if len(no_yp) >= 2 and (b.y1 - b.y0) >= 0.05:
                step = (b.y1 - b.y0) / len(no_yp)
                for i, f in enumerate(no_yp):
                    top = b.y0 + i * step
                    f.bbox = BBox(f.bbox.x0, top, f.bbox.x1, top + step)
    return doc


# A block taller than this many page-fractions spans multiple rows (a table), so
# its box must be narrowed to the field's row. A typical handwritten row is ~2.5%.
_ROW_TALL = 0.045
_ROW_HALF = 0.012
# A block wider than this spans multiple columns (a full-width table row), so a
# multi-cell row gets each cell narrowed to its column via xpos.
_COL_WIDE = 0.40


def _col_half(value: str | None) -> float:
    """Half-width of a value's column box, scaled a little by value length so a long
    material name gets a wider box than a 4-digit number."""
    n = len((value or "").strip())
    return min(max(0.035 + n * 0.006, 0.04), 0.18)


def _ydist(b: BBox, yp: float | None) -> float:
    """Vertical distance from a row estimate to a block — 0 when the estimate falls
    inside the block, else the gap to its nearest edge. Lets a field's vlm_ypos pick
    the RIGHT row among blocks holding the same repeated value (dates, 'Ja', masses)."""
    if yp is None:
        return 0.0
    if b.y0 <= yp <= b.y1:
        return 0.0
    return min(abs(yp - b.y0), abs(yp - b.y1))


def _best_block(fld, blocks: list[OcrWord], used: set[int]) -> tuple[int, OcrWord] | None:
    val = (fld.value_raw or "").strip()
    yp = fld.vlm_ypos

    # 1. value match -----------------------------------------------------------
    if val:
        target = _digits(val)
        cands: list[tuple[int, float, float, int, float, int, OcrWord]] = []
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
                # sort key: rank, nearest the field's row, smallest area, unused, topmost
                cands.append((rank, _ydist(b.bbox, yp), _area(b.bbox),
                              1 if idx in used else 0, b.bbox.y0, idx, b))
        if cands:
            cands.sort(key=lambda c: (c[0], c[1], c[2], c[3], c[4]))
            best = cands[0]
            return best[5], best[6]

    # 2. label anchor (short / unmatchable values) -----------------------------
    label = _norm(fld.label_raw)
    if len(label) >= 4:
        lcands: list[tuple[float, float, int, int, OcrWord]] = []
        for idx, b in enumerate(blocks):
            if label in _norm(b.text):
                lcands.append((_ydist(b.bbox, yp), _area(b.bbox), 1 if idx in used else 0, idx, b))
        if lcands:
            lcands.sort(key=lambda c: (c[0], c[1], c[2]))  # nearest row, smallest, unused
            best = lcands[0]
            return best[3], best[4]

    return None
