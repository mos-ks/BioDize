"""Cross-document value history.

Flags when a numeric parameter reads SUDDENLY differently than it has in prior
batch records — the "you have a database, check if this one parameter is now
different" idea. Complements within-document anomaly detection (STAT_OUTLIER): here
the peers are the SAME parameter in OTHER documents, identified by a stable
signature (role | normalized-label | unit).
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import models
from app.domain.roles import NUMERIC_ROLES
from app.domain.severity import Category, Severity
from app.pipeline.model import Document, Field, Flag


def _param_key(field: Field) -> str | None:
    if field.role not in NUMERIC_ROLES:
        return None
    label = re.sub(r"[^0-9a-zäöüß ]+", " ", (field.label_raw or "").lower())
    label = re.sub(r"\s+", " ", label).strip()
    if not label:
        return None
    return f"{field.role}|{label}|{(field.unit or '').lower()}"


def _numeric(field: Field) -> float | None:
    if isinstance(field.value, (int, float)) and not isinstance(field.value, bool):
        return float(field.value)
    return None


def check_consistency(doc: Document, db: Session) -> None:
    """Add CROSS_DOC_DRIFT warnings for values that depart from this parameter's
    history across previously-processed records. No history yet → nothing to flag."""
    k = settings.outlier_std_k
    min_n = settings.outlier_min_samples
    for f in doc.all_fields():
        v = _numeric(f)
        if v is None or f.has_error:          # known-bad values are already flagged
            continue
        key = _param_key(f)
        if not key:
            continue
        hist = [row.value for row in
                db.query(models.ParameterHistory.value)
                  .filter(models.ParameterHistory.param_key == key).all()]
        if len(hist) < min_n:
            continue
        mean = sum(hist) / len(hist)
        sd = (sum((x - mean) ** 2 for x in hist) / len(hist)) ** 0.5
        if sd == 0:
            if abs(v - mean) > 1e-9:          # historically constant, now different
                f.add_flag(Flag(Severity.WARNING, Category.CROSS_REFERENCE, "CROSS_DOC_DRIFT",
                                f"{f.value} differs from this parameter's prior records ({mean})",
                                expected=str(mean), actual=str(f.value)))
            continue
        if abs((v - mean) / sd) > k:
            f.add_flag(Flag(Severity.WARNING, Category.CROSS_REFERENCE, "CROSS_DOC_DRIFT",
                            f"{f.value} is {abs((v - mean) / sd):.1f}σ from prior records "
                            f"(mean {round(mean, 2)}, n={len(hist)})",
                            expected=f"{round(mean, 2)} ± {round(sd, 2)}", actual=str(f.value)))


def record(doc: Document, db: Session, document_id: str) -> None:
    """Append this document's numeric parameter values to the history."""
    rows = []
    for f in doc.all_fields():
        v = _numeric(f)
        key = _param_key(f) if v is not None else None
        if key is not None:
            rows.append(models.ParameterHistory(param_key=key, value=v, document_id=document_id))
    if rows:
        db.add_all(rows)
        db.commit()
