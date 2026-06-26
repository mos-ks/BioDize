"""Flag listing (dashboard)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.db import models
from app.schemas.schemas import FlagOut

router = APIRouter(prefix="/documents", tags=["flags"])


@router.get("/{document_id}/flags", response_model=list[FlagOut])
def list_flags(
    document_id: str,
    severity: str | None = None,
    category: str | None = None,
    db: Session = Depends(get_db),
) -> list[FlagOut]:
    q = (db.query(models.Flag)
         .join(models.Field, models.Flag.field_id == models.Field.id)
         .filter(models.Field.document_id == document_id))
    if severity:
        q = q.filter(models.Flag.severity == severity)
    if category:
        q = q.filter(models.Flag.category == category)
    return [FlagOut.model_validate(f) for f in q.all()]
