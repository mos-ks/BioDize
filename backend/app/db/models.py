"""SQLAlchemy ORM models. Mirrors docs/DATA_MODEL.md.

Hierarchy: Document -> Chapter -> Block -> Field -> FieldRead, plus Flag,
Correction, AuditLog and RoleStat (historical aggregates for priors).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid(prefix: str):
    return lambda: f"{prefix}_{uuid.uuid4().hex[:12]}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid("d"))
    batch_no: Mapped[str | None] = mapped_column(String, nullable=True)
    doc_no: Mapped[str] = mapped_column(String, index=True)        # hardcoded, e.g. AB-ABC-123456
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    rev: Mapped[str | None] = mapped_column(String, nullable=True)
    project_code: Mapped[str | None] = mapped_column(String, nullable=True)
    source_path: Mapped[str | None] = mapped_column(String, nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    declared_page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    generated_at: Mapped[str | None] = mapped_column(String, nullable=True)  # print date (ISO)
    status: Mapped[str] = mapped_column(String, default="uploaded")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    pages: Mapped[list["Page"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    fields: Mapped[list["Field"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid("p"))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    page_no: Mapped[int] = mapped_column(Integer)                  # hardcoded
    image_path: Mapped[str | None] = mapped_column(String, nullable=True)
    is_blank: Mapped[bool] = mapped_column(Boolean, default=False)
    has_kreuzung: Mapped[bool] = mapped_column(Boolean, default=False)

    document: Mapped[Document] = relationship(back_populates="pages")


class Field(Base):
    __tablename__ = "fields"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid("f"))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    chapter: Mapped[str | None] = mapped_column(String, nullable=True)
    block_key: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    page_no: Mapped[int] = mapped_column(Integer, index=True)
    role: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    label_raw: Mapped[str | None] = mapped_column(String, nullable=True)
    value_raw: Mapped[str | None] = mapped_column(String, nullable=True)
    value_norm: Mapped[str | None] = mapped_column(String, nullable=True)
    value_type: Mapped[str | None] = mapped_column(String, nullable=True)
    unit: Mapped[str | None] = mapped_column(String, nullable=True)
    nks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bbox: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [x0,y0,x1,y1] normalized
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str] = mapped_column(String, default="model")    # model|ocr|human
    status: Mapped[str] = mapped_column(String, default="extracted", index=True)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    document: Mapped[Document] = relationship(back_populates="fields")
    reads: Mapped[list["FieldRead"]] = relationship(back_populates="field", cascade="all, delete-orphan")
    flags: Mapped[list["Flag"]] = relationship(back_populates="field", cascade="all, delete-orphan")
    corrections: Mapped[list["Correction"]] = relationship(back_populates="field", cascade="all, delete-orphan")


class FieldRead(Base):
    __tablename__ = "field_reads"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid("r"))
    field_id: Mapped[str] = mapped_column(ForeignKey("fields.id"), index=True)
    model: Mapped[str] = mapped_column(String)
    value_raw: Mapped[str | None] = mapped_column(String, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    bbox_raw: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    field: Mapped[Field] = relationship(back_populates="reads")


class Flag(Base):
    __tablename__ = "flags"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid("fl"))
    field_id: Mapped[str | None] = mapped_column(ForeignKey("fields.id"), index=True, nullable=True)
    block_key: Mapped[str | None] = mapped_column(String, nullable=True)
    severity: Mapped[str] = mapped_column(String, index=True)       # error|warning
    category: Mapped[str] = mapped_column(String, index=True)
    code: Mapped[str] = mapped_column(String)
    message: Mapped[str] = mapped_column(Text)
    expected: Mapped[str | None] = mapped_column(String, nullable=True)
    actual: Mapped[str | None] = mapped_column(String, nullable=True)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    field: Mapped[Field | None] = relationship(back_populates="flags")


class Correction(Base):
    __tablename__ = "corrections"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid("c"))
    field_id: Mapped[str] = mapped_column(ForeignKey("fields.id"), index=True)
    old_value: Mapped[str | None] = mapped_column(String, nullable=True)
    new_value: Mapped[str | None] = mapped_column(String, nullable=True)
    action: Mapped[str] = mapped_column(String)                     # confirm|correct
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    actor: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    field: Mapped[Field] = relationship(back_populates="corrections")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid("a"))
    entity_type: Mapped[str] = mapped_column(String)
    entity_id: Mapped[str] = mapped_column(String, index=True)
    action: Mapped[str] = mapped_column(String)
    actor: Mapped[str | None] = mapped_column(String, nullable=True)
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class RoleStat(Base):
    """Running aggregates per role for Bayesian priors / distribution plots."""
    __tablename__ = "role_stats"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid("rs"))
    role: Mapped[str] = mapped_column(String, index=True)
    unit: Mapped[str | None] = mapped_column(String, nullable=True)
    n: Mapped[int] = mapped_column(Integer, default=0)
    mean: Mapped[float] = mapped_column(Float, default=0.0)
    m2: Mapped[float] = mapped_column(Float, default=0.0)            # sum of squares for running variance
    min: Mapped[float | None] = mapped_column(Float, nullable=True)
    max: Mapped[float | None] = mapped_column(Float, nullable=True)
    samples: Mapped[list | None] = mapped_column(JSON, nullable=True)  # recent values for histogram/KDE
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
