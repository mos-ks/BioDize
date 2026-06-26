"""Document ingest + processing endpoints."""
from __future__ import annotations

import os
import shutil

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.db import models
from app.pipeline import orchestrator
from app.schemas.schemas import DocumentSummary, ProcessResult

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=dict)
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    os.makedirs(settings.storage_dir, exist_ok=True)
    dest = os.path.join(settings.storage_dir, file.filename or "upload.pdf")
    with open(dest, "wb") as out:
        shutil.copyfileobj(file.file, out)
    return {"source_path": dest, "filename": file.filename,
            "hint": "POST /documents/process to run the pipeline on this file."}


@router.post("/process", response_model=ProcessResult)
def process_document(source_path: str | None = None, db: Session = Depends(get_db)) -> ProcessResult:
    """Run the full pipeline. With EXTRACTOR=stub, source_path is optional."""
    if settings.extractor != "stub" and not source_path:
        raise HTTPException(400, "source_path is required unless EXTRACTOR=stub")
    summary = orchestrator.process(source_path, db)
    return ProcessResult(
        document_id=summary.document_id, status="processed", n_fields=summary.n_fields,
        n_errors=summary.n_errors, n_warnings=summary.n_warnings,
        n_auto_accepted=summary.n_auto_accepted, n_needs_review=summary.n_needs_review,
    )


@router.get("", response_model=list[DocumentSummary])
def list_documents(db: Session = Depends(get_db)) -> list[DocumentSummary]:
    docs = db.query(models.Document).order_by(models.Document.created_at.desc()).all()
    return [_summary(d, db) for d in docs]


@router.get("/{document_id}", response_model=DocumentSummary)
def get_document(document_id: str, db: Session = Depends(get_db)) -> DocumentSummary:
    doc = db.get(models.Document, document_id)
    if not doc:
        raise HTTPException(404, "document not found")
    return _summary(doc, db)


def _summary(doc: models.Document, db: Session) -> DocumentSummary:
    n_fields = db.query(func.count(models.Field.id)).filter(models.Field.document_id == doc.id).scalar() or 0
    n_review = (db.query(func.count(models.Field.id))
                .filter(models.Field.document_id == doc.id, models.Field.status == "needs_review").scalar() or 0)
    flags = (db.query(models.Flag.severity, func.count(models.Flag.id))
             .join(models.Field, models.Flag.field_id == models.Field.id)
             .filter(models.Field.document_id == doc.id).group_by(models.Flag.severity).all())
    counts = dict(flags)
    return DocumentSummary(
        id=doc.id, doc_no=doc.doc_no, title=doc.title, status=doc.status, page_count=doc.page_count,
        n_fields=n_fields, n_errors=counts.get("error", 0), n_warnings=counts.get("warning", 0),
        n_needs_review=n_review,
    )
