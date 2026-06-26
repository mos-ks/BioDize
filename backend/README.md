# BioDize Backend

FastAPI service: scanned handwritten batch-record PDF → extracted, validated, structured data
+ review API + Excel export. Runs **offline on the stub** (no API keys) and switches to cloud
providers (OpenAI read + Mistral OCR 4 boxes) via `.env`. No GPU required.

See the design docs in [`../docs/`](../docs/) (architecture, validation rules, API, data model, uncertainty).

## Quick start (offline, no keys)
```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # defaults to EXTRACTOR=stub
uvicorn app.main:app --reload                          # http://localhost:8000/docs
```
Then run the pipeline on the built-in fixture and inspect results:
```bash
curl -X POST http://localhost:8000/api/v1/documents/process      # -> {document_id, n_errors, ...}
curl http://localhost:8000/api/v1/documents/<id>/queue           # review queue (errors first)
curl -OJ http://localhost:8000/api/v1/documents/<id>/export.xlsx # Excel
```
The stub catches the planted errors (calc, 4-eyes, range, date-format) so the whole flow is demoable
with zero setup.

## Going live (cloud providers)
Set in `.env`:
```
EXTRACTOR=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5            # your exact GPT-5.x vision id
OCR_ENGINE=mistral
MISTRAL_API_KEY=...
```
Then `POST /api/v1/documents` (upload PDF) and `POST /api/v1/documents/process?source_path=...`.

## On-prem swap (DGX Spark / vLLM) — no code change
Serve an open model with an OpenAI-compatible endpoint and point the config at it:
```
OPENAI_BASE_URL=http://spark:8000/v1
OPENAI_MODEL=qwen3-vl
```

## Giving the frontend access to the API
- **Fast (dev):** run locally + tunnel — `cloudflared tunnel --url http://localhost:8000` (or `ngrok http 8000`).
  CORS is open, so the browser app can call the tunnel URL directly.
- **Stable (recommended):** deploy with the included `Dockerfile` / `render.yaml` to Render/Railway/Fly
  (no GPU). Set the API keys as env vars and point `DATABASE_URL` at **Supabase Postgres** for persistence.
- **Not Appwrite** — it's a BaaS for its own primitives, not for hosting this FastAPI app.

## Tests
```bash
pytest -q
```

## Layout
```
app/
  core/config.py          settings (.env)
  db/                     SQLAlchemy engine + ORM models
  domain/                 roles, severities, statuses
  schemas/                Pydantic API DTOs
  pipeline/
    ingest, preprocess    PDF -> page images
    ocr/                  OCR engines (stub, mistral) -> bounding boxes + confidence
    extract/              Extractor interface (stub, openai) -> fields
    localize              value -> OCR polygon -> bbox
    normalize             EU number/date/time parsing, roles, Soll ranges
    validate/             rules + engine + uncertainty (confidence gate)
    store, export         persist + Excel
    orchestrator          the end-to-end pipeline
  api/routes/             documents, fields, flags, pages, stats, export, health
```
