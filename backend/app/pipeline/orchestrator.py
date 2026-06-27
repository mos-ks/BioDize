"""Pipeline orchestrator: extract -> ocr/localize -> normalize -> validate -> uncertainty -> store.

The whole thing runs offline with EXTRACTOR=stub (no API calls). With
EXTRACTOR=openai + OCR_ENGINE=mistral it calls the cloud providers.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import models
from app.domain.severity import FieldStatus, Severity
from app.pipeline import history, store
from app.pipeline.extract.base import get_extractor
from app.pipeline.ingest import render_pdf
from app.pipeline.localize import localize, ocr_crosscheck
from app.pipeline.normalize import normalize
from app.pipeline.ocr.base import get_ocr_engine
from app.pipeline.resolve import resolve
from app.pipeline.validate.engine import validate
from app.pipeline.validate.uncertainty import score
from app.pipeline.zoom_reread import zoom_reread


@dataclass
class ProcessSummary:
    document_id: str
    n_fields: int
    n_errors: int
    n_warnings: int
    n_auto_accepted: int
    n_needs_review: int


def process(source_path: str | None, db: Session, max_pages: int | None = None,
            force_extractor: str | None = None,
            progress: "Callable[..., None] | None" = None) -> ProcessSummary:
    # force_extractor lets endpoints pin the stub (e.g. the simulated-batch button)
    # regardless of the globally configured extractor.
    extractor_name = force_extractor or settings.extractor
    t0 = time.monotonic()

    def _p(stage: str | None = None, **kw) -> None:
        # Report progress to a background-job listener (no-op for sync callers).
        if progress:
            progress(stage=stage, **kw)

    # 0. Render the PDF ONCE; share the page images with the reader and the OCR layer.
    page_images: dict[int, str] = {}
    pages = None
    if source_path and extractor_name != "stub":
        _p("Rendering PDF…")
        pages = render_pdf(source_path).pages
        if max_pages:
            pages = pages[:max_pages]          # cheap first run: limit model calls
        page_images = {p.page_no: p.image_path for p in pages if p.image_path}

    # 1. Extract (parameters discovered, not hardcoded). The reader reports
    #    per-page progress for live runs (the slowest stage).
    extractor = get_extractor(extractor_name)
    if pages:
        _p(f"Reading {len(pages)} page(s) with the model…", page_total=len(pages))
    doc = extractor.extract(source_path, pages, progress=progress)

    # 2. OCR layer -> bounding boxes (skipped for the stub, which carries its own).
    ocr_engine = get_ocr_engine(settings.ocr_engine)
    ocr_by_page = {}
    page_nos = sorted({f.page_no for f in doc.all_fields()})
    for idx, page_no in enumerate(page_nos, 1):
        img = page_images.get(page_no)
        if img is None:
            continue  # page not rendered (stub, or max_pages truncation) -> no geometry
        _p(f"Locating fields — page {idx} of {len(page_nos)}…", page_done=idx, page_total=len(page_nos))
        ocr_by_page[page_no] = ocr_engine.recognize(img, page_no)
    localize(doc, ocr_by_page)
    ocr_crosscheck(doc, ocr_by_page)   # ensemble: flag VLM/OCR numeric disagreements
    zoom_reread(doc, page_images)      # second look at low-conf / blank-required fields (crop+upscale+re-read)

    # 3. Normalize -> 3b. Domain resolution (snap Kürzel to roster, etc.)
    #    -> 4. Validate -> 5. Uncertainty/gate.
    _p("Validating…")
    normalize(doc)
    resolve(doc)
    validate(doc)
    history.check_consistency(doc, db)   # cross-document: value drift vs prior records
    score(doc)

    # 6. Persist (with page-image paths so the review UI can serve them).
    _p("Saving…")
    document_id = store.persist(doc, db, page_images)
    history.record(doc, db, document_id)  # append this record's values to the history

    # Record how long generating this batch took (shown on the landing page).
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    db.query(models.Document).filter(models.Document.id == document_id).update(
        {"processing_ms": elapsed_ms})
    db.commit()

    fields = doc.all_fields()
    n_err = sum(1 for f in fields for fl in f.flags if fl.severity is Severity.ERROR)
    n_warn = sum(1 for f in fields for fl in f.flags if fl.severity is Severity.WARNING)
    return ProcessSummary(
        document_id=document_id,
        n_fields=len(fields),
        n_errors=n_err,
        n_warnings=n_warn,
        n_auto_accepted=sum(1 for f in fields if f.status is FieldStatus.AUTO_ACCEPTED),
        n_needs_review=sum(1 for f in fields if f.status is FieldStatus.NEEDS_REVIEW),
    )
