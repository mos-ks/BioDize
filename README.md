# BioDize — Digital Workflow Transformation of Production Records

> Rentschler Biopharma Challenge — *Digitalization*. Turn scanned **handwritten** German pharma
> batch records into **structured, validated** data in a database + Excel, with a **human review**
> interface — on **controlled infrastructure**.

This repository is split: **backend** (this branch) owns the extraction → validation → storage →
export pipeline and the review API. The **frontend** (separate) builds the review UI against the
API contract in [`docs/API.md`](docs/API.md).

## The one-paragraph idea
A real Batch Production Record is ~20 forms × 100–200 handwritten pages per batch, scanned to PDF and
buried on SharePoint. We read every form, associate each handwritten **value** with its **parameter**
(by *role*, never by hardcoded label), normalize it, and run a **validation engine** that recomputes
physics, checks ranges, dates, the 4-eyes principle, conditional/N-A logic and cross-page references.
Because handwriting OCR is never perfect, the system is built so it is **never confidently wrong**:
every value is either machine-certain *and* cross-validated, or sent to a human with a one-click
**bounding-box** jump to the exact spot on the page. Output lands in a structured DB and an Excel export.

## Guiding principle — "perfect accuracy"
The system is **right or it asks**. The metric is not OCR accuracy %; it is (1) *zero wrong values
auto-accepted* and (2) *minimum human review load*. See [`docs/UNCERTAINTY.md`](docs/UNCERTAINTY.md).

## Status
- [x] Challenge + sample document analyzed page-by-page → [`docs/DOMAIN_KNOWLEDGE.md`](docs/DOMAIN_KNOWLEDGE.md)
- [x] Validation rule catalog → [`docs/VALIDATION_RULES.md`](docs/VALIDATION_RULES.md)
- [x] Model research → [`docs/MODEL_RESEARCH.md`](docs/MODEL_RESEARCH.md)
- [x] Architecture, API contract, data model, uncertainty design — docs below
- [ ] Backend code scaffold *(held until design is approved)*

## Documentation
| Doc | What it covers |
|---|---|
| [`docs/CHALLENGE.md`](docs/CHALLENGE.md) | The challenge brief (requirements + wishlist), preserved |
| [`docs/DOMAIN_KNOWLEDGE.md`](docs/DOMAIN_KNOWLEDGE.md) | Page-by-page domain model of the sample BPR |
| [`docs/VALIDATION_RULES.md`](docs/VALIDATION_RULES.md) | Full rule catalog, two-tier severity (`error`/`warning`) |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Pipeline, components, extractor interface, tech stack |
| [`docs/UNCERTAINTY.md`](docs/UNCERTAINTY.md) | Confidence/UQ subsystem + confidence-gated review |
| [`docs/API.md`](docs/API.md) | REST contract for the frontend |
| [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) | Database schema |
| [`docs/MODEL_RESEARCH.md`](docs/MODEL_RESEARCH.md) | OCR/VLM model selection (June 2026) |
| [`docs/ROADMAP_72H.md`](docs/ROADMAP_72H.md) | 72-hour plan |

## Key decisions (locked)
- **Stack:** Python + FastAPI, SQLAlchemy + **SQLite** (`DATABASE_URL`-swappable to Postgres/Supabase).
- **Extraction now:** OpenAI vision API, behind a **provider-agnostic** `Extractor` interface.
- **Extraction later:** swap to an on-prem model via an OpenAI-compatible `base_url` (vLLM) — config change, not a rewrite.
- **Bounding boxes:** from an **OCR engine's word polygons**, never from a general VLM (VLMs can't box reliably).
- **Review model:** **confidence-gated** — auto-accept only on model-consensus *and* zero rule violations; everything else → human.
- **Ensemble:** single model first, **schema is ensemble-ready** (per-field reads).

## Sample data
`data/scanned_batch_documentation.pdf` — one real (anonymized as "cake baking") 45-page batch record,
generated 09.06.2026, executed 10.06.2026. Contains deliberately planted errors used as test cases
(listed in [`docs/DOMAIN_KNOWLEDGE.md`](docs/DOMAIN_KNOWLEDGE.md)).
