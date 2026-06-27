"""Field listing, review queue, and human corrections."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db import models
from app.schemas.schemas import AnnotationIn, CorrectionIn, FieldOut

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


@router.post("/documents/{document_id}/annotations", response_model=FieldOut)
def add_annotation(document_id: str, body: AnnotationIn, db: Session = Depends(get_db)) -> FieldOut:
    """A human drew a box on the PDF: create a HUMAN-LABELED field entry (with that
    box) so it lands in the database and the review list. Audit-logged."""
    if not db.get(models.Document, document_id):
        raise HTTPException(404, "document not found")
    flagged = body.severity in ("error", "warning")
    # The human's tag becomes the flag's code chip (e.g. "Rounding" -> ROUNDING).
    code = "".join(c if c.isalnum() else "_" for c in (body.tag or "").strip().upper())
    code = "_".join(p for p in code.split("_") if p)[:32] or "HUMAN_LABELED"
    mf = models.Field(
        document_id=document_id, page_no=body.page_no, chapter=None, block_key="human",
        role=None, label_raw=body.label or "Human annotation",
        value_raw=body.value, value_norm=body.value, value_type=None, unit=None, nks=None,
        bbox=[round(v, 6) for v in body.bbox] if body.bbox else None,
        confidence=1.0, source="human",
        status="needs_review" if flagged else "confirmed", is_required=False,
    )
    db.add(mf)
    db.flush()
    if flagged:
        db.add(models.Flag(
            field_id=mf.id, block_key="human", severity=body.severity, category="human",
            code=code, message=body.label or body.note or "Human-labeled entry",
            expected=None, actual=body.value,
        ))
    db.add(models.AuditLog(
        entity_type="field", entity_id=mf.id, action="annotate", actor=body.actor,
        before=None,
        after={"label": body.label, "value": body.value, "bbox": mf.bbox, "severity": body.severity},
    ))
    db.commit()
    db.refresh(mf)
    return FieldOut.from_orm_field(mf)


@router.patch("/fields/{field_id}", response_model=FieldOut)
def correct_field(field_id: str, body: CorrectionIn, db: Session = Depends(get_db)) -> FieldOut:
    """Human confirm/correct a value. Audit-logged; sets status accordingly."""
    f = db.get(models.Field, field_id)
    if not f:
        raise HTTPException(404, "field not found")

    old_value = f.value_norm
    old_bbox  = f.bbox

    if body.action == "set_bbox":
        # Nur Bounding-Box aktualisieren, Wert unveraendert
        if body.bbox is not None:
            f.bbox = [round(v, 6) for v in body.bbox]
        db.add(models.AuditLog(entity_type="field", entity_id=f.id, action="set_bbox",
                               actor=body.actor, before={"bbox": old_bbox},
                               after={"bbox": f.bbox}))
    elif body.action == "delete_bbox":
        f.bbox = None
        db.add(models.AuditLog(entity_type="field", entity_id=f.id, action="delete_bbox",
                               actor=body.actor, before={"bbox": old_bbox}, after={"bbox": None}))
    else:
        if body.action == "correct" and body.value is not None:
            f.value_norm = body.value
            f.value_raw  = body.value
            f.source     = "human"
            f.status     = "corrected"
        else:
            f.status = "confirmed"
        f.confidence = 1.0
        # Bbox gleichzeitig setzen falls mitgeliefert
        if body.bbox is not None:
            f.bbox = [round(v, 6) for v in body.bbox]
        db.add(models.Correction(field_id=f.id, old_value=old_value,
                                 new_value=f.value_norm, action=body.action,
                                 reason=body.reason, actor=body.actor))
        db.add(models.AuditLog(entity_type="field", entity_id=f.id,
                               action=body.action, actor=body.actor,
                               before={"value": old_value, "bbox": old_bbox},
                               after={"value": f.value_norm, "bbox": f.bbox}))

    db.commit(); db.refresh(f)
    return FieldOut.from_orm_field(f)
