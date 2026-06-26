"""Internal pipeline data model.

Plain dataclasses that flow through the pipeline and get progressively enriched:
  extract  -> Field(value_raw, reads, ...)
  localize -> Field.bbox
  normalize-> Field.value, value_type, decimals, role (confirmed)
  validate -> Field.flags
  uncertainty -> Field.confidence, Field.status

Kept separate from the SQLAlchemy ORM (`db/models.py`) and the API DTOs
(`schemas/schemas.py`) so the rules/normalize logic stay pure and unit-testable.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.domain.severity import Category, FieldStatus, Severity


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


@dataclass
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float

    def to_list(self) -> list[float]:
        return [self.x0, self.y0, self.x1, self.y1]


@dataclass
class Read:
    """One model's reading of one field (ensemble-ready; usually one)."""
    model: str
    value_raw: str
    confidence: float = 0.5
    bbox: BBox | None = None


@dataclass
class Flag:
    severity: Severity
    category: Category
    code: str
    message: str
    expected: str | None = None
    actual: str | None = None


@dataclass
class Field:
    page_no: int
    chapter: str
    role: str | None
    label_raw: str
    value_raw: str
    key: str = field(default_factory=lambda: _id("f"))
    block_key: str = ""
    unit: str | None = None
    nks: int | None = None            # required decimal places, if the form states it
    soll: str | None = None           # raw "Soll: ..." text, if present
    calc_expr: str | None = None      # printed formula with handwritten numbers substituted
    is_required: bool = True
    bbox: BBox | None = None
    reads: list[Read] = field(default_factory=list)

    # enriched by normalize
    value: Any = None
    value_type: str | None = None     # number|date|time|datetime|bool|text|checkbox
    decimals: int | None = None

    # enriched by localize (OCR per-word confidence of the matched token)
    ocr_confidence: float | None = None
    # enriched by validate / uncertainty
    confidence: float = 0.0
    status: FieldStatus = FieldStatus.EXTRACTED
    flags: list[Flag] = field(default_factory=list)

    def add_flag(self, flag: Flag) -> None:
        self.flags.append(flag)

    @property
    def has_error(self) -> bool:
        return any(f.severity is Severity.ERROR for f in self.flags)

    @property
    def has_warning(self) -> bool:
        return any(f.severity is Severity.WARNING for f in self.flags)


@dataclass
class Block:
    chapter: str
    page_no: int
    template: str                      # bilanzierung|calc|equipment|gate|signature|range|...
    key: str = field(default_factory=lambda: _id("b"))
    applicability: str = "applicable"  # applicable|na_field|na_block|na_chapter|na_rest|redirect
    applicability_source: str | None = None
    fields: list[Field] = field(default_factory=list)

    def role(self, role: str) -> Field | None:
        return next((f for f in self.fields if f.role == role), None)

    def roles(self, role: str) -> list[Field]:
        return [f for f in self.fields if f.role == role]


@dataclass
class Document:
    doc_no: str
    title: str
    key: str = field(default_factory=lambda: _id("d"))
    rev: str | None = None
    project_code: str | None = None
    generated_at: date | None = None   # print date — temporal lower bound
    page_count: int = 0
    declared_page_count: int | None = None
    source_path: str | None = None
    blocks: list[Block] = field(default_factory=list)

    def all_fields(self) -> list[Field]:
        return [f for b in self.blocks for f in b.fields]
