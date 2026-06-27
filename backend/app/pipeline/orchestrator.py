"""Pipeline orchestrator: extract -> ocr/localize -> normalize -> validate -> uncertainty -> store.

The whole thing runs offline with EXTRACTOR=stub (no API calls). With
EXTRACTOR=openai + OCR_ENGINE=mistral it calls the cloud providers.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import settings
from app.domain.severity import FieldStatus, Severity
from app.pipeline import store
from app.pipeline.extract.base import get_extractor
from app.pipeline.ingest import render_pdf
from app.pipeline.localize import localize
from app.pipeline.normalize import normalize
from app.pipeline.ocr.base import get_ocr_engine
from app.pipeline.resolve import resolve
from app.pipeline.validate.engine import validate
from app.pipeline.validate.uncertainty import score


@dataclass
class ProcessSummary:
    document_id: str
    n_fields: int
    n_errors: int
    n_warnings: int
    n_auto_accepted: int
    n_needs_review: int


def process(source_path: str | None, db: Session, max_pages: int | None = None) -> ProcessSummary:
    # 0. Render the PDF ONCE; share the page images with the reader and the OCR layer.
    page_images: dict[int, str] = {}
    pages = None
    if source_path and settings.extractor != "stub":
        pages = render_pdf(source_path).pages
        if max_pages:
            pages = pages[:max_pages]          # cheap first run: limit model calls
        page_images = {p.page_no: p.image_path for p in pages if p.image_path}

    # 1. Extract (parameters discovered, not hardcoded).
    extractor = get_extractor(settings.extractor)
    doc = extractor.extract(source_path, pages)

    # 2. OCR layer -> bounding boxes (skipped for the stub, which carries its own).
    ocr_engine = get_ocr_engine(settings.ocr_engine)
    ocr_by_page = {}
    for page_no in {f.page_no for f in doc.all_fields()}:
        img = page_images.get(page_no)
        if img is None:
            continue  # page not rendered (stub, or max_pages truncation) -> no geometry
        ocr_by_page[page_no] = ocr_engine.recognize(img, page_no)
    localize(doc, ocr_by_page)

    # 3. Normalize -> 3b. Domain resolution (snap Kürzel to roster, etc.)
    #    -> 4. Validate -> 5. Uncertainty/gate.
    normalize(doc)
    resolve(doc)
    validate(doc)
    score(doc)

    # 6. Persist (with page-image paths so the review UI can serve them).
    document_id = store.persist(doc, db, page_images)

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
