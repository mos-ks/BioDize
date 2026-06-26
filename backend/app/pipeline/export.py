"""Excel export — a tidy sheet (1 row/parameter) + a wide pivot (1 row/batch)."""
from __future__ import annotations

import io

from sqlalchemy.orm import Session

from app.db import models

TIDY_HEADER = ["document", "page", "chapter", "role", "label", "value", "unit",
               "status", "confidence", "flags"]


def export_xlsx(document_id: str, db: Session) -> bytes:
    try:
        from openpyxl import Workbook
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("`pip install openpyxl` to export Excel.") from exc

    doc = db.get(models.Document, document_id)
    fields = (
        db.query(models.Field)
        .filter(models.Field.document_id == document_id)
        .order_by(models.Field.page_no)
        .all()
    )

    wb = Workbook()

    tidy = wb.active
    tidy.title = "tidy"
    tidy.append(TIDY_HEADER)
    for f in fields:
        flag_txt = "; ".join(f"{fl.severity}:{fl.code}" for fl in f.flags)
        tidy.append([
            doc.doc_no if doc else document_id, f.page_no, f.chapter, f.role, f.label_raw,
            f.value_norm if f.value_norm is not None else f.value_raw, f.unit,
            f.status, round(f.confidence, 3), flag_txt,
        ])

    # Wide pivot: one row, parameters (role) as columns. Last value wins on dupes.
    pivot = wb.create_sheet("pivot")
    roles = sorted({f.role for f in fields if f.role})
    pivot.append(["document"] + roles)
    by_role = {f.role: (f.value_norm if f.value_norm is not None else f.value_raw) for f in fields if f.role}
    pivot.append([doc.doc_no if doc else document_id] + [by_role.get(r) for r in roles])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
