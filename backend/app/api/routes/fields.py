"""Field listing, review queue, and human corrections."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db import models
from app.schemas.schemas import CorrectionIn, FieldOut

router = APIRouter(tags=["fields"])

# Review-queue ordering: errors first, then warnings, then low confidence.
_SEVERITY_RANK = {"error": 0, "warning": 1}


@router.get("/documents/{document_id}/fields", response_model=list[FieldOut])
def list_fields(
    document_id: str,
    status: str | None = None,
    severity: str | None = None,
    category: str | None = None,
    page_no: int | None = None,
    role: str | None = None,
    db: Session = Depends(get_db),
) -> list[FieldOut]:
    q = db.query(models.Field).filter(models.Field.document_id == document_id)
    if status:
        q = q.filter(models.Field.status == status)
    if page_no is not None:
        q = q.filter(models.Field.page_no == page_no)
    if role:
        q = q.filter(models.Field.role == role)
    fields = q.order_by(models.Field.page_no).all()

    out = [FieldOut.from_orm_field(f) for f in fields]
    if severity:
        out = [f for f in out if any(fl.severity == severity for fl in f.flags)]
    if category:
        out = [f for f in out if any(fl.category == category for fl in f.flags)]
    return out


@router.get("/documents/{document_id}/queue", response_model=list[FieldOut])
def review_queue(document_id: str, db: Session = Depends(get_db)) -> list[FieldOut]:
    fields = (db.query(models.Field)
              .filter(models.Field.document_id == document_id,
                      models.Field.status == "needs_review").all())
    out = [FieldOut.from_orm_field(f) for f in fields]

    def rank(f: FieldOut):
        best = min((_SEVERITY_RANK.get(fl.severity, 2) for fl in f.flags), default=3)
        return (best, f.confidence)

    return sorted(out, key=rank)


@router.get("/fields/{field_id}", response_model=FieldOut)
def get_field(field_id: str, db: Session = Depends(get_db)) -> FieldOut:
    f = db.get(models.Field, field_id)
    if not f:
        raise HTTPException(404, "field not found")
    return FieldOut.from_orm_field(f)


@router.patch("/fields/{field_id}", response_model=FieldOut)
def correct_field(field_id: str, body: CorrectionIn, db: Session = Depends(get_db)) -> FieldOut:
    """Human confirm/correct a value. Audit-logged; sets status accordingly."""
    f = db.get(models.Field, field_id)
    if not f:
        raise HTTPException(404, "field not found")

    old = f.value_norm
    if body.action == "correct" and body.value is not None:
        f.value_norm = body.value
        f.value_raw = body.value
        f.source = "human"
        f.status = "corrected"
    else:
        f.status = "confirmed"
    f.confidence = 1.0

    db.add(models.Correction(field_id=f.id, old_value=old, new_value=f.value_norm,
                             action=body.action, reason=body.reason, actor=body.actor))
    db.add(models.AuditLog(entity_type="field", entity_id=f.id, action=body.action,
                           actor=body.actor, before={"value": old}, after={"value": f.value_norm}))
    # TODO: re-run rules dependent on this field (e.g. correcting tare re-checks net).
    db.commit()
    db.refresh(f)
    return FieldOut.from_orm_field(f)
