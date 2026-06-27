"""Serialize a STORED DB Document back into the ``results/extracted_fields.json``
shape that :func:`app.evaluation.results_loader.document_from_results` consumes.

This is what powers the "Re-eval" button: it lets the scorecard reflect the
*current* pipeline run instead of the frozen committed snapshot. No model calls —
it reads the already-extracted DB rows (incl. their stored flags), so it never
spends credits. Fields the DB schema doesn't persist (soll/calc_expr) are omitted;
the validators that need them rely on the preserved stored flags instead.
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.db import models


def document_to_results(doc: models.Document, db: Session) -> dict:
    """Build the export dict (``{"document": {...}, "fields": [...]}``) for one doc."""
    rows = (
        db.query(models.Field)
        .filter(models.Field.document_id == doc.id)
        .order_by(models.Field.page_no)
        .all()
    )
    entries: list[dict] = []
    for f in rows:
        entries.append({
            "id": f.id,
            "page_no": f.page_no,
            "chapter": f.chapter or "",
            "role": f.role,
            "label": f.label_raw or "",
            "value_raw": f.value_raw or "",
            # `value` is the normalized read the scorer compares against gold.
            "value": f.value_norm if f.value_norm is not None else (f.value_raw or ""),
            "unit": f.unit,
            "nks": f.nks,
            "bbox": f.bbox,
            "confidence": f.confidence or 0.0,
            "status": f.status,
            "flags": [
                {
                    "severity": fl.severity,
                    "category": fl.category,
                    "code": fl.code,
                    "message": fl.message or "",
                    "expected": fl.expected,
                    "actual": fl.actual,
                }
                for fl in f.flags
            ],
        })
    return {
        "document": {
            "id": doc.id,
            "doc_no": doc.doc_no,
            "title": doc.title,
            "generated_at": doc.generated_at,
            "page_count": doc.page_count,
        },
        "fields": entries,
    }


def write_results(doc: models.Document, db: Session, path: Path) -> int:
    """Dump ``doc`` to ``path`` as JSON; returns the number of fields written."""
    payload = document_to_results(doc, db)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(payload["fields"])
