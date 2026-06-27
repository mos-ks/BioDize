"""Document ingest + processing endpoints."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.db import models
from app.pipeline import orchestrator
from app.schemas.schemas import DocumentSummary, ProcessResult

router = APIRouter(prefix="/documents", tags=["documents"])

# repo-root/ground_truth (backend/app/api/routes/documents.py -> repo root is parents[4])
_GOLD_DIR = Path(__file__).resolve().parents[4] / "ground_truth"


@router.post("", response_model=dict)
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    os.makedirs(settings.storage_dir, exist_ok=True)
    dest = os.path.join(settings.storage_dir, file.filename or "upload.pdf")
    with open(dest, "wb") as out:
        shutil.copyfileobj(file.file, out)
    return {"source_path": dest, "filename": file.filename,
            "hint": "POST /documents/process to run the pipeline on this file."}


@router.post("/process", response_model=ProcessResult)
def process_document(
    source_path: str | None = None,
    max_pages: int | None = None,
    db: Session = Depends(get_db),
) -> ProcessResult:
    """Run the full pipeline. With EXTRACTOR=stub, source_path is ignored.
    Otherwise, defaults to the bundled sample scan when source_path is omitted.
    Pass max_pages=N for a cheap first run (limits model calls)."""
    if settings.extractor != "stub" and not source_path:
        if os.path.exists(settings.sample_pdf_path):
            source_path = settings.sample_pdf_path
        else:
            raise HTTPException(400, "source_path is required (sample PDF not found)")
    summary = orchestrator.process(source_path, db, max_pages=max_pages)
    return _process_result(summary)


@router.post("/simulate", response_model=ProcessResult)
def simulate_document(db: Session = Depends(get_db)) -> ProcessResult:
    """Create the next simulated demo batch (offline, no upload, no API calls).
    Always uses the stub regardless of the configured extractor, cycling through
    the three 'Simulated' batches."""
    from app.pipeline.extract.stub import SIMULATE_NEXT
    summary = orchestrator.process(SIMULATE_NEXT, db, force_extractor="stub")
    return _process_result(summary)


def _process_result(summary) -> ProcessResult:
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


@router.delete("/{document_id}", response_model=dict)
def delete_document(document_id: str, db: Session = Depends(get_db)) -> dict:
    """Delete a batch record and all its pages/fields/flags (ORM cascade)."""
    doc = db.get(models.Document, document_id)
    if not doc:
        raise HTTPException(404, "document not found")
    db.delete(doc)
    db.commit()
    return {"deleted": document_id}


@router.get("/{document_id}/evaluation", response_model=dict)
def evaluate_document(document_id: str, db: Session = Depends(get_db)) -> dict:
    """Score this document's STORED flags + values against the ground-truth gold
    set (ground_truth/) and return the scorecard: rule precision/recall/F1, value/
    checkbox/signature accuracy, coverage, and per-page pass/fail. Computed on
    demand (deterministic, no model calls), so the UI can re-run it any time."""
    doc = db.get(models.Document, document_id)
    if not doc:
        raise HTTPException(404, "document not found")
    if not _GOLD_DIR.exists():
        raise HTTPException(404, "ground_truth/ not found on the server")
    from app.evaluation.scorer import score_ground_truth
    report = score_ground_truth(_rebuild_document(doc, db), _GOLD_DIR)
    result = report.as_dict()
    result["document_id"] = doc.id
    result["gold_pages"] = len(result.get("pages", []))
    return result


def _rebuild_document(doc: models.Document, db: Session):
    """Reconstruct an app.pipeline.model.Document from the STORED rows (fields +
    flags) so the scorer sees exactly what the pipeline committed — no re-validation."""
    from app.domain.severity import Category, Severity
    from app.pipeline.model import Block, Document, Field, Flag

    pdoc = Document(doc_no=doc.doc_no or "doc", title=doc.title or "doc")
    blocks: dict[int, Block] = {}
    for fr in db.query(models.Field).filter(models.Field.document_id == doc.id).all():
        b = blocks.get(fr.page_no)
        if b is None:
            b = Block(chapter=fr.chapter or "", page_no=fr.page_no, template="stored")
            blocks[fr.page_no] = b
        pf = Field(page_no=fr.page_no, chapter=fr.chapter or "", role=fr.role,
                   label_raw=fr.label_raw or "", value_raw=fr.value_raw or "")
        pf.value = fr.value_norm
        pf.value_type = fr.value_type
        for fl in fr.flags:
            try:
                sev, cat = Severity(fl.severity), Category(fl.category)
            except ValueError:
                continue
            pf.flags.append(Flag(sev, cat, fl.code, fl.message or "", fl.expected, fl.actual))
        b.fields.append(pf)
    pdoc.blocks = list(blocks.values())
    return pdoc


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
        n_needs_review=n_review, processing_ms=getattr(doc, "processing_ms", None),
    )
