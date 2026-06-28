# BioDize — Digitize & validate handwritten pharma batch records

> Rentschler Biopharma **"Digitalization"** Challenge. Turn scanned **handwritten German** GMP
> batch records into **structured, validated** data — in a database + Excel, with a human review
> UI that is **right or it asks, never silently wrong**.

---

## ▶️ Test it — for the jury (no install, no login)

**1. Open → [https://biodize.tech](https://biodize.tech)**

**2. Upload a PDF.** Click the **upload** icon (top-right) and pick a scanned batch-record PDF.
   *No PDF handy?* Use the bundled sample [`data/scanned_batch_documentation.pdf`](data/scanned_batch_documentation.pdf), or click the **flask** icon ("Simulated batch") for an **instant** demo batch — no upload, no wait.

**3. Click _Process_.** It reads **every page** with live progress. A full 46-page batch takes a few
   minutes — set **max pages** (e.g. `8`) to cap it for a quick look, or just use the Simulated batch.

**4. Review the results.** You land on the batch with **errors / warnings / to‑review** counts:
   - Open any flag → it **jumps to the exact pin** on the scanned page (what the AI read vs. why it's flagged).
   - **Confirm** or **Correct** each one.
   - **Download** → the **Excel** in the host's Solution format.

That's the whole flow: **open the link → upload → review.** The green dot (top‑right) shows the
backend is connected; click it to run a health check.

🎥 **Demo video:** [`BioDize.mp4`](BioDize.mp4)

---

## What it does
- **Reads every field** (handwriting → value) and binds each value to its parameter **by role**
  (never a hardcoded label); drops prose, legends and the table of contents.
- **Reads the cover identity** (Dok‑Nr, Batch No, product) separately so the batch is correctly named.
- **Validation engine** (two‑tier `error`/`warning`): physics recomputation (mass balance, `V = m·ρ`,
  duration = end − start), Soll‑range checks, **kaufmännische Rundung** and **Nachkommastellen**
  (`20,2` flagged when the form wants `20,20`), zero‑padded dates, **4‑eyes** (Geprüft after
  Bearbeitet, distinct signers), identifier consistency, conditional "findet keine Anwendung" scope,
  cross‑page references, missing signatures / checkmarks / values.
- **Anomaly detection** — values beyond k·σ of their role‑peers, with the distribution plotted.
- **Verified (positive) marker** — a clean handwritten number confirmed by a calculation or a second
  identical value is marked blue *Verified* (host taxonomy: "confirmed by second value").
- **Confidence‑gated review** — auto‑accept only on a confident, rule‑clean read; everything else is
  queued with a **location pin** at its spot on the scan. Reviewers can also **click any spot to add a
  human flag** (title + tag).

On the bundled sample we measure **~100% gold precision** and **~92% recall against the host's
Solution Excel** (`backend/scripts/solution_recall.py`).

## How it works
```
PDF → render pages → VLM read (values, checkboxes, signatures) → OCR localize (bounding boxes)
    → normalize → resolve roles → validate (rules) → uncertainty gate → store → Excel/CSV export
```
Every model is a **remote API** (no GPU); the extractor is **provider‑agnostic** — point
`OPENAI_BASE_URL` at an on‑prem vLLM server to keep GxP data on controlled infrastructure, no rewrite.

---

## Run it locally (developers)
Two services. Defaults run **fully offline** (`EXTRACTOR=stub`) — no keys, no internet.

**Backend**
```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate   # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload                       # → http://localhost:8000  (docs at /docs)
```

**Frontend**
```bash
cd frontend
npm install
VITE_API_BASE=http://localhost:8000 npm run dev     # → http://localhost:5173
```
For real (non‑stub) extraction, set `EXTRACTOR=openai`, `OCR_ENGINE=mistral` and the API keys in
`backend/.env`. Tests: `cd backend && pytest`.

**Deploy** (cloud, laptop‑free): see [`DEPLOY.md`](DEPLOY.md). The static frontend bakes its backend
URL from the `VITE_API_BASE` repo variable, so visitors auto‑connect with nothing to configure.

---

## Documentation
| Doc | What it covers |
|---|---|
| [`DEPLOY.md`](DEPLOY.md) | Laptop‑free deploy (GitHub Pages + Render), the jury upload flow |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Pipeline, components, extractor interface |
| [`docs/VALIDATION_RULES.md`](docs/VALIDATION_RULES.md) | Full rule catalog, two‑tier severity |
| [`docs/UNCERTAINTY.md`](docs/UNCERTAINTY.md) | Confidence subsystem + confidence‑gated review |
| [`docs/DOMAIN_KNOWLEDGE.md`](docs/DOMAIN_KNOWLEDGE.md) | Page‑by‑page domain model of the sample BPR |
| [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) | Database schema |
| [`docs/API.md`](docs/API.md) | REST contract for the frontend |
| [`docs/TECH_STACK.md`](docs/TECH_STACK.md) | Tech stack + on‑prem model swap |
| [`docs/MODEL_RESEARCH.md`](docs/MODEL_RESEARCH.md) | OCR/VLM model selection |

## Sample data
[`data/scanned_batch_documentation.pdf`](data/scanned_batch_documentation.pdf) — one anonymized
46‑page batch record (generated 09.06.2026, executed 10.06.2026) with deliberately planted errors
used as test cases (catalogued in [`docs/DOMAIN_KNOWLEDGE.md`](docs/DOMAIN_KNOWLEDGE.md)).
