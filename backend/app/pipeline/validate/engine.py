"""Validation engine: run the rule registries over a normalized Document."""
from __future__ import annotations

from app.pipeline.model import Document
from app.pipeline.validate import rules


def validate(doc: Document) -> Document:
    for block in doc.blocks:
        # A block declared N-A by a gate / Kreuzung is skipped for "missing"
        # checks; the inverse (filled-in-NA) is a Day-2 rule.
        applicable = block.applicability == "applicable"

        for field in block.fields:
            for rule in rules.FIELD_RULES:
                for flag in rule(field):
                    field.add_flag(flag)

        if applicable:
            for rule in rules.BLOCK_RULES:
                rule(block)  # block rules attach flags to the relevant field directly

    # Document-level checks (need the record's print date / cross-field context).
    rules.rule_dates_document(doc, rules.print_date(doc))
    rules.rule_kuerzel_document(doc)

    return doc
