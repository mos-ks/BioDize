"""Export endpoints: Excel (.xlsx) und CSV."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db import models
from app.pipeline.export import export_csv, export_xlsx

router = APIRouter(prefix="/documents", tags=["export"])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_CSV  = "text/csv; charset=utf-8"


def _doc_or_404(document_id: str, db: Session):
    doc = db.get(models.Document, document_id)
    if not doc:
        raise HTTPException(404, "document not found")
    return doc


@router.get("/{document_id}/export.xlsx")
def export_document_xlsx(document_id: str, db: Session = Depends(get_db)) -> Response:
    doc = _doc_or_404(document_id, db)
    safe = (doc.doc_no or document_id).replace("/", "_").replace(" ", "_")
    data = export_xlsx(document_id, db)
    return Response(
        content=data, media_type=_XLSX,
        headers={"Content-Disposition": f'attachment; filename="{safe}.xlsx"'},
    )


@router.get("/{document_id}/export.csv")
def export_document_csv(document_id: str, db: Session = Depends(get_db)) -> Response:
    doc = _doc_or_404(document_id, db)
    safe = (doc.doc_no or document_id).replace("/", "_").replace(" ", "_")
    data = export_csv(document_id, db)
    return Response(
        content=data, media_type=_CSV,
        headers={"Content-Disposition": f'attachment; filename="{safe}.csv"'},
    )
