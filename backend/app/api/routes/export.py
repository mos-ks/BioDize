"""Export endpoints: Excel (.xlsx) und CSV."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db import models
from app.pipeline.export import export_changelog_csv, export_csv, export_xlsx

router = APIRouter(prefix="/documents", tags=["export"])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_CSV  = "text/csv; charset=utf-8"


def _doc_or_404(document_id: str, db: Session):
    doc = db.get(models.Document, document_id)
    if not doc:
        raise HTTPException(404, "document not found")
    return doc


def _safe_name(doc, document_id: str) -> str:
    """ASCII-safe filename — Content-Disposition can't carry '·', spaces, etc."""
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", (doc.doc_no or document_id)).strip("_")
    return base or document_id


@router.get("/{document_id}/export.xlsx")
def export_document_xlsx(document_id: str, db: Session = Depends(get_db)) -> Response:
    doc = _doc_or_404(document_id, db)
    safe = _safe_name(doc, document_id)
    data = export_xlsx(document_id, db)
    return Response(
        content=data, media_type=_XLSX,
        headers={"Content-Disposition": f'attachment; filename="{safe}.xlsx"'},
    )


@router.get("/{document_id}/export.csv")
def export_document_csv(document_id: str, db: Session = Depends(get_db)) -> Response:
    doc = _doc_or_404(document_id, db)
    safe = _safe_name(doc, document_id)
    data = export_csv(document_id, db)
    return Response(
        content=data, media_type=_CSV,
        headers={"Content-Disposition": f'attachment; filename="{safe}.csv"'},
    )


@router.get("/{document_id}/changes.csv")
def export_document_changes(document_id: str, db: Session = Depends(get_db)) -> Response:
    """The change log: every human correction / confirmation / annotation."""
    doc = _doc_or_404(document_id, db)
    safe = _safe_name(doc, document_id)
    data = export_changelog_csv(document_id, db)
    return Response(
        content=data, media_type=_CSV,
        headers={"Content-Disposition": f'attachment; filename="{safe}_changelog.csv"'},
    )
