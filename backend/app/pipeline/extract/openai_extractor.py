"""OpenAIExtractor — vision extraction via the OpenAI (or OpenAI-compatible) API.

Uses Structured Outputs (strict json_schema) to return parameter/value pairs per
page. Parameters are NOT hardcoded: the model returns whatever label/value pairs
it sees; role assignment + normalization happen downstream.

On-prem swap: set OPENAI_BASE_URL to a vLLM OpenAI-compatible server (e.g. the
DGX Spark) and OPENAI_MODEL to the local model. No code change.

Bounding boxes are NOT taken from the VLM (unreliable — see MODEL_RESEARCH.md);
they come from the OCR layer + localize.
"""
from __future__ import annotations

import base64
import json
import os

from app.core.config import settings
from app.pipeline.ingest import PageImage, render_pdf
from app.pipeline.model import Block, Document, Field, Read

# Strict Structured Outputs schema: one page -> a list of parameter/value pairs.
_SCHEMA = {
    "name": "page_fields",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "fields": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "label": {"type": "string", "description": "printed parameter label"},
                        "value": {"type": "string", "description": "handwritten value, verbatim ('' if blank)"},
                        "unit": {"type": ["string", "null"]},
                        "soll": {"type": ["string", "null"], "description": "Soll target/range text if present"},
                        "nks": {"type": ["integer", "null"], "description": "required decimal places (N NKS)"},
                        "calc_expr": {"type": ["string", "null"], "description":
                                      "if this value is the result of a formula printed on the form, the "
                                      "arithmetic with the handwritten numbers substituted, e.g. "
                                      "'6,6 * 45 - 4,3 * 0,75'; otherwise null"},
                        "chapter": {"type": ["string", "null"], "description":
                                    "the section number this field sits under, exactly as printed on the "
                                    "page (e.g. '5.3.1'); null if none is visible"},
                    },
                    "required": ["label", "value", "unit", "soll", "nks", "calc_expr", "chapter"],
                },
            }
        },
        "required": ["fields"],
    },
}

_PROMPT = (
    "You are extracting data from ONE page of a scanned, handwritten GMP batch "
    "record (German, anonymized as cake baking). Read every handwritten entry and "
    "pair it with its printed parameter label. Put the 'Soll' target/range text in "
    "`soll` and the required decimal places '(N NKS)' in `nks` when present. Do NOT "
    "include explanatory prose, section descriptions, headers, or footers — only "
    "parameter/value pairs. Transcribe values verbatim, keeping the German decimal "
    "comma (e.g. '4,50'). For signature fields keep 'DD.MM.YYYY / Kuerzel'. When a "
    "value is the result of a formula printed on the form, also fill `calc_expr` "
    "with that formula's arithmetic using the handwritten numbers (e.g. "
    "'6,6 * 45 - 4,3 * 0,75'). Set `chapter` to the section number the field sits "
    "under, exactly as printed (e.g. '5.3.1') — this links 'Übertrag Kapitel X' "
    "carried values to their source. If a field is blank, set value to an empty string."
)


class OpenAIExtractor:
    name = "openai"

    def __init__(self) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("`pip install openai` to use the OpenAI extractor.") from exc
        self._client = OpenAI(
            api_key=settings.openai_api_key or "not-needed",
            base_url=settings.openai_base_url or None,   # empty string -> default api.openai.com
        )
        self._model = settings.openai_model

    def extract(self, source_path: str | None, pages: list[PageImage] | None = None) -> Document:
        if pages is None:
            if not source_path:
                raise ValueError("OpenAIExtractor requires a PDF source_path or pre-rendered pages.")
            pages = render_pdf(source_path).pages

        doc = Document(
            doc_no=os.path.basename(source_path) if source_path else "document",
            title=os.path.basename(source_path) if source_path else "document",
            page_count=len(pages),
            source_path=source_path,
        )

        for page in pages:
            if page.is_blank or not page.image_path:
                continue
            block = Block(chapter="", page_no=page.page_no, template="page")
            for raw in self._read_page(page.image_path):
                value = str(raw.get("value", "")).strip()
                if not value:
                    continue  # keep param:value pairs; blanks handled by missing-data (Day 2)
                fld = Field(
                    page_no=page.page_no, chapter=(raw.get("chapter") or "").strip(), role=None,
                    label_raw=str(raw.get("label", "")), value_raw=value,
                    unit=raw.get("unit"), nks=raw.get("nks"), soll=raw.get("soll"),
                    calc_expr=raw.get("calc_expr"), block_key=block.key,
                )
                fld.reads = [Read(model=self._model, value_raw=value, confidence=0.8)]
                block.fields.append(fld)
            if block.fields:
                doc.blocks.append(block)
        return doc

    def _read_page(self, image_path: str) -> list[dict]:
        with open(image_path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()
        resp = self._client.chat.completions.create(
            model=self._model,
            response_format={"type": "json_schema", "json_schema": _SCHEMA},
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": _PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }],
        )
        choice = resp.choices[0]
        if getattr(choice.message, "refusal", None):
            raise RuntimeError(f"model refused page: {choice.message.refusal}")
        if choice.finish_reason == "length":
            raise RuntimeError("response truncated — raise max_tokens")
        content = choice.message.content
        if not content:
            return []
        return json.loads(content).get("fields", [])
