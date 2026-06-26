"""Severity and category enums for validation flags.

Two severities only: a clean, confident, consistent field produces NO flag.
"""
from __future__ import annotations

from enum import Enum


class Severity(str, Enum):
    ERROR = "error"      # provably wrong; must be resolved
    WARNING = "warning"  # suspicious / uncertain / acknowledged; human should glance


class Category(str, Enum):
    EXTRACTION = "extraction"
    CALCULATION = "calculation"
    RANGE = "range"
    TEMPORAL = "temporal"
    FOUR_EYES = "four_eyes"
    FORMAT = "format"
    APPLICABILITY = "applicability"
    CROSS_REFERENCE = "cross_reference"
    DEVIATION = "deviation"
    OUTLIER = "outlier"
    MISSING = "missing"


class FieldStatus(str, Enum):
    EXTRACTED = "extracted"
    VALIDATED = "validated"
    AUTO_ACCEPTED = "auto_accepted"
    NEEDS_REVIEW = "needs_review"
    CONFIRMED = "confirmed"
    CORRECTED = "corrected"


class DocumentStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
