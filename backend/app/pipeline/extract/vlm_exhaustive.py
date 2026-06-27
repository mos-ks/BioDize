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
          "is_blank": {"type": "boolean"}},
        "required": ["label", "kind", "value", "options", "selected", "unit", "soll", "calc_expr", "is_blank"]}}},
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
  "Read handwriting verbatim; keep the German decimal comma (e.g. '4,50'). Ignore page "
  "headers/footers (Dok-Nr, Rev., Seite) and abbreviation legends."
)


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
        # confidence seeded modestly; OCR/localize + ensemble refine it downstream
        f.reads = [Read(model=self._model, value_raw=value, confidence=0.8)]
        return f
