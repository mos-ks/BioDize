"""Mistral OCR 4 adapter — boxes + typed blocks + per-word confidence (cloud API).

Chosen as the box/confidence/structure provider (see docs/MODEL_RESEARCH.md §6).
Returns OcrWords with normalized bboxes + confidence; `localize.py` binds the
OpenAI-read handwritten values to these polygons, and the per-word confidence
feeds the UQ scorer.

NOTE: the exact OCR-4 response schema (per-block boxes vs per-word) should be
confirmed against the live API; parsing here is defensive. Lazy import so the
app boots without the SDK / key.
"""
from __future__ import annotations

import base64

from app.core.config import settings
from app.pipeline.model import BBox
from app.pipeline.ocr.base import OcrEngine, OcrResult, OcrWord


class MistralOcr(OcrEngine):
    name = "mistral-ocr-4"

    def __init__(self) -> None:
        try:
            from mistralai import Mistral
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("`pip install mistralai` to use the Mistral OCR engine.") from exc
        if not settings.mistral_api_key:
            raise RuntimeError("MISTRAL_API_KEY is not set.")
        self._client = Mistral(api_key=settings.mistral_api_key)
        self._model = "mistral-ocr-latest"

    def recognize(self, image_path: str | None, page_no: int) -> OcrResult:
        if not image_path:
            return OcrResult(page_no=page_no, words=[])
        with open(image_path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()

        resp = self._client.ocr.process(
            model=self._model,
            document={"type": "image_url", "image_url": f"data:image/png;base64,{b64}"},
            # OCR 4 returns per-block boxes + per-page/word confidence.
        )
        return OcrResult(page_no=page_no, words=list(self._parse(resp)))

    def _parse(self, resp) -> list[OcrWord]:
        """Defensively flatten the OCR response into words with normalized boxes."""
        words: list[OcrWord] = []
        pages = getattr(resp, "pages", None) or []
        for page in pages:
            dims = getattr(page, "dimensions", None)
            pw = getattr(dims, "width", 0) or 1
            ph = getattr(dims, "height", 0) or 1
            for block in getattr(page, "blocks", None) or getattr(page, "words", None) or []:
                bbox = _normalize_bbox(getattr(block, "bbox", None), pw, ph)
                if bbox is None:
                    continue
                words.append(OcrWord(
                    text=getattr(block, "text", "") or "",
                    bbox=bbox,
                    confidence=float(getattr(block, "confidence", 0.5) or 0.5),
                    is_handwritten=bool(getattr(block, "is_handwritten", False)),
                ))
        return words


def _normalize_bbox(raw, page_w: float, page_h: float) -> BBox | None:
    """Accept {x0,y0,x1,y1} in pixels (or already-normalized) -> normalized BBox."""
    if raw is None:
        return None
    try:
        x0, y0, x1, y1 = raw.get("x0"), raw.get("y0"), raw.get("x1"), raw.get("y1")
    except AttributeError:
        x0, y0, x1, y1 = raw  # tuple/list fallback
    if max(x1, y1) > 1.5:  # looks like pixels
        return BBox(x0 / page_w, y0 / page_h, x1 / page_w, y1 / page_h)
    return BBox(x0, y0, x1, y1)
