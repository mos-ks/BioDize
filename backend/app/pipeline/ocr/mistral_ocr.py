"""Mistral OCR 4 adapter — typed blocks + boxes + word confidence (cloud API).

Chosen as the box/confidence/structure provider (see docs/MODEL_RESEARCH.md §6).
Returns OcrWords with normalized bboxes + confidence; `localize.py` binds the
OpenAI-read handwritten values to these polygons, and the per-word confidence
feeds the UQ scorer.

SCHEMA (verified June 2026 against the live Document AI API and mistralai SDK):
  - Call:  client.ocr.process(model=..., document={"type": "image_url",
           "image_url": "data:image/png;base64,<...>"}, include_blocks=True,
           confidence_scores_granularity="word")
  - Boxes are PER-BLOCK, not per-word. Each block carries integer PIXEL coords
    `top_left_x/top_left_y/bottom_right_x/bottom_right_y` (relative to the page
    `dimensions.width/height`) plus a `type` (title/text/table/...) and `content`.
  - Confidence is PER-WORD: page.confidence_scores.word_confidence_scores is a
    list of objects with `text` and `confidence` ONLY — it has NO bounding box.
  Refs:
    https://docs.mistral.ai/studio-api/document-processing/basic_ocr
    https://docs.mistral.ai/api/endpoint/ocr
    https://mistral.ai/news/ocr-4/
Lazy import so the app boots without the SDK / key.
"""
from __future__ import annotations

import base64
from statistics import mean

from app.core.config import settings
from app.pipeline.model import BBox
from app.pipeline.ocr.base import OcrEngine, OcrResult, OcrWord

# Block types Mistral classifies as handwriting-bearing / signature regions.
_HANDWRITTEN_TYPES = {"signature", "handwriting", "handwritten"}


class MistralOcr(OcrEngine):
    name = "mistral-ocr-4"

    def __init__(self) -> None:
        try:
            try:
                from mistralai import Mistral            # mistralai 1.x
            except ImportError:
                from mistralai.client import Mistral      # mistralai 2.x (Mistral moved here)
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("`pip install mistralai` to use the Mistral OCR engine.") from exc
        if not settings.mistral_api_key:
            raise RuntimeError("MISTRAL_API_KEY is not set.")
        self._client = Mistral(api_key=settings.mistral_api_key)
        # `include_blocks` requires OCR 4 (mistral-ocr-4-0). Pin the family so a
        # future `-latest` rollover to a model without blocks can't silently
        # drop our boxes; bump deliberately when upgrading.
        self._model = "mistral-ocr-4-0"

    def recognize(self, image_path: str | None, page_no: int) -> OcrResult:
        if not image_path:
            return OcrResult(page_no=page_no, words=[])
        with open(image_path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()

        resp = self._client.ocr.process(
            model=self._model,
            document={
                "type": "image_url",
                # Image input = a base64 data URI on the `image_url` field.
                "image_url": f"data:image/png;base64,{b64}",
            },
            include_blocks=True,                      # -> page.blocks (per-block bboxes)
            confidence_scores_granularity="word",     # -> page.confidence_scores.word_*
        )
        return OcrResult(page_no=page_no, words=list(self._parse(resp)))

    def _parse(self, resp) -> list[OcrWord]:
        """Flatten the OCR response into words/blocks with normalized boxes.

        The API gives boxes per BLOCK and confidence per WORD (no per-word box),
        so we emit one OcrWord per typed block and estimate its confidence from
        the word_confidence_scores whose text appears in that block's content.
        """
        words: list[OcrWord] = []
        for page in getattr(resp, "pages", None) or []:
            dims = getattr(page, "dimensions", None)
            pw = float(getattr(dims, "width", 0) or 0) or 1.0
            ph = float(getattr(dims, "height", 0) or 0) or 1.0

            # Per-word confidence map: {normalized_word_text: confidence}.
            word_conf = _word_confidence_map(getattr(page, "confidence_scores", None))
            page_avg = _page_avg_confidence(getattr(page, "confidence_scores", None))

            for block in getattr(page, "blocks", None) or []:
                bbox = _block_bbox(block, pw, ph)
                if bbox is None:
                    continue
                text = _block_text(block)
                btype = (getattr(block, "type", "") or "").lower()
                words.append(OcrWord(
                    text=text,
                    bbox=bbox,
                    confidence=_block_confidence(text, word_conf, page_avg),
                    is_handwritten=btype in _HANDWRITTEN_TYPES,
                ))
        return words


# --- response-shape helpers (named exactly per the live schema) ---------------

def _block_bbox(block, page_w: float, page_h: float) -> BBox | None:
    """Block carries integer PIXEL corners top_left_*/bottom_right_*; normalize."""
    tlx = getattr(block, "top_left_x", None)
    tly = getattr(block, "top_left_y", None)
    brx = getattr(block, "bottom_right_x", None)
    bry = getattr(block, "bottom_right_y", None)
    if None in (tlx, tly, brx, bry):
        return None
    return BBox(
        float(tlx) / page_w,
        float(tly) / page_h,
        float(brx) / page_w,
        float(bry) / page_h,
    )


def _block_text(block) -> str:
    # Blocks expose `content`; fall back to `text` for forward/back compat.
    return (getattr(block, "content", None) or getattr(block, "text", "") or "").strip()


def _word_confidence_map(conf) -> dict[str, float]:
    """page.confidence_scores.word_confidence_scores -> {text: confidence}.

    Each entry has `text` and `confidence` (no bbox). Keep the min confidence
    when a token repeats so a single low-confidence hit isn't masked.
    """
    out: dict[str, float] = {}
    for w in getattr(conf, "word_confidence_scores", None) or []:
        t = (getattr(w, "text", "") or "").strip().lower()
        if not t:
            continue
        c = float(getattr(w, "confidence", 0.0) or 0.0)
        out[t] = min(out.get(t, c), c)
    return out


def _page_avg_confidence(conf) -> float:
    return float(getattr(conf, "average_page_confidence_score", 0.5) or 0.5)


def _block_confidence(text: str, word_conf: dict[str, float], default: float) -> float:
    """Average the per-word confidences of tokens contained in this block."""
    hits = [word_conf[t] for t in {w.strip().lower() for w in text.split()} if t in word_conf]
    return mean(hits) if hits else default
