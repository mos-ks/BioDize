"""Uncertainty-triggered ZOOM RE-READ — a focused second look at the fields the
first full-page pass was unsure about.

When a field is read with low confidence, or a required signature/checkbox comes
back blank, we crop its region from the HIGH-RES scan, upscale it, and re-read
just that strip with the VLM. The model stops competing with the rest of the page
and the handwriting fills the frame — recovering faint values the page pass missed
(e.g. a signature read as blank) and confidently confirming the genuinely-empty
ones. Only the uncertain subset is re-read, so it's a few dozen tiny crops, not a
full second pass. Runs after localize (boxes exist) and before normalize (so the
recovered value_raw is parsed/resolved normally). Toggle with settings.zoom_reread.
"""
from __future__ import annotations

import base64
import io
import json
import logging
from concurrent.futures import ThreadPoolExecutor

from app.core.config import settings
from app.domain.roles import Role
from app.pipeline.model import BBox, Document, Field, Read

_log = logging.getLogger(__name__)
_SIG_ROLES = (Role.SIGNATURE_PROCESSED, Role.SIGNATURE_CHECKED)
_PAD_Y = 0.018          # handwriting overflows the printed line — pad vertically
_PAD_X = 0.012
_UPSCALE = 3


def _read_conf(f: Field) -> float:
    return min((r.confidence for r in f.reads), default=1.0)


def _is_uncertain(f: Field) -> bool:
    if f.bbox is None:
        return False
    if _read_conf(f) < settings.zoom_conf_threshold:
        return True
    # a required signature/checkbox that came back blank: confirm empty vs faint
    blank = not (f.value_raw or "").strip()
    if blank and f.is_required and (f.role in _SIG_ROLES or f.value_type == "checkbox"):
        return True
    return False


def _crop_b64(im, b: BBox, w: int, h: int) -> str | None:
    x0 = max(0, int((min(b.x0, b.x1) - _PAD_X) * w))
    x1 = min(w, int((max(b.x0, b.x1) + _PAD_X) * w))
    y0 = max(0, int((min(b.y0, b.y1) - _PAD_Y) * h))
    y1 = min(h, int((max(b.y0, b.y1) + _PAD_Y) * h))
    if x1 - x0 < 6 or y1 - y0 < 6:
        return None
    crop = im.crop((x0, y0, x1, y1))
    crop = crop.resize((crop.width * _UPSCALE, crop.height * _UPSCALE))
    buf = io.BytesIO()
    crop.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def zoom_reread(doc: Document, page_images: dict[int, str]) -> Document:
    if not settings.zoom_reread or not page_images:
        return doc
    try:
        from PIL import Image
        from openai import OpenAI
    except ImportError:
        _log.warning("zoom_reread skipped: Pillow/openai not installed")
        return doc

    targets = [f for f in doc.all_fields()
               if _is_uncertain(f) and f.page_no in page_images][: settings.zoom_max_fields]
    if not targets:
        return doc

    client = OpenAI(api_key=settings.openai_api_key or "x", base_url=settings.openai_base_url or None)
    model = settings.openai_model
    images: dict[int, "Image.Image"] = {}

    def _img(page_no: int):
        im = images.get(page_no)
        if im is None:
            im = Image.open(page_images[page_no]).convert("RGB")
            images[page_no] = im
        return im

    def _reread(f: Field):
        try:
            im = _img(f.page_no)
            b64 = _crop_b64(im, f.bbox, *im.size)
            if not b64:
                return None
            prompt = (
                "Zoomed crop of ONE field from a German GMP batch record. "
                f"Field: '{f.label_raw}'. Read ONLY its handwritten value verbatim "
                "(a signature is 'DD.MM.YYYY / Kürzel'; keep the German decimal comma; "
                "return '' ONLY if the cell is truly empty). "
                'Return ONLY JSON: {"value":"..","confidence":0-1}.')
            resp = client.chat.completions.create(
                model=model, response_format={"type": "json_object"},
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}])
            return f, json.loads(resp.choices[0].message.content or "{}")
        except Exception as exc:                       # one bad crop must not kill the run
            _log.debug("zoom_reread field failed: %s", exc)
            return None

    with ThreadPoolExecutor(max_workers=6) as ex:
        results = [r for r in ex.map(_reread, targets) if r]

    recovered = confirmed = 0
    for f, out in results:
        val = (out.get("value") or "").strip()
        try:
            conf = max(0.0, min(1.0, float(out.get("confidence"))))
        except (TypeError, ValueError):
            conf = 0.7
        was_blank = not (f.value_raw or "").strip()
        if val and (was_blank or conf >= _read_conf(f)):
            # recovered a value the page pass missed, or a more confident zoom read
            f.value_raw = val
            f.value = val
            f.reads.append(Read(model=f"{model}-zoom", value_raw=val, confidence=conf))
            f.ocr_confidence = max(f.ocr_confidence or 0.0, conf)
            recovered += 1
        elif not val and was_blank and conf >= 0.85:
            # confidently confirmed empty -> trust it (stop nagging as low-confidence)
            for r in f.reads:
                r.confidence = max(r.confidence, conf)
            confirmed += 1

    _log.info("zoom_reread: %d uncertain, %d recovered, %d confirmed-blank",
              len(targets), recovered, confirmed)
    return doc
