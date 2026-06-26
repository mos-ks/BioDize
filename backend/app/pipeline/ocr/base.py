"""OCR layer abstraction.

The OCR engine is the source of BOUNDING BOXES (general VLMs cannot box reliably
— see docs/MODEL_RESEARCH.md). It returns words with normalized polygons and a
per-word confidence; `pipeline/localize.py` binds extracted values to these.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.pipeline.model import BBox


@dataclass
class OcrWord:
    text: str
    bbox: BBox                      # normalized 0..1 on the page
    confidence: float = 0.5
    is_handwritten: bool = False


@dataclass
class OcrResult:
    page_no: int
    words: list[OcrWord] = field(default_factory=list)


class OcrEngine(Protocol):
    name: str

    def recognize(self, image_path: str | None, page_no: int) -> OcrResult: ...


def get_ocr_engine(name: str) -> OcrEngine:
    if name == "mistral":
        from app.pipeline.ocr.mistral_ocr import MistralOcr

        return MistralOcr()
    # "azure" / "google" adapters slot in here the same way.
    from app.pipeline.ocr.stub_ocr import StubOcr

    return StubOcr()
