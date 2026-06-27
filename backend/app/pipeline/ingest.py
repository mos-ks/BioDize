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
    """Render each PDF page to a PNG under out_dir; return page metadata.

    Tries PyMuPDF (fitz) first; falls back to pypdfium2+Pillow which has
    ARM64-Windows wheels when PyMuPDF is unavailable.
    """
    out_dir = out_dir or os.path.join(settings.storage_dir, "pages")
    os.makedirs(out_dir, exist_ok=True)

    # --- renderer selection ---------------------------------------------------
    try:
        import fitz  # PyMuPDF
        return _render_fitz(fitz, source_path, out_dir)
    except ImportError:
        pass

    try:
        import pypdfium2 as pdfium
        return _render_pdfium(pdfium, source_path, out_dir)
    except ImportError:
        pass

    raise RuntimeError(
        "No PDF renderer available. Install either PyMuPDF or pypdfium2+Pillow:\n"
        "  pip install pypdfium2 Pillow"
    )


def _render_fitz(fitz, source_path: str, out_dir: str) -> IngestResult:
    doc = fitz.open(source_path)
    zoom = settings.render_dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    pages: list[PageImage] = []
    for i, page in enumerate(doc, start=1):
        pix = page.get_pixmap(matrix=matrix)
        img_path = os.path.join(out_dir, f"page_{i:03d}.png")
        pix.save(img_path)
        pages.append(PageImage(
            page_no=i, image_path=img_path,
            width=pix.width, height=pix.height,
            is_blank=_looks_blank_fitz(pix),
        ))
    doc.close()
    return IngestResult(source_path=source_path, page_count=len(pages), pages=pages)


def _render_pdfium(pdfium, source_path: str, out_dir: str) -> IngestResult:
    scale = settings.render_dpi / 72.0
    doc = pdfium.PdfDocument(source_path)
    pages: list[PageImage] = []
    for i in range(len(doc)):
        page = doc[i]
        bmp = page.render(scale=scale)
        img = bmp.to_pil()
        img_path = os.path.join(out_dir, f"page_{i + 1:03d}.png")
        img.save(img_path)
        pages.append(PageImage(
            page_no=i + 1, image_path=img_path,
            width=img.width, height=img.height,
            is_blank=_looks_blank_pil(img),
        ))
    return IngestResult(source_path=source_path, page_count=len(pages), pages=pages)


def _looks_blank_fitz(pix) -> bool:
    try:
        data = pix.samples
        n = max(1, pix.n)
        dark = total = 0
        for i in range(0, len(data) - n, n * 97):
            if data[i] < 200:
                dark += 1
            total += 1
        return total > 0 and (dark / total) < 0.002
    except Exception:
        return False


def _looks_blank_pil(img) -> bool:
    try:
        gray = img.convert("L")
        pixels = gray.getdata()
        step = max(1, len(pixels) // 500)
        sampled = [pixels[i] for i in range(0, len(pixels), step)]
        dark = sum(1 for p in sampled if p < 200)
        return (dark / len(sampled)) < 0.002
    except Exception:
        return False
