"""MistralStructuredExtractor — recognition + localization in ONE step.

The OpenAI extractor reads a whole page in one pass (conflating layout, field-ID
and handwriting transcription) and then boxes are bolted on by fragile text-
matching — which misreads values and mislocates boxes (see the HTR eval).

Mistral OCR already returns every value as its OWN tightly-boxed block, with
per-word confidence and checkbox state. This extractor parses those blocks
directly: associate each value block with its printed label by geometry (the
label is the nearest text to the LEFT on the same row, else the nearest header
above), merge "date + Kürzel" signature pairs, capture ☑/☐ checkbox state, and
parse dense markdown tables. Boxes are Mistral's — correct by construction.

extractor=mistral_structured pairs with ocr_engine=stub (no second OCR needed;
localize() is a no-op because every field already carries a bbox).
"""
from __future__ import annotations

import os
import re

from app.core.config import settings
from app.pipeline.ingest import PageImage, render_pdf
from app.pipeline.model import BBox, Block, Document, Field, Read
from app.pipeline.ocr.mistral_ocr import MistralOcr

_DATE = re.compile(r"\d{1,2}\.\d{1,2}\.\d{2,4}")
_TIME = re.compile(r"^\d{1,2}:\d{2}$")
_NUM = re.compile(r"^[+-]?\d[\d.,]*$")
_KUERZEL = re.compile(r"^[A-Za-zÄÖÜäöüß]{2,5}$")
_CHECK = "☑⊠☒✓"
_UNCHECK = "☐"
_UNITS = {"kg", "l", "g/l", "uhr", "min", "h", "°c", "ml", "mg", "kg/l", "hübe/min", "%"}
_DROP_LABELS = {"kürzel", "kuerzel", "(datum/kürzel)", "(datum/kuerzel)", "datum/kürzel", "gmp"}


def _cy(b: BBox) -> float:
    return (b.y0 + b.y1) / 2


def _union(boxes: list[BBox]) -> BBox:
    return BBox(min(b.x0 for b in boxes), min(b.y0 for b in boxes),
               max(b.x1 for b in boxes), max(b.y1 for b in boxes))


def _is_value(text: str, x0: float) -> bool:
    s = text.strip()
    if not s:
        return False
    if any(c in s for c in _CHECK):              # a CHECKED box is a value
        return True
    if any(c in s for c in _UNCHECK):            # an unchecked option is NOT a value
        return False
    if _DATE.search(s) or _TIME.match(s):
        return True
    if _NUM.match(s):
        return True
    if re.fullmatch(r"\d[\d ]*\d", s):           # "59030 123" = printed code + handwritten
        return True
    if _KUERZEL.match(s) and s.islower() and x0 > 0.45:   # handwritten Kürzel are lowercase
        return True                                       # (printed GMP/HZ are not)
    return False


def _merge_values(vals: list[str]) -> str:
    """Merge a row's value cells into one entry: date+time / date+Kürzel -> 'd / x'."""
    if not vals:
        return ""
    date = next((_DATE.search(v).group() for v in vals if _DATE.search(v)), None)
    tm = next((v.strip() for v in vals if _TIME.match(v.strip())), None)
    kz = next((v.strip() for v in vals if _KUERZEL.match(v.strip()) and v.strip().islower()), None)
    if date and tm:
        return f"{date} / {tm}"
    if date and kz:
        return f"{date} / {kz}"
    if date:
        return date
    return vals[-1].strip().rstrip("/ ").strip()


def _nearest_label(vbb: BBox, label_blocks) -> str:
    """Label to the LEFT of a value, nearest in y (for checkbox columns whose
    label sits on a different row than the checked option)."""
    best, best_dy = None, 1e9
    vy = _cy(vbb)
    for lb in label_blocks:
        if lb.bbox.x0 >= vbb.x0:
            continue
        dy = abs(_cy(lb.bbox) - vy)
        if dy <= 0.06 and dy < best_dy:
            best_dy, best = dy, lb
    return best.text.strip().rstrip(":") if best else ""


def _classify(text: str, x0: float) -> str:
    s = (text or "").strip()
    if not s:
        return "empty"
    if s.startswith("#"):
        return "header"
    low = s.lower()
    if low.startswith("soll") or low.startswith("richtwert"):
        return "soll"
    if "|" in s and s.count("|") >= 2:
        return "table"
    if any(c in s for c in _CHECK):
        return "value"                           # a checked box is a value
    if any(c in s for c in _UNCHECK):
        return "checkbox_off"                    # unchecked option: never a label or value
    if low in _UNITS:
        return "unit"
    if _is_value(s, x0):
        return "value"
    return "label"


