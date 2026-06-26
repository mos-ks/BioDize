"""OpenAIExtractor — vision extraction via the OpenAI (or OpenAI-compatible) API.

Renders the PDF to page images and asks a vision model for parameter/value pairs
per page as JSON. Parameters are NOT hardcoded: the model returns whatever
label/value pairs it sees; role assignment + normalization happen downstream.

On-prem swap: set OPENAI_BASE_URL to a vLLM OpenAI-compatible server and
OPENAI_MODEL to the local model (e.g. dots.ocr). No code change here.

NOTE: bounding boxes are intentionally NOT taken from the VLM (they are
unreliable — see docs/MODEL_RESEARCH.md). They come from the OCR layer + localize.
"""
from __future__ import annotations

import base64
import json

from app.core.config import settings
from app.pipeline.ingest import render_pdf
from app.pipeline.model import Block, Document, Field, Read

_PROMPT = (
    "You are extracting data from one page of a scanned, handwritten GMP batch "
    "record (German). Return ONLY JSON: {\"fields\": [{\"label\": str, \"value\": "
    "str, \"unit\": str|null, \"soll\": str|null, \"nks\": int|null}]}. "
    "Rules: read every handwritten entry and pair it with its printed parameter "
    "label. Include the 'Soll' target/range text in `soll` when present, and the "
    "required decimal places `(N NKS)` in `nks`. Do NOT include explanatory prose "
    "or section descriptions. Transcribe values verbatim, keeping the German "
    "decimal comma (e.g. '4,50'). If a field is blank, use value \"\"."
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
            base_url=settings.openai_base_url,
        )
        self._model = settings.openai_model

    def extract(self, source_path: str | None) -> Document:
        if not source_path:
            raise ValueError("OpenAIExtractor requires a PDF source_path.")
        ingest = render_pdf(source_path)
        doc = Document(doc_no="UNKNOWN", title=source_path, page_count=ingest.page_count,
                       source_path=source_path)

        for page in ingest.pages:
            if page.is_blank or not page.image_path:
                continue
            block = Block(chapter="", page_no=page.page_no, template="page")
            for raw in self._read_page(page.image_path):
                fld = Field(
                    page_no=page.page_no, chapter="", role=None,
                    label_raw=str(raw.get("label", "")), value_raw=str(raw.get("value", "")),
                    unit=raw.get("unit"), nks=raw.get("nks"), soll=raw.get("soll"),
                    block_key=block.key,
                )
                fld.reads = [Read(model=self._model, value_raw=fld.value_raw, confidence=0.8)]
                block.fields.append(fld)
            doc.blocks.append(block)
        return doc

    def _read_page(self, image_path: str) -> list[dict]:
        with open(image_path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()
        resp = self._client.chat.completions.create(
            model=self._model,
            response_format={"type": "json_object"},
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": _PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            }],
        )
        try:
            return json.loads(resp.choices[0].message.content).get("fields", [])
        except (json.JSONDecodeError, AttributeError):
            return []
