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
import re
from concurrent.futures import ThreadPoolExecutor

from app.core.config import settings
from app.domain.roles import Role
from app.pipeline.model import BBox, Document, Field, Read
from app.pipeline.resolve import _edits, _roster_kuerzel, _split_sig

_log = logging.getLogger(__name__)
_SIG_ROLES = (Role.SIGNATURE_PROCESSED, Role.SIGNATURE_CHECKED)
_PAD_Y = 0.018          # handwriting overflows the printed line — pad vertically
_PAD_X = 0.012
_UPSCALE = 3


def _read_conf(f: Field) -> float:
    return min((r.confidence for r in f.reads), default=1.0)


_SIG_LABEL = ("datum/kürzel", "datum/kuerzel", "bearbeitet", "geprüft", "geprueft", "unterschrift")


def _looks_like_signature(f: Field) -> bool:
    # Roles aren't assigned until normalize (which runs AFTER this pass), so a
    # signature must be recognized by its printed label here, not by f.role.
    if f.role in _SIG_ROLES:
        return True
    low = (f.label_raw or "").lower()
    return any(k in low for k in _SIG_LABEL)


_SIG_COMPLETE = re.compile(r"\d{1,2}\.\d{1,2}\.\d{2,4}.*?/\s*[A-Za-zÄÖÜäöüß]{2,}")


def _complete_signature(val: str) -> bool:
    """A usable signature re-read has BOTH a date and a Kürzel. A partial zoom read
    (date-only or Kürzel-only) just trades one flag for another, so we reject it."""
    return bool(_SIG_COMPLETE.search(val or ""))


def _kuerzel_stray(f: Field, roster: set[str]) -> bool:
    """A signature read as a Kürzel that matches NO registered signer (edit-distance
    > 2 from every roster Kürzel) is almost certainly a misread (e.g. 'Gg') — worth
    a zoomed second look even though the reader thought it was confident."""
    if not roster or not _looks_like_signature(f):
        return False
    _, kz = _split_sig(f.value_raw or "")
    return bool(kz) and all(_edits(kz, r, 3) > 2 for r in roster)


def _is_uncertain(f: Field, roster: set[str]) -> bool:
    if f.bbox is None:
        return False
    if _read_conf(f) < settings.zoom_conf_threshold:
        return True
    blank = not (f.value_raw or "").strip()
    # a required signature/checkbox that came back blank: confirm empty vs faint
    if blank and f.is_required and (_looks_like_signature(f) or f.value_type == "checkbox"):
        return True
    # a signature whose Kürzel matches no registered signer -> likely a misread
    if not blank and _kuerzel_stray(f, roster):
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

    roster = set(_roster_kuerzel(doc).keys())          # registered signers (e.g. {han, ohe})
    targets = [f for f in doc.all_fields()
               if _is_uncertain(f, roster) and f.page_no in page_images][: settings.zoom_max_fields]
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
        was_stray = _kuerzel_stray(f, roster)          # original Kürzel matched no signer
        # accept the zoom value when it filled a blank, beat the original confidence,
        # or replaced a stray Kürzel (which can't be worse than matching no signer).
        if val and (was_blank or was_stray or conf >= _read_conf(f)):
            # a signature re-read is only useful if it's a COMPLETE 'date / Kürzel';
            # a partial read just swaps one warning for another, so keep the original.
            if _looks_like_signature(f) and not _complete_signature(val):
                continue
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
