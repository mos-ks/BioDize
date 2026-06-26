"""Ingest: render a scanned PDF to page images and attach hardcoded metadata.

The page number (footer "Seite N von M") is the reliable anchor — we key
everything on it. PyMuPDF is imported lazily so the app boots (and the stub
pipeline runs) even if it isn't installed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from app.core.config import settings


@dataclass
class PageImage:
    page_no: int
    image_path: str | None
    width: int = 0
    height: int = 0
    is_blank: bool = False
    has_kreuzung: bool = False


@dataclass
class IngestResult:
    source_path: str
    page_count: int
    pages: list[PageImage] = field(default_factory=list)


def render_pdf(source_path: str, out_dir: str | None = None) -> IngestResult:
    """Render each PDF page to a PNG under out_dir; return page metadata."""
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "PyMuPDF (fitz) is required for PDF ingest. `pip install PyMuPDF`, "
            "or use EXTRACTOR=stub to run the pipeline without a PDF."
        ) from exc

    out_dir = out_dir or os.path.join(settings.storage_dir, "pages")
    os.makedirs(out_dir, exist_ok=True)

    doc = fitz.open(source_path)
    zoom = settings.render_dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)

    pages: list[PageImage] = []
    for i, page in enumerate(doc, start=1):
        pix = page.get_pixmap(matrix=matrix)
        img_path = os.path.join(out_dir, f"page_{i:03d}.png")
        pix.save(img_path)
        pages.append(
            PageImage(
                page_no=i,
                image_path=img_path,
                width=pix.width,
                height=pix.height,
                is_blank=_looks_blank(pix),
                has_kreuzung=False,  # TODO: detect diagonal strike via line analysis
            )
        )
    doc.close()
    return IngestResult(source_path=source_path, page_count=len(pages), pages=pages)


def _looks_blank(pix) -> bool:
    """Ink-coverage check on the rendered pixmap (scanned pages have no text layer,
    so text-based detection is useless). Blank = almost no dark pixels. A page with
    headers/footers/table borders has plenty of ink, so only truly empty pages skip."""
    try:
        data = pix.samples
        n = max(1, pix.n)
        dark = total = 0
        for i in range(0, len(data) - n, n * 97):   # sparse stride, on channel boundaries
            if data[i] < 200:                        # first channel as a luminance proxy
                dark += 1
            total += 1
        return total > 0 and (dark / total) < 0.002
    except Exception:
        return False
