"""Extractor interface — provider-agnostic.

`extract()` returns a Document of Blocks/Fields. Parameters are NOT hardcoded;
each field carries the raw label + value plus per-model `reads` (ensemble-ready).
Today: StubExtractor / OpenAIExtractor. The on-prem swap is a config change
(point OPENAI_BASE_URL at a vLLM server) — no code change here.
"""
from __future__ import annotations

from typing import Protocol

from app.pipeline.ingest import PageImage
from app.pipeline.model import Document


class Extractor(Protocol):
    name: str

    def extract(self, source_path: str | None, pages: list[PageImage] | None = None) -> Document:
        """Return a Document. `pages` are pre-rendered images (so the PDF is
        rendered once and shared with the OCR layer); the stub ignores both."""
        ...


def get_extractor(name: str) -> Extractor:
    if name == "openai":
        from app.pipeline.extract.openai_extractor import OpenAIExtractor

        return OpenAIExtractor()
    from app.pipeline.extract.stub import StubExtractor

    return StubExtractor()
