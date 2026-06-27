"""VlmExhaustiveExtractor — the "understanding" layer of the modular ensemble.

A powerful VLM reads EVERY field on each page (never drop): values, selection/
checkbox state (incl. option columns — which one is marked), and signatures
(signed/blank). Boxes are added downstream by the OCR + localize layer
(OCR_ENGINE=mistral); Kürzel are snapped by resolve. Point OPENAI_BASE_URL at
Azure OpenAI to run the same thing inside the customer's Azure tenant (secure).
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.core.config import settings
from app.pipeline.ingest import PageImage, render_pdf
from app.pipeline.model import Block, Document, Field, Read

# doc-meta / boilerplate labels to drop (headers, footers, legends) — not data fields
_NOISE = re.compile(
    r"^(dok[- ]?nr|rev\.?|revisionstyp|projektcode|seite|batch no|rl-abcd|"
    r"herstellung von kuchen|kap\.?|prozessstufe|sap-?materialnummer|zugehörige man|"
    r"production code ds|batch production record)\b", re.I)

_SCHEMA = {
  "name": "page_understanding", "strict": True,
  "schema": {"type": "object", "additionalProperties": False,
    "properties": {
      "section": {"type": "string"},
      "fields": {"type": "array", "items": {"type": "object", "additionalProperties": False,
        "properties": {
          "label": {"type": "string", "description": "printed parameter label / question, verbatim"},
          "kind": {"type": "string", "enum": ["value", "selection", "signature"]},
          "value": {"type": "string", "description": "value entry verbatim; signature: 'DD.MM.YYYY / Kürzel' if signed; '' if blank"},
          "options": {"type": "array", "items": {"type": "string"}, "description": "selection: all option labels"},
          "selected": {"type": "array", "items": {"type": "string"}, "description": "selection: which options are marked (empty if none)"},
          "unit": {"type": ["string", "null"]},
          "nks": {"type": ["integer", "null"], "description": "required Nachkommastellen (decimal places) the FORM prescribes for this value — read it from the printed format (e.g. '__,__ kg' = 2, the Soll's precision like 'Soll: 2,00' = 2). null if the form doesn't prescribe a fixed precision (free text, integers, dates)."},
          "soll": {"type": ["string", "null"]},
          "calc_expr": {"type": ["string", "null"], "description": "if the value is a printed formula's result, the arithmetic with the handwritten numbers substituted (e.g. '6,6 * 45 - 4,3 * 0,75'); else null"},
          "confidence": {"type": "number", "description": "your 0.0-1.0 certainty this value is read correctly. Be HONEST: use LOW (<0.5) for hard-to-read/ambiguous handwriting — ESPECIALLY 2-3 letter signature Kürzel and smudged digits; HIGH (>0.9) only for clearly printed text or unambiguous handwriting. A blank field is 1.0 (certainly blank)."},
          "ypos": {"type": "number", "description": "vertical position of THIS field's row on the page: 0.0 = very top edge, 1.0 = very bottom edge. Estimate the center of the row the value/checkbox/signature sits on, as accurately as you can."},
          "xpos": {"type": "number", "description": "horizontal position of THIS field's VALUE on the page: 0.0 = very left edge, 1.0 = very right edge. Estimate the horizontal center of the handwritten value / checkbox / signature itself (in a table, the COLUMN it sits in), as accurately as you can."},
          "handwritten": {"type": "boolean", "description": "true if the VALUE is HANDWRITTEN (blue/pen ink, filled in by a person); false if it is PRINTED machine text (black, part of the form template). A blank field's intended answer is handwritten -> true."},
          "crossed_out": {"type": "boolean", "description": "true if the entry is struck through / durchgestrichen / scratched out (a correction); otherwise false."},
          "is_blank": {"type": "boolean"}},
        "required": ["label", "kind", "value", "options", "selected", "unit", "nks", "soll", "calc_expr", "confidence", "ypos", "xpos", "handwritten", "crossed_out", "is_blank"]}}},
    "required": ["section", "fields"]}}

_PROMPT = (
  "Exhaustively transcribe EVERY field on this page of a German pharma batch record. "
  "Include EVERY printed parameter/question even when its handwritten value is blank "
  "(is_blank=true, value=''). Set kind: 'value' for a normal entry (date/time/number/text); "
  "'selection' for a checkbox or option group — put ALL options in `options` and the MARKED "
  "ones in `selected` (empty if none is checked); 'signature' for Bearbeitet/Geprüft/Reviewer "
  "fields — if signed put 'DD.MM.YYYY / Kürzel' in `value`, if blank set is_blank=true. "
  "Put any 'Soll'/'Richtwert' target in `soll` and a unit in `unit`. Set `nks` to the number "
  "of decimal places the FORM requires for the value (from the printed '__,__' format or the "
  "Soll's precision, e.g. 2 for 'Soll: 2,00 kg'); use null when no fixed precision is prescribed. "
  "When a value is the "
  "result of a printed formula, fill `calc_expr` with that formula's arithmetic using the "
  "handwritten numbers (e.g. '6,6 * 45 - 4,3 * 0,75'); otherwise null. Do NOT skip anything. "
  "Read handwriting verbatim; keep the German decimal comma (e.g. '4,50'). For EACH field set "
  "`confidence` to your honest 0-1 certainty the value is read correctly — use LOW values for "
  "illegible/ambiguous handwriting, especially short signature Kürzel — never a flat default. "
  "Ignore page headers/footers (Dok-Nr, Rev., Seite) and abbreviation legends. "
  "Do NOT transcribe the table of contents (Inhaltsverzeichnis) or its page numbers. "
  "For EACH field set `handwritten` = true when the value is hand-filled (blue/pen ink) and "
  "false when it is printed form text (black); and `crossed_out` = true when the entry is struck "
  "through / durchgestrichen (a correction)."
)

_META_SCHEMA = {
  "name": "doc_identity", "strict": True,
  "schema": {"type": "object", "additionalProperties": False,
    "properties": {
      "product": {"type": "string", "description": "the product / batch-record title, e.g. 'Herstellung von Vanilla Celebration Cake'"},
      "doc_no": {"type": "string", "description": "Dok-Nr. value, e.g. 'AB-ABC-123456'"},
      "batch_no": {"type": "string", "description": "Batch No. value"},
      "project_code": {"type": "string", "description": "Projektcode value"},
      "rev": {"type": "string", "description": "Rev. value"}},
    "required": ["product", "doc_no", "batch_no", "project_code", "rev"]}}

_META_PROMPT = (
  "Read ONLY the document IDENTITY from the header/cover of this German pharma batch "
  "record: the product/title (e.g. 'Herstellung von …'), Dok-Nr., Batch No., "
  "Projektcode, and Rev. Return '' for any field that is not present.")


def _prettify_name(source_path: str | None) -> str:
    """Human-readable fallback title from a filename — used only when the header
    identity can't be read, so a document never shows as a raw 'foo_bar.pdf'."""
    if not source_path:
        return "Batch record"
    stem = os.path.splitext(os.path.basename(source_path))[0]
    stem = " ".join(stem.replace("_", " ").replace("-", " ").split())
    return stem.title() if stem else "Batch record"


