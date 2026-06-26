# Architecture

## Goals
1. **Perfect accuracy** — never confidently wrong (see [`UNCERTAINTY.md`](UNCERTAINTY.md)).
2. **Controlled infrastructure** — OpenAI now, on-prem later via a config change.
3. **Robust to varying layouts** — discover parameters by role; anchor on page number.

## Pipeline
```
PDF (scanned, handwritten)
  │
  1. INGEST        PyMuPDF → page images @300dpi; attach hardcoded {doc_no, page_no};
  │                detect blank/Kreuzung pages
  │
  2. PREPROCESS    deskew, denoise, contrast; (optional) block crops
  │
  3. OCR LAYER     OCR engine → words[] with polygons + per-word confidence   ← bounding boxes come from HERE
  │
  4. EXTRACT       Extractor.extract(page) → fields[]:
  │                {role, label_raw, value_raw, unit, nks?, page_no, reads[], confidence}
  │                (OpenAI vision now; provider-agnostic; structured JSON output;
  │                 parameters NOT hardcoded; prose dropped)
  │
  5. LOCALIZE      bind each field's value_raw to OCR words → bbox (the click-to-locate box)
  │
  6. NORMALIZE     EU numbers ("1,100"→1.1, "4,50"→4.50), dates DD.MM.YYYY, 24h time, units;
  │                role assignment; applicability (gate) state machine
  │
  7. VALIDATE      rule engine → flags[] (error|warning)  + UQ posterior confidence
  │
  8. STORE         SQLite: Document→Chapter→Block→Field (+ reads, flags, corrections, audit, role_stats)
  │
  9. REVIEW API    confidence-gated queue; serve page image + bbox; accept corrections (audited)
  │
 10. EXPORT        Excel: tidy sheet (1 row/param) + wide pivot (1 row/batch)
```

## Why OCR-box + VLM-read (not VLM boxes)
General VLMs (GPT included) **cannot produce reliable bounding boxes** (OCRBench v2: GPT-4o = 0 on
text-spotting; see `MODEL_RESEARCH.md`). So: the **OCR engine** provides geometry (word polygons +
confidence), the **VLM** provides the *reading* of messy handwriting. The field's box is the union of the
OCR polygons its value matched. This makes the reviewer's one-click jump accurate.

## The `Extractor` interface (provider-agnostic, ensemble-ready)
```python
class Extractor(Protocol):
    name: str
    def extract(self, page: PageImage, ocr: OcrResult) -> list[FieldRead]: ...

# FieldRead = one model's reading of one field
@dataclass
class FieldRead:
    role: str | None
    label_raw: str
    value_raw: str
    unit: str | None
    nks: int | None
    bbox: BBox | None        # filled in the LOCALIZE step from OCR polygons
    confidence: float        # model/engine self-confidence
    model: str               # which provider produced this read
```
- **Now:** `OpenAIExtractor` (configurable `base_url`, `model`, `api_key`).
- **Local swap:** point `base_url` at a vLLM OpenAI-compatible server (e.g. `dots.ocr`) → no rewrite.
- **Ensemble (later):** run several `Extractor`s; a `ConsensusExtractor` merges `reads[]` per field and
  sets confidence from agreement. The schema already stores `reads[]`, so this is additive.
- **`StubExtractor`:** deterministic fake data from the sample, so the **frontend integrates and the whole
  pipeline runs offline / without spending API calls.**

## Components (backend modules)
| Module | Responsibility |
|---|---|
| `pipeline/ingest` | PDF → page images, doc/page metadata, blank/Kreuzung detection |
| `pipeline/preprocess` | deskew/denoise/crop |
| `pipeline/ocr` | OCR engine adapter → words + polygons + confidence |
| `pipeline/extract` | `Extractor` interface + OpenAI / Stub (/ later local, consensus) impls |
| `pipeline/localize` | value → OCR polygon binding → bbox |
| `pipeline/normalize` | EU number/date/time/unit parsing, role assignment, gate state machine |
| `pipeline/validate` | rule engine (`rules.py`) + UQ scorer → flags + confidence |
| `pipeline/store` | persist to DB; update `role_stats` priors |
| `pipeline/export` | Excel (tidy + pivot) |
| `api/*` | FastAPI routes (ingest, extract, validate, review, export, stats, health) |

## Tech stack
Python 3.11 · **FastAPI** · **SQLAlchemy** + **SQLite** (`DATABASE_URL`-swappable) · Pydantic v2 ·
`openai` SDK · PyMuPDF · an OCR engine (Azure Read for dev / `dots.ocr` for on-prem) · openpyxl · pandas ·
NumPy/SciPy (stats). Docker + docker-compose. Config via `.env` / pydantic-settings.

## Data flow for the review UI (frontend contract)
1. `POST /documents` → upload PDF, returns `document_id`.
2. `POST /documents/{id}/extract` then `POST /documents/{id}/validate` (or one `process` call).
3. `GET /documents/{id}/fields?status=needs_review` → values + confidence + flags + `{page_no, bbox}`.
4. Frontend renders the page image (`GET /pages/{id}/image`) and draws the bbox; one click per flag.
5. `PATCH /fields/{id}` → human confirms/corrects (audit-logged).
6. `GET /documents/{id}/export.xlsx`.

See [`API.md`](API.md) and [`DATA_MODEL.md`](DATA_MODEL.md).
