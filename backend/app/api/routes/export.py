"""Excel export endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db import models
from app.pipeline.export import export_xlsx

router = APIRouter(prefix="/documents", tags=["export"])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/{document_id}/export.xlsx")
def export_document(document_id: str, db: Session = Depends(get_db)) -> Response:
    if not db.get(models.Document, document_id):
        raise HTTPException(404, "document not found")
    data = export_xlsx(document_id, db)
    return Response(
        content=data, media_type=_XLSX,
        headers={"Content-Disposition": f'attachment; filename="{document_id}.xlsx"'},
    )
