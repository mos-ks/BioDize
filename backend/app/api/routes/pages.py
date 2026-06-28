"""Page images and field crops for the bbox overlay."""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.db import models

router = APIRouter(tags=["pages"])
_log = logging.getLogger(__name__)


def _rerender_from_pdf(page: models.Page, db: Session) -> str | None:
    """Re-render a single page from the stored source PDF and cache it to disk.
    Used when the ephemeral image cache was wiped (e.g. a cloud restart) but the
    PDF bytes survive in a persistent DB. Returns the new path, or None."""
    rec = db.get(models.DocumentPdf, page.document_id)
    if not rec or not rec.data:
        return None
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return None
    try:
        pdoc = fitz.open(stream=rec.data, filetype="pdf")
        idx = page.page_no - 1
        if idx < 0 or idx >= pdoc.page_count:
            return None
        zoom = settings.render_dpi / 72.0
        pix = pdoc[idx].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        out_dir = os.path.join(settings.storage_dir, "pages")
        os.makedirs(out_dir, exist_ok=True)
        out = os.path.join(out_dir, f"{page.document_id}_page_{page.page_no:03d}.png")
        pix.save(out)
        pdoc.close()
        page.image_path = out
        db.commit()
        return out
    except Exception as exc:
        _log.warning("page %s re-render failed: %s", page.page_no, exc)
        return None


def _serve_page(page: models.Page | None, db: Session) -> FileResponse:
    if page and page.image_path and os.path.exists(page.image_path):
        return FileResponse(page.image_path, media_type="image/png")
    path = _rerender_from_pdf(page, db) if page else None
    if path:
        return FileResponse(path, media_type="image/png")
    raise HTTPException(404, "page image not available")


@router.get("/pages/{page_id}/image")
def page_image(page_id: str, db: Session = Depends(get_db)):
    return _serve_page(db.get(models.Page, page_id), db)


@router.get("/documents/{document_id}/pages/{page_no}/image")
def page_image_by_no(document_id: str, page_no: int, db: Session = Depends(get_db)):
    page = (db.query(models.Page)
            .filter(models.Page.document_id == document_id, models.Page.page_no == page_no)
            .first())
    return _serve_page(page, db)
