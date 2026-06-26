"""Page images and field crops for the bbox overlay."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db import models

router = APIRouter(tags=["pages"])


@router.get("/pages/{page_id}/image")
def page_image(page_id: str, db: Session = Depends(get_db)):
    page = db.get(models.Page, page_id)
    if not page or not page.image_path or not os.path.exists(page.image_path):
        raise HTTPException(404, "page image not available (stub pipeline renders no images)")
    return FileResponse(page.image_path, media_type="image/png")


@router.get("/documents/{document_id}/pages/{page_no}/image")
def page_image_by_no(document_id: str, page_no: int, db: Session = Depends(get_db)):
    page = (db.query(models.Page)
            .filter(models.Page.document_id == document_id, models.Page.page_no == page_no)
            .first())
    if not page or not page.image_path or not os.path.exists(page.image_path):
        raise HTTPException(404, "page image not available")
    return FileResponse(page.image_path, media_type="image/png")
