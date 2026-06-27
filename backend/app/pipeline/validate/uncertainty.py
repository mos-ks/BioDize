"""Uncertainty quantification + the confidence-gated commit decision.

Fuses signals into a per-field posterior confidence, then sets the field status:
auto-accept only when confident AND flag-free; otherwise route to human review.
See docs/UNCERTAINTY.md. Bayesian prior over role history is a Day-2/3 add
(STAT_OUTLIER) — the MVP uses read confidence + rule-consistency.
"""
from __future__ import annotations

import re

from app.core.config import settings
from app.domain.severity import Category, FieldStatus, Severity
from app.pipeline.model import Document, Field, Flag

# Roster / legend cells (the "Beteiligte Personen" table: Name + Kürzel columns)
# are REFERENCE data — the source of truth for who's who, not values a reviewer
# verifies one-by-one. They still feed the known-Kürzel registry; we just keep
# them out of the review queue. Matched on the printed column label.
_REFERENCE_LABELS = {"kürzel", "kuerzel", "name mitarbeiter", "name", "mitarbeiter"}


def is_reference_field(field: Field) -> bool:
    label = re.sub(r"[^0-9a-zäöüß ]+", " ", (field.label_raw or "").lower()).strip()
    return label in _REFERENCE_LABELS


def _field_confidence(field: Field) -> float:
    # Likelihood term: best read confidence (ensemble agreement when >1 read).
    reads = [r.confidence for r in field.reads]
    base = max(reads) if reads else 0.5
    if len(reads) > 1:
        spread = max(reads) - min(reads)
        base *= (1.0 - min(spread, 0.5))      # disagreement lowers confidence

    # The OCR engine's per-word confidence is a real legibility signal — prefer
    # it over the reader's flat self-report when the value was localized.
    if field.ocr_confidence is not None:
        base = field.ocr_confidence

    # Rule-consistency term: a value that violates its own rules is less trustworthy.
    if field.has_error:
        base = min(base, 0.40)
    elif field.has_warning:
        base = min(base, 0.70)

    return round(max(0.0, min(base, 1.0)), 3)


def score(doc: Document) -> Document:
    threshold = settings.auto_accept_threshold
    warn_threshold = settings.low_conf_warn_threshold
    verify_all = settings.verification_policy == "verify_everything"

    for field in doc.all_fields():
        field.confidence = _field_confidence(field)

        # Roster/legend cells are reference data, not review targets: keep them
        # out of the queue (they still populate the known-Kürzel registry).
        if is_reference_field(field) and not field.flags:
            field.status = FieldStatus.AUTO_ACCEPTED
            continue

        # Focus review on the HANDWRITTEN (blue) entries: printed/machine form text
        # (black) is highly reliable, so a clean printed field auto-accepts and stays
        # out of the queue regardless of OCR confidence.
        if field.is_handwritten is False and not field.flags:
            field.status = FieldStatus.AUTO_ACCEPTED
            continue

        # Only a GENUINELY illegible read (below the warn floor) gets a low-conf
        # warning. The [warn, accept) band still routes to review but without a
        # warning on every handwritten value. Checkboxes (Ja/Nein) are high-info
        # even at modest OCR confidence, so they never get the low-conf warning.
        if not field.flags and field.value_type != "bool" and field.confidence < warn_threshold:
            field.add_flag(Flag(Severity.WARNING, Category.EXTRACTION, "EXTRACT_LOW_CONF",
                                f"Low extraction confidence ({field.confidence}); verify the value"))

        clean = not field.flags and field.confidence >= threshold
        if clean and not verify_all:
            field.status = FieldStatus.AUTO_ACCEPTED
        else:
            field.status = FieldStatus.NEEDS_REVIEW
    return doc
