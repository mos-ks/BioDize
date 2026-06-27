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
import os
import re

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
          "soll": {"type": ["string", "null"]},
          "calc_expr": {"type": ["string", "null"], "description": "if the value is a printed formula's result, the arithmetic with the handwritten numbers substituted (e.g. '6,6 * 45 - 4,3 * 0,75'); else null"},
          "confidence": {"type": "number", "description": "your 0.0-1.0 certainty this value is read correctly. Be HONEST: use LOW (<0.5) for hard-to-read/ambiguous handwriting — ESPECIALLY 2-3 letter signature Kürzel and smudged digits; HIGH (>0.9) only for clearly printed text or unambiguous handwriting. A blank field is 1.0 (certainly blank)."},
          "ypos": {"type": "number", "description": "vertical position of THIS field's row on the page: 0.0 = very top edge, 1.0 = very bottom edge. Estimate the center of the row the value/checkbox/signature sits on, as accurately as you can."},
          "is_blank": {"type": "boolean"}},
        "required": ["label", "kind", "value", "options", "selected", "unit", "soll", "calc_expr", "confidence", "ypos", "is_blank"]}}},
    "required": ["section", "fields"]}}

_PROMPT = (
  "Exhaustively transcribe EVERY field on this page of a German pharma batch record. "
  "Include EVERY printed parameter/question even when its handwritten value is blank "
  "(is_blank=true, value=''). Set kind: 'value' for a normal entry (date/time/number/text); "
  "'selection' for a checkbox or option group — put ALL options in `options` and the MARKED "
  "ones in `selected` (empty if none is checked); 'signature' for Bearbeitet/Geprüft/Reviewer "
  "fields — if signed put 'DD.MM.YYYY / Kürzel' in `value`, if blank set is_blank=true. "
  "Put any 'Soll'/'Richtwert' target in `soll` and a unit in `unit`. When a value is the "
  "result of a printed formula, fill `calc_expr` with that formula's arithmetic using the "
  "handwritten numbers (e.g. '6,6 * 45 - 4,3 * 0,75'); otherwise null. Do NOT skip anything. "
  "Read handwriting verbatim; keep the German decimal comma (e.g. '4,50'). For EACH field set "
  "`confidence` to your honest 0-1 certainty the value is read correctly — use LOW values for "
  "illegible/ambiguous handwriting, especially short signature Kürzel — never a flat default. "
  "Ignore page headers/footers (Dok-Nr, Rev., Seite) and abbreviation legends. "
  "Do NOT transcribe the table of contents (Inhaltsverzeichnis) or its page numbers."
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


class VlmExhaustiveExtractor:
    name = "vlm_exhaustive"

    def __init__(self) -> None:
        from openai import OpenAI
        self._client = OpenAI(api_key=settings.openai_api_key or "x",
                              base_url=settings.openai_base_url or None)
        self._model = settings.openai_model

    def extract(self, source_path: str | None, pages: list[PageImage] | None = None) -> Document:
        if pages is None:
            pages = render_pdf(source_path).pages if source_path else []
        doc = Document(
            doc_no=(os.path.basename(source_path) if source_path else "document") + " [ensemble]",
            title=os.path.basename(source_path) if source_path else "document",
            page_count=len(pages), source_path=source_path)

        # Name the experiment by its extracted identity (product + batch), not the
        # PDF filename. Read the cover/header of the first real page.
        first = next((p for p in pages if p.image_path and not p.is_blank), None)
        if first:
            self._apply_identity(doc, first.image_path)

        for page in pages:
            if page.is_blank or not page.image_path:
                continue
            block = Block(chapter="", page_no=page.page_no, template="page")
            for raw in self._read_page(page.image_path):
                f = self._to_field(raw, page.page_no, block.key)
                if f is not None:
                    block.fields.append(f)
            if block.fields:
                doc.blocks.append(block)
        return doc

    def _apply_identity(self, doc: Document, image_path: str) -> None:
        """Set doc.title (product) and doc.doc_no (Dok-Nr · Batch) from the header,
        so the UI names the experiment by its content, not the filename. Best-effort."""
        try:
            with open(image_path, "rb") as fh:
                b64 = base64.b64encode(fh.read()).decode()
            resp = self._client.chat.completions.create(
                model=self._model,
                response_format={"type": "json_schema", "json_schema": _META_SCHEMA},
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": _META_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}])
            m = json.loads(resp.choices[0].message.content or "{}")
        except Exception:
            return
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
        return f