class MistralStructuredExtractor:
    name = "mistral_structured"

    def __init__(self) -> None:
        self._ocr = MistralOcr()

    def extract(self, source_path: str | None, pages: list[PageImage] | None = None) -> Document:
        if pages is None:
            if not source_path:
                raise ValueError("MistralStructuredExtractor needs a PDF source_path or pages.")
            pages = render_pdf(source_path).pages

        doc = Document(
            doc_no=(os.path.basename(source_path) if source_path else "document") + " [mistral]",
            title=os.path.basename(source_path) if source_path else "document",
            page_count=len(pages), source_path=source_path,
        )
        for page in pages:
            if page.is_blank or not page.image_path:
                continue
            blocks = self._ocr.recognize(page.image_path, page.page_no).words
            block = Block(chapter="", page_no=page.page_no, template="page")
            block.fields.extend(self._parse_page(blocks, page.page_no, block.key))
            if block.fields:
                doc.blocks.append(block)
        return doc

    # --- per-page parsing ----------------------------------------------------

    def _parse_page(self, blocks, page_no: int, block_key: str) -> list[Field]:
        fields: list[Field] = []
        atomic = [b for b in blocks if _classify(b.text, b.bbox.x0) != "table"]
        tables = [b for b in blocks if _classify(b.text, b.bbox.x0) == "table"]
        label_blocks = [b for b in atomic if _classify(b.text, b.bbox.x0) == "label"]

        # group atomic blocks into visual rows by y-centre proximity
        atomic.sort(key=lambda b: (_cy(b.bbox), b.bbox.x0))
        rows: list[list] = []
        for b in atomic:
            if rows and abs(_cy(b.bbox) - _cy(rows[-1][0].bbox)) < 0.012:
                rows[-1].append(b)
            else:
                rows.append([b])

        last_label = ""
        for row in rows:
            row.sort(key=lambda b: b.bbox.x0)
            kinds = [(_classify(b.text, b.bbox.x0), b) for b in row]
            labels = [b for k, b in kinds if k == "label"]
            values = [b for k, b in kinds if k == "value"]
            if labels:
                last_label = labels[0].text.strip().rstrip(":")
            if not values:
                continue
            if labels:
                label = labels[0].text.strip().rstrip(":")
            else:
                # no same-row label (e.g. a checked box in a column) -> look left
                label = _nearest_label(_union([b.bbox for b in values]), label_blocks) or last_label
            if label.strip().lower() in _DROP_LABELS:
                continue
            f = self._field_from_values(label, values, page_no, block_key)
            if f:
                fields.append(f)

        for tb in tables:
            fields.extend(self._parse_table(tb, page_no, block_key))
        return fields

    def _field_from_values(self, label, value_blocks, page_no, block_key) -> Field | None:
        # signature: a date + a Kürzel on the same row -> "DD.MM.YYYY / kürzel"
        date_b = next((b for b in value_blocks if _DATE.search(b.text)), None)
        kuerzel_b = next((b for b in value_blocks
                          if _KUERZEL.match(b.text.strip()) and not _DATE.search(b.text)), None)
        time_b = next((b for b in value_blocks if _TIME.match(b.text.strip())), None)
        checks = [b for b in value_blocks if any(c in b.text for c in _CHECK)]

        if checks:                                   # checkbox: value = checked option(s)
            opts = [re.sub(r"[%s]" % (_CHECK + _UNCHECK), "", b.text).strip() for b in checks]
            value = ", ".join(o for o in opts if o) or "Ja"
            used = checks
        elif date_b and kuerzel_b:
            value = f"{_DATE.search(date_b.text).group()} / {kuerzel_b.text.strip()}"
            used = [date_b, kuerzel_b]
        elif date_b and time_b:
            value = f"{_DATE.search(date_b.text).group()} / {time_b.text.strip()}"
            used = [date_b, time_b]
        else:
            # take the right-most non-unit value (the handwritten entry), strip printed prefix
            b = value_blocks[-1]
            m = _NUM.findall(b.text.strip()) if False else None
            value = b.text.strip().split()[-1] if " " in b.text.strip() else b.text.strip()
            used = [b]

        value = value.strip()
        if not value:
            return None
        bbox = _union([b.bbox for b in used])
        conf = min((b.confidence for b in used if b.confidence), default=0.6)
        f = Field(page_no=page_no, chapter="", role=None, label_raw=label,
                  value_raw=value, block_key=block_key, bbox=bbox)
        f.ocr_confidence = conf
        f.reads = [Read(model="mistral-ocr-4", value_raw=value, confidence=conf, bbox=bbox)]
        return f

    def _parse_table(self, tb, page_no, block_key) -> list[Field]:
        """Parse a markdown-table block; band-split its box by data-row count."""
        lines = [ln for ln in (tb.text or "").splitlines() if ln.strip().startswith("|")]
        data_rows = []
        for ln in lines:
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if not any(cells) or all(set(c) <= set("-: ") for c in cells):
                continue                              # separator / empty row
            data_rows.append(cells)
        if not data_rows:
            return []

        out: list[Field] = []
        b = tb.bbox
        step = (b.y1 - b.y0) / len(data_rows)
        for i, cells in enumerate(data_rows):
            label = cells[0].strip().rstrip(":")
            # gather the handwritten value cells, then merge (date+time, date+Kürzel)
            vals: list[str] = []
            for c in cells[1:]:
                cs = c.strip()
                if not cs or cs.lower() in _UNITS or cs.lower().startswith(("soll", "v =", "ρ", "richtwert")):
                    continue
                if any(ch in cs for ch in _CHECK):
                    vals = [re.sub(r"[%s]" % (_CHECK + _UNCHECK), "", cs).strip() or "Ja"]
                    break
                if any(ch in cs for ch in _UNCHECK):
                    continue
                if _is_value(cs, 0.6):
                    vals.append(cs)
            value = _merge_values(vals)
            if not label or not value:
                continue
            top = b.y0 + i * step
            bbox = BBox(b.x0, top, b.x1, top + step)
            f = Field(page_no=page_no, chapter="", role=None, label_raw=label,
                      value_raw=value, block_key=block_key, bbox=bbox)
            f.ocr_confidence = tb.confidence
            f.reads = [Read(model="mistral-ocr-4", value_raw=value, confidence=tb.confidence, bbox=bbox)]
            out.append(f)
        return out
