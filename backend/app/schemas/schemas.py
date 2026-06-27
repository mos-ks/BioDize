"""Pydantic DTOs for the API (mirrors docs/API.md)."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class FlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    severity: str
    category: str
    code: str
    message: str
    expected: str | None = None
    actual: str | None = None


class ReadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    model: str
    value_raw: str | None = None
    confidence: float


class FieldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    document_id: str
    chapter: str | None = None
    block_key: str | None = None
    page_no: int
    role: str | None = None
    label_raw: str | None = None
    value: str | None = None          # normalized (value_norm)
    value_raw: str | None = None
    unit: str | None = None
    nks: int | None = None
    bbox: list[float] | None = None
    confidence: float
    status: str
    is_handwritten: bool | None = None
    is_verified: bool = False
    verified_reason: str | None = None
    reads: list[ReadOut] = []
    flags: list[FlagOut] = []

    @classmethod
    def from_orm_field(cls, f) -> "FieldOut":
        return cls(
            id=f.id, document_id=f.document_id, chapter=f.chapter, block_key=f.block_key,
            page_no=f.page_no, role=f.role, label_raw=f.label_raw, value=f.value_norm,
            value_raw=f.value_raw, unit=f.unit, nks=f.nks, bbox=f.bbox,
            confidence=f.confidence, status=f.status, is_handwritten=getattr(f, "is_handwritten", None),
            is_verified=bool(getattr(f, "is_verified", None)),  # coerce NULL (old rows) -> False
            verified_reason=getattr(f, "verified_reason", None),
            reads=[ReadOut.model_validate(r) for r in f.reads],
            flags=[FlagOut.model_validate(fl) for fl in f.flags],
        )


class DocumentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    doc_no: str
    title: str | None = None
    status: str
    page_count: int
    n_fields: int = 0
    n_errors: int = 0
    n_warnings: int = 0
    n_needs_review: int = 0
    processing_ms: int | None = None


class CorrectionIn(BaseModel):
    value: str | None = None
    action: str = "confirm"           # confirm | correct | set_bbox | delete_bbox
    reason: str | None = None
    actor: str | None = None
    bbox: list[float] | None = None   # [x0,y0,x1,y1] normiert 0-1


class AnnotationIn(BaseModel):
    """A human-placed flag on the PDF that becomes a human-labeled entry."""
    page_no: int
    bbox: list[float] | None = None   # [x0,y0,x1,y1] normalized 0-1
    label: str | None = None          # the title
    tag: str | None = None            # short category tag -> becomes the flag code chip
    value: str | None = None
    note: str | None = None
    severity: str | None = None       # error | warning | None (just a note)
    actor: str | None = None


class ProcessResult(BaseModel):
    document_id: str
    status: str
    n_fields: int
    n_errors: int
    n_warnings: int
    n_auto_accepted: int
    n_needs_review: int


class DistributionOut(BaseModel):
    role: str
    n: int
    mean: float | None = None
    std: float | None = None
    min: float | None = None
    max: float | None = None
    histogram: list[dict] = []
