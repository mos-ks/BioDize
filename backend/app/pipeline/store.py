"""Persist a processed pipeline Document into the database."""
from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy.orm import Session

from app.db import models
from app.pipeline.model import Document


def _to_str(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "Ja" if value else "Nein"
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))          # IDs/counts: 1234567.0 -> "1234567"
    return str(value)


def persist(doc: Document, db: Session, page_images: dict[int, str] | None = None) -> str:
    page_images = page_images or {}
    row = models.Document(
        doc_no=doc.doc_no, title=doc.title, rev=doc.rev, project_code=doc.project_code,
        page_count=doc.page_count, declared_page_count=doc.declared_page_count,
        generated_at=doc.generated_at.isoformat() if doc.generated_at else None,
        source_path=doc.source_path, status="processed",
    )
    db.add(row)
    db.flush()

    for page_no in sorted({f.page_no for f in doc.all_fields()}):
        db.add(models.Page(document_id=row.id, page_no=page_no, image_path=page_images.get(page_no)))

    for block in doc.blocks:
        for fld in block.fields:
            mf = models.Field(
                document_id=row.id, chapter=fld.chapter, block_key=block.key, page_no=fld.page_no,
                role=fld.role, label_raw=fld.label_raw, value_raw=fld.value_raw,
                value_norm=_to_str(fld.value), value_type=fld.value_type, unit=fld.unit,
                is_handwritten=fld.is_handwritten,
                is_verified=fld.is_verified, verified_reason=fld.verified_reason,
                nks=fld.nks, bbox=fld.bbox.to_list() if fld.bbox else None,
                confidence=fld.confidence, status=fld.status.value, is_required=fld.is_required,
            )
            db.add(mf)
            db.flush()
            for r in fld.reads:
                db.add(models.FieldRead(
                    field_id=mf.id, model=r.model, value_raw=r.value_raw,
                    confidence=r.confidence, bbox_raw=r.bbox.to_list() if r.bbox else None,
                ))
            for fl in fld.flags:
                db.add(models.Flag(
                    field_id=mf.id, block_key=block.key, severity=fl.severity.value,
                    category=fl.category.value, code=fl.code, message=fl.message,
                    expected=fl.expected, actual=fl.actual,
                ))

    db.commit()
    return row.id