class VlmExhaustiveExtractor:
    name = "vlm_exhaustive"

    def __init__(self) -> None:
        from openai import OpenAI
        self._client = OpenAI(api_key=settings.openai_api_key or "x",
                              base_url=settings.openai_base_url or None)
        self._model = settings.openai_model

    def extract(self, source_path: str | None, pages: list[PageImage] | None = None,
                progress=None) -> Document:
        if pages is None:
            pages = render_pdf(source_path).pages if source_path else []
        doc = Document(
            doc_no="Batch record",
            title=_prettify_name(source_path),
            page_count=len(pages), source_path=source_path)

        non_blank = [p for p in pages if p.image_path and not p.is_blank]
        n_total = len(pages)
        if not non_blank:
            return doc

        workers = min(len(non_blank) + 1, settings.pipeline_workers)
        blocks_by_page: dict[int, Block] = {}
        identity_meta: dict = {}

        with ThreadPoolExecutor(max_workers=workers) as ex:
            # Identity read runs concurrently with the page reads — no wasted time
            # waiting for it before the first page starts.
            id_future = ex.submit(self._fetch_identity, non_blank[0].image_path)

            # All pages submitted at once; completed in arrival order.
            page_futures = {ex.submit(self._read_page, p.image_path): p for p in non_blank}
            done = 0
            for fut in as_completed(page_futures):
                page = page_futures[fut]
                done += 1
                if progress:
                    progress(stage=f"Reading page {page.page_no} of {n_total}…",
                             page_done=done, page_total=len(non_blank))
                try:
                    raws = fut.result()
                except Exception as exc:
                    logging.getLogger(__name__).warning(
                        "page %d read failed: %s", page.page_no, exc)
                    raws = []
                block = Block(chapter="", page_no=page.page_no, template="page")
                for raw in raws:
                    f = self._to_field(raw, page.page_no, block.key)
                    if f is not None:
                        block.fields.append(f)
                if block.fields:
                    blocks_by_page[page.page_no] = block

            try:
                identity_meta = id_future.result()
            except Exception:
                identity_meta = {}

        # Apply identity metadata (main thread — safe doc mutation)
        self._apply_identity(doc, identity_meta)
        # Restore page order (as_completed delivers in arrival, not submission, order)
        doc.blocks = [blocks_by_page[pno] for pno in sorted(blocks_by_page)]
        return doc

    def _fetch_identity(self, image_path: str) -> dict:
        """Fetch doc identity from cover page. Returns raw dict; safe to call from a thread."""
        try:
            with open(image_path, "rb") as fh:
                b64 = base64.b64encode(fh.read()).decode()
            resp = self._client.chat.completions.create(
                model=self._model,
                response_format={"type": "json_schema", "json_schema": _META_SCHEMA},
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": _META_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}])
            return json.loads(resp.choices[0].message.content or "{}")
        except Exception:
            return {}

    def _apply_identity(self, doc: Document, m: dict) -> None:
        """Apply identity metadata to doc (call from main thread only)."""
        product = (m.get("product") or "").strip()
        docno = (m.get("doc_no") or "").strip()
        batch = (m.get("batch_no") or "").strip()
        if product:
            doc.title = product
        ident = " · ".join(b for b in (docno, f"Batch {batch}" if batch else "") if b)
        if ident:
            doc.doc_no = ident
        doc.project_code = (m.get("project_code") or "").strip() or doc.project_code
        doc.rev = (m.get("rev") or "").strip() or doc.rev

    def _read_page(self, image_path: str) -> list[dict]:
        with open(image_path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()
        resp = self._client.chat.completions.create(
            model=self._model,
            response_format={"type": "json_schema", "json_schema": _SCHEMA},
            messages=[{"role": "user", "content": [
                {"type": "text", "text": _PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}])
        content = resp.choices[0].message.content
        return json.loads(content).get("fields", []) if content else []

    def _to_field(self, raw: dict, page_no: int, block_key: str) -> Field | None:
        label = (raw.get("label") or "").strip()
        if not label or _NOISE.match(label):
            return None
        kind = raw.get("kind")
        if kind == "selection":
            selected = [s for s in (raw.get("selected") or []) if s.strip()]
            value = ", ".join(selected)             # the checked option(s); '' if none
            # An empty checkbox/selection is a missing answer — a lone mandatory "Ja"
            # left unchecked is a violation (there is no other option to pick).
            vtype = "checkbox"
        else:
            value = (raw.get("value") or "").strip()
            vtype = None
        f = Field(page_no=page_no, chapter="", role=None, label_raw=label,
                  value_raw=value, unit=raw.get("unit"), soll=raw.get("soll"),
                  calc_expr=raw.get("calc_expr"), block_key=block_key, is_required=True)
        f.value_type = vtype
        # REAL per-field confidence from the reader (legibility self-assessment) —
        # the key signal that lets validation route illegible reads to review
        # instead of asserting hard violations off a guess. Blanks are certain.
        try:
            conf = max(0.0, min(1.0, float(raw.get("confidence"))))
        except (TypeError, ValueError):
            conf = 0.8
        if not value:
            conf = max(conf, 0.95)             # a confidently-blank field
        f.reads = [Read(model=self._model, value_raw=value, confidence=conf)]
        # reader's vertical position estimate -> rescues per-row box placement when
        # Mistral returns a table as one block (see localize band-split).
        try:
            yp = float(raw.get("ypos"))
            f.vlm_ypos = yp if 0.0 <= yp <= 1.0 else None
        except (TypeError, ValueError):
            f.vlm_ypos = None
        # reader's horizontal position estimate -> narrows a full-width table ROW
        # box down to the value's COLUMN (see localize x-split).
        try:
            xp = float(raw.get("xpos"))
            f.vlm_xpos = xp if 0.0 <= xp <= 1.0 else None
        except (TypeError, ValueError):
            f.vlm_xpos = None
        # handwritten (blue) vs printed (black); struck-through entries -> warning.
        hw = raw.get("handwritten")
        f.is_handwritten = bool(hw) if hw is not None else None
        f.is_crossed_out = bool(raw.get("crossed_out"))
        nks = raw.get("nks")
        f.nks = int(nks) if isinstance(nks, (int, float)) and not isinstance(nks, bool) else None
        return f
