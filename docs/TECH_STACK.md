# Tech Stack & Deployment

BioDize digitizes scanned **handwritten** German pharma batch records into structured,
validated data + Excel, with a human-review UI. It is built to run **entirely on your own
infrastructure** — a laptop for the demo, or a private/on-prem cluster for production. No
data has to leave your control.

---

## 1. What runs where

```
            ┌─────────────────────────────────────────────────────────────┐
  scanned   │  INGEST            render PDF → page images (local)          │
   PDF  ───►│  READ (VLM)        transcribe every field + position estimate│
            │  OCR               word/region boxes + per-word confidence    │
            │  LOCALIZE          bind each value to its exact box on the page│
            │  NORMALIZE/RESOLVE German numbers/dates, roles, Kürzel registry│
            │  VALIDATE          physics, ranges, dates, 4-eyes, anomalies   │
            │  UNCERTAINTY       confidence-gate → auto-accept or ask        │
            │  STORE / EXPORT    database  +  Excel                          │
            └─────────────────────────────────────────────────────────────┘
                         ▲                                  │
                  React review UI  ◄──────  REST API  ◄─────┘
```

Everything above runs as **two local services** (a backend API and a frontend UI). The only
calls that ever leave the box are to **whatever model endpoints you configure** — and those
can be pointed at services inside your own network (see §4), so nothing is sent to a public
provider unless you choose to.

---

## 2. Stack

| Layer | Technology | Why |
|---|---|---|
| Backend API | **Python 3 · FastAPI · Uvicorn** | typed, fast, OpenAPI out of the box |
| Pipeline | plain Python dataclasses (pure, unit-tested) | provider-agnostic, portable |
| PDF render | **PyMuPDF** (pip wheel, no system binary) | page images for the readers + the UI |
| Persistence | **SQLAlchemy 2** + **SQLite** (default) | one-file DB; swap to Postgres via one env var |
| Excel | **openpyxl** | the required structured `.xlsx` output |
| Frontend | **React + TypeScript + Vite + Tailwind** | static SPA, retargetable at runtime |

No proprietary runtime, no managed service is required. SQLite → Postgres is a single
`DATABASE_URL` change.

---

## 3. The two model *roles* (bring your own models)

The system never hardcodes a specific model. It needs **two kinds of model**, behind clean
interfaces, plus an offline stub:

1. **Page-understanding model — a Vision-Language Model (VLM).**
   Reads the handwriting and returns, per field: the value, checkbox/selection state,
   signatures, and a coarse position estimate. It is reached over an **OpenAI-compatible
   chat/vision API**, so *any* model served that way works — including a model you host
   yourself (e.g. with vLLM) on a private GPU cluster. Selected via `OPENAI_BASE_URL` +
   `OPENAI_MODEL`.

2. **OCR engine — for geometry.**
   Provides **word/region bounding boxes and per-word confidence** (the spatial signal a
   general VLM cannot produce reliably). This is what takes the reviewer to the *exact spot*
   on the page. It sits behind an adapter, so any OCR that returns boxes can be plugged in.
   Selected via `OCR_ENGINE`.

3. **Offline stub (default).**
   Deterministic fixtures that exercise the *entire* pipeline and UI with **no API keys and
   no internet** — used for the demo, for CI, and as a zero-cost way to evaluate the system.

> The `Extractor` and `OcrEngine` interfaces are the only integration points. Swapping a
> cloud model for an in-cluster one is a **config change, not a code change**.

---

## 4. Deploy it locally (clear, minimal steps)

**Prerequisites:** Python 3.11+, Node 18+. Nothing else for the offline demo.

### A. Backend
```bash
cd backend
python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload        # → http://localhost:8000  (API docs at /docs)
```
The database and tables are created automatically. With the **defaults** (`EXTRACTOR=stub`,
`OCR_ENGINE=stub`) it runs fully offline — no keys.

### B. Frontend
```bash
cd frontend
npm install
npm run dev                          # → http://localhost:5173
```
Click the **gear** (top-right) and point it at `http://localhost:8000` (saved in the
browser; no rebuild). Build a static bundle with `npm run build` (output in `dist/`).

### C. Use it
- **Simulated batch** → instant, offline demo records.
- **Upload PDF → Process** → a real scan (requires real model config, step D).
- Review the queue, jump to the **exact box**, **Compare** batches, **Eval AI** vs ground
  truth, **Export .xlsx**.

### D. Wire up your own models (production / private cluster)
```bash
cp backend/.env.example backend/.env     # then edit:
EXTRACTOR=openai                          # use the VLM role
OPENAI_BASE_URL=http://<your-vlm-host>/v1 # your in-cluster, OpenAI-compatible endpoint
OPENAI_MODEL=<your-model-id>
OCR_ENGINE=<your-ocr-adapter>             # the engine that returns boxes
DATABASE_URL=postgresql+psycopg://...     # optional: swap SQLite → Postgres
```
Point `OPENAI_BASE_URL` at a model **inside your network** and **no document data leaves
your infrastructure**. Restart the backend to apply.

---

## 5. Data control / compliance posture

- **Self-hosted by default.** Backend, DB, page images and Excel all live on your machine /
  cluster (`STORAGE_DIR`, `DATABASE_URL`).
- **No mandatory third party.** External calls happen only to the model endpoints *you*
  configure; set them to internal services for a fully air-gapped-friendly deployment.
- **Right or it asks.** Uncertain reads are never silently accepted — they are queued for a
  human with a one-click jump to the exact location on the scan.
