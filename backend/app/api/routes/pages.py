"""Page images and field crops for the bbox overlay."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.db import models

router = APIRouter(tags=["pages"])
_log = logging.getLogger(__name__)


def _cache_blob(page: models.Page, path: str, db: Session) -> None:
    """Store the rendered PNG in the DB so it's served fast and survives a restart."""
    if db.get(models.PageImage, page.id):
        return
    try:
        db.add(models.PageImage(page_id=page.id, data=Path(path).read_bytes()))
        db.commit()
    except Exception:
        db.rollback()


def _rerender_from_pdf(page: models.Page, db: Session) -> str | None:
    """Re-render one page from the stored source PDF, cache it to disk AND the DB.
    Used when the ephemeral image cache was wiped (e.g. a cloud restart) but the PDF
    bytes survive in a persistent DB. After this runs once, the page is served from
    the DB blob (no re-render). Returns the new path, or None."""
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
        _cache_blob(page, out, db)
        return out
    except Exception as exc:
        _log.warning("page %s re-render failed: %s", page.page_no, exc)
        return None


def _serve_page(page: models.Page | None, db: Session):
    # 1) disk cache (fastest)  2) DB blob (fast, persistent)  3) re-render from PDF
    if page and page.image_path and os.path.exists(page.image_path):
        return FileResponse(page.image_path, media_type="image/png")
    if page:
        blob = db.get(models.PageImage, page.id)
        if blob and blob.data:
            return Response(content=blob.data, media_type="image/png")
        path = _rerender_from_pdf(page, db)
        if path:
            return FileResponse(path, media_type="image/png")
    raise HTTPException(404, "page image not available")


def backfill_page_blobs() -> None:
    """One-time background job: for docs that have a stored PDF but no cached PNGs
    yet (processed before this feature), render every page once — loading the PDF
    blob a single time per doc — and cache it in the DB. After this, scans are fast
    and persist; subsequent restarts find nothing to do."""
    from app.db.base import SessionLocal
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return
    with SessionLocal() as db:
        doc_ids = [r[0] for r in db.query(models.DocumentPdf.document_id).all()]
        for doc_id in doc_ids:
            pages = db.query(models.Page).filter(models.Page.document_id == doc_id).all()
            todo = [p for p in pages if not db.get(models.PageImage, p.id)]
            if not todo:
                continue
            rec = db.get(models.DocumentPdf, doc_id)
            if not rec or not rec.data:
                continue
            try:
                pdoc = fitz.open(stream=rec.data, filetype="pdf")
            except Exception:
                continue
            zoom = settings.render_dpi / 72.0
            out_dir = os.path.join(settings.storage_dir, "pages")
            os.makedirs(out_dir, exist_ok=True)
            for p in todo:
                idx = p.page_no - 1
                if idx < 0 or idx >= pdoc.page_count:
                    continue
                try:
                    pix = pdoc[idx].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                    out = os.path.join(out_dir, f"{doc_id}_page_{p.page_no:03d}.png")
                    pix.save(out)
                    p.image_path = out
                    db.add(models.PageImage(page_id=p.id, data=Path(out).read_bytes()))
                    db.commit()
                except Exception:
                    db.rollback()
            pdoc.close()
            _log.info("backfilled %d page scans for %s", len(todo), doc_id)


@router.get("/pages/{page_id}/image")
def page_image(page_id: str, db: Session = Depends(get_db)):
    return _serve_page(db.get(models.Page, page_id), db)


@router.get("/documents/{document_id}/pages/{page_no}/image")
def page_image_by_no(document_id: str, page_no: int, db: Session = Depends(get_db)):
    page = (db.query(models.Page)
            .filter(models.Page.document_id == document_id, models.Page.page_no == page_no)
            .first())
    return _serve_page(page, db)
