# Pipeline Results

Output of a **live end-to-end run** of the backend on the sample batch record
`data/scanned_batch_documentation.pdf` (all 45 pages).

- **Reader:** `gpt-5.5` (OpenAI) — handwriting → values
- **OCR (boxes + per-word confidence):** `mistral-ocr-4-0`
- **Pipeline:** ingest → OCR/localize → extract → normalize → validate → uncertainty → store → export

## Files
| File | What it is |
|---|---|
| `batch_export.xlsx` | The Excel deliverable — `tidy` sheet (1 row/parameter) + `pivot` sheet (1 row/batch) |
| `extracted_fields.json` | All 326 extracted fields: role, value, unit, **bbox**, confidence, status, flags |
| `summary.json` | Counts + the full error list (page / code / message) |

## Headline numbers
- **326 fields** extracted across all pages
- **186 auto-accepted** (high confidence + zero rule violations)
- **140 to review**, ordered errors-first
- **21 errors / 119 warnings**

## Errors caught (the validation working on real data)
- `RANGE_SOLL` — **p17** Wippgeschwindigkeit `32` (>20–30); **p39** Dauer Temperierung `2h` (vs 72–75h)
- `CALC_NET_MASS` — **p12** net `300` ≠ gross−tare `200`
- `4EYES_ORDER` — **p10** Geprüft dated before Bearbeitet
- `4EYES_DISTINCT` ×13 — same person signed both Bearbeitet and Geprüft

> **Honesty note:** 3 of the 21 errors are `FMT_DATE_PADDING` on **p30** — false positives where a
> materials-table "geprüft" column made a `Ja` value look like a signature. Fixed in a later commit
> (the rule now only flags values that actually contain digits), so the *current* code reports **18
> genuine errors**. This snapshot is kept as the raw run output.

## Known not-yet-caught (Day-2 rules)
- **p36 `Load Volumen 2021,78`** — a unit-error value; needs the multi-input formula-calc rule.
- **p38 `2016`** — a `2026→2016` handwriting misread; needs date-before-print + cross-reference (Übertrag) checks.

Regenerate anytime: `POST /api/v1/documents/process` then `GET /documents/{id}/export.xlsx`.
