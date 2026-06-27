# BioDize — Digital Workflow Transformation of Production Records

> Rentschler Biopharma Challenge — *Digitalization*. Turn scanned **handwritten** German pharma
> batch records into **structured, validated** data in a database + Excel, with a **human review**
> interface — on **controlled infrastructure**.

This repository holds **both** sides: `backend/` (extraction → validation → storage → export
pipeline + review API) and `frontend/` (the React review UI). It runs **fully offline** out of
the box and deploys on your own infrastructure — see [Quickstart](#quickstart) and
[`docs/TECH_STACK.md`](docs/TECH_STACK.md).

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

## Quickstart
Two local services. **Defaults are fully offline** (`EXTRACTOR=stub`, `OCR_ENGINE=stub`) — no
API keys, no internet — so the whole pipeline + UI run on a laptop. See
[`docs/TECH_STACK.md`](docs/TECH_STACK.md) to plug in your own VLM/OCR models on a private cluster.

**Backend**
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate   |   macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload        # → http://localhost:8000  (API docs at /docs)
```
The SQLite DB + tables are created automatically.

**Frontend**
```bash
cd frontend
npm install
npm run dev                          # → http://localhost:5173
```
Click the **gear** (top-right) → set the backend URL to `http://localhost:8000` (saved in the
browser, no rebuild).

**Try it:** in the UI, **Simulated batch** populates instant offline demo records; or
**Upload PDF → Process** for a real scan (needs model config). Then review the queue, jump to the
**exact box** on the page, **Compare** batches, **Eval AI** vs ground truth, **Export .xlsx**.

## What it does
- **Reads every field** (handwriting → value), binds each value to its parameter **by role**
  (never a hardcoded label), drops prose/legends/table-of-contents.
- **Validation engine** (two-tier `error`/`warning`): physics recomputation (mass balance,
  `V = m·ρ`), Soll-range checks, zero-padded dates, **4-eyes** (Geprüft after Bearbeitet, distinct
  signers), conditional "findet keine Anwendung" scope, cross-page references, missing data.
- **Anomaly detection** — values beyond k·σ of their role-peers (leave-one-out z-score), with the
  distribution plotted in review.
- **Confidence-gated review** — auto-accept only on a confident, rule-clean read; everything else
  is queued. *Right or it asks, never silently wrong.*
- **Exact-location boxes** — each value links to its bounding box on the scan (row + column
  estimate snapped to OCR geometry); a redundant-flag post-process keeps the queue clean.
- **Review UI** — page-grouped queue (sort by **severity** or **page**; nothing selected by default),
  full-page "all boxes" view, the model's **real per-field confidence**, one-click confirm/correct, batch
  **Compare**, **Eval AI** vs ground truth, **Excel export**, **simulated** demo batches, delete.

## Status
- [x] Full pipeline: extract → OCR/localize → normalize → resolve → validate → uncertainty → store → export
- [x] Review UI (queue, bbox overlay, confirm/correct, compare, eval, stats, export)
- [x] Anomaly detection, 4-eyes, physics calc, dates, ranges, cross-refs, applicability
- [x] Offline stub (zero-config demo) + provider-agnostic real models
- [ ] Bounding-box **column** precision in dense tables (xpos-narrowed; tuning ongoing)
- [ ] Checkbox extraction accuracy (~74% vs gold; improving)

## Documentation
| Doc | What it covers |
|---|---|
| [`docs/CHALLENGE.md`](docs/CHALLENGE.md) | The challenge brief (requirements + wishlist), preserved |
| [`docs/TECH_STACK.md`](docs/TECH_STACK.md) | Tech stack + **deploy locally / on a private cluster** with your own VLM/OCR models |
| [`docs/DOMAIN_KNOWLEDGE.md`](docs/DOMAIN_KNOWLEDGE.md) | Page-by-page domain model of the sample BPR |
| [`docs/VALIDATION_RULES.md`](docs/VALIDATION_RULES.md) | Full rule catalog, two-tier severity (`error`/`warning`) |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Pipeline, components, extractor interface, tech stack |
| [`docs/UNCERTAINTY.md`](docs/UNCERTAINTY.md) | Confidence/UQ subsystem + confidence-gated review |
| [`docs/API.md`](docs/API.md) | REST contract for the frontend |
| [`docs/FRONTEND_CONNECT.md`](docs/FRONTEND_CONNECT.md) | Frontend connection guide — base URL, endpoints, bbox overlay, sample fetch |
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
