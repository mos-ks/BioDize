"""Validation engine: run the rule registries over a normalized Document."""
from __future__ import annotations

from app.domain.severity import Category, Severity
from app.pipeline.model import Document
from app.pipeline.validate import rules

# When several flags of the same category+severity collapse, KEEP the lower-priority
# code (0 = most preferred). Unlisted codes default to 50; ties keep original order.
_CODE_PRIORITY = {"4EYES_DISTINCT": 0, "4EYES_ORDER": 1}


def consolidate_flags(doc: Document) -> Document:
    """Post-process the flags so a reviewer sees ONE issue per real problem:

      * drop exact-duplicate codes on the same field, and
      * collapse multiple flags of the SAME (category, severity) on a field into one
        — they describe the same kind of problem (e.g. a signature that is both
        same-signer AND out-of-order is one four-eyes failure). The kept flag's
        message gains the merged reasons so nothing is lost.

    Redundant-looking flags erode trust in the validation, so this keeps the review
    queue clean. Different categories (e.g. a temporal + a cross-reference issue on
    one field) and different severities stay separate.
    """
    for f in doc.all_fields():
        # 1) drop exact-duplicate codes on the same field
        seen: set[str] = set()
        flags = []
        for fl in f.flags:
            if fl.code in seen:
                continue
            seen.add(fl.code)
            flags.append(fl)

        # 2) one keeper per (category, severity)
        groups: dict[tuple[Category, Severity], list] = {}
        for fl in flags:
            groups.setdefault((fl.category, fl.severity), []).append(fl)
        keepers: set[int] = set()
        for grp in groups.values():
            keep = min(grp, key=lambda fl: _CODE_PRIORITY.get(fl.code, 50))
            extra = "; ".join(fl.message for fl in grp if fl is not keep)
            if extra and extra not in keep.message:
                keep.message = f"{keep.message}; {extra}"
            keepers.add(id(keep))
        f.flags = [fl for fl in flags if id(fl) in keepers]
    return doc


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
    rules.rule_xref_document(doc)
    rules.rule_identifier_consistency(doc)  # Batch/Dok-Nr/Projektcode must be constant across the record
    rules.rule_stat_outlier(doc)        # anomaly detection: values beyond k std of role-peers

    consolidate_flags(doc)              # post-process: drop redundant / duplicate flags
    return doc
