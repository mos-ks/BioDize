"""Helpers for evaluating a stored ``results/extracted_fields.json`` run.

The exported results already contain production flags.  Ground-truth scoring
should keep those flags, then run the local validators as an additive safety net
for rules that can be reconstructed from the flat field export.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from app.domain.severity import Category, FieldStatus, Severity
from app.pipeline.model import BBox, Block, Document, Field, Flag, Read
from app.pipeline.normalize import normalize
from app.pipeline.resolve import resolve
from app.pipeline.validate.engine import validate
from app.pipeline.validate.uncertainty import score


def _enum_or(enum_cls, raw: Any, default):
    if isinstance(raw, enum_cls):
        return raw
    try:
        return enum_cls(raw)
    except Exception:
        return default


def _date_or_none(raw: Any) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def _flag_from_json(raw: dict[str, Any]) -> Flag:
    return Flag(
        severity=_enum_or(Severity, raw.get("severity"), Severity.ERROR),
        category=_enum_or(Category, raw.get("category"), Category.EXTRACTION),
        code=str(raw.get("code") or "UNKNOWN"),
        message=str(raw.get("message") or ""),
        expected=raw.get("expected"),
        actual=raw.get("actual"),
    )


def document_from_results(
    results_json: Path,
    *,
    model_name: str = "results",
    preserve_flags: bool = True,
    run_validation: bool = True,
    run_uncertainty: bool = True,
) -> Document:
    """Build a pipeline ``Document`` from an exported results JSON file."""
    data = json.loads(results_json.read_text(encoding="utf-8"))
    meta = data.get("document") or {}
    entries = data.get("fields") or []

    doc = Document(
        doc_no=meta.get("doc_no") or meta.get("id") or results_json.stem,
        title=meta.get("title") or meta.get("doc_no") or results_json.name,
        key=meta.get("id") or f"d_{results_json.stem}",
        generated_at=_date_or_none(meta.get("generated_at")),
        page_count=int(meta.get("page_count") or 0),
    )

    blocks: dict[tuple[str, int], Block] = {}
    for entry in entries:
        chapter = (entry.get("chapter") or "").strip()
        page_no = int(entry["page_no"])
        block_key = (chapter, page_no)
        if block_key not in blocks:
            blocks[block_key] = Block(chapter=chapter, page_no=page_no, template="results")
        block = blocks[block_key]

        bbox_raw = entry.get("bbox")
        bbox = BBox(*bbox_raw) if bbox_raw and len(bbox_raw) == 4 else None
        value_raw = str(entry.get("value_raw") or entry.get("value") or "")
        field = Field(
            page_no=page_no,
            chapter=chapter,
            role=entry.get("role"),
            label_raw=entry.get("label") or "",
            value_raw=value_raw,
            key=entry.get("id") or f"f_{page_no}_{len(block.fields)}",
            unit=entry.get("unit"),
            nks=entry.get("nks"),
            soll=entry.get("soll"),
            calc_expr=entry.get("calc_expr"),
            bbox=bbox,
            confidence=float(entry.get("confidence") or 0.0),
            status=_enum_or(FieldStatus, entry.get("status"), FieldStatus.EXTRACTED),
        )
        field.reads = [
            Read(
                model=model_name,
                value_raw=value_raw,
                confidence=float(entry.get("confidence") or 1.0),
                bbox=bbox,
            )
        ]
        if preserve_flags:
            field.flags.extend(_flag_from_json(flag) for flag in entry.get("flags", []))
        block.fields.append(field)
        field.block_key = block.key

    doc.blocks = list(blocks.values())
    normalize(doc)
    resolve(doc)
    if run_validation:
        validate(doc)
    if run_uncertainty:
        score(doc)
    return doc
