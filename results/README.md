# Pipeline Results

Output of a **live end-to-end run** of the backend on the sample batch record
`data/scanned_batch_documentation.pdf` (all 45 pages), with the full validation
catalog including the Day-2 rules (multi-input formula calc + date-window checks).

- **Reader:** `gpt-5.5` (OpenAI) — handwriting → values
- **OCR (boxes + per-word confidence):** `mistral-ocr-4-0`
- **Pipeline:** ingest → OCR/localize → extract → normalize → validate → uncertainty → store → export

## Files
| File | What it is |
|---|---|
| `batch_export.xlsx` | The Excel deliverable — `tidy` sheet (1 row/parameter) + `pivot` sheet (1 row/batch) |
| `extracted_fields.json` | All extracted fields: role, value, unit, **bbox**, confidence, status, flags |
| `summary.json` | Counts + the full error list (page / code / message) |

## Headline numbers
- **330 fields** extracted across all pages
- **178 auto-accepted** (high confidence + zero rule violations)
- **152 to review**, ordered errors-first
- **22 errors / 130 warnings** — all 22 errors genuine (no false positives)

## Errors caught (validation on real data)
| Code | Count | Examples |
|---|---|---|
| `4EYES_DISTINCT` | 15 | same person signed Bearbeitet and Geprüft |
| `4EYES_ORDER` | 1 | **p10** Geprüft dated before Bearbeitet |
| `RANGE_SOLL` | 4 | **p17** Wippgeschw. `32` (>20–30); **p39** Dauer Temperierung `2h` (vs 72–75h) |
| `CALC_NET_MASS` | 1 | **p12** net `300` ≠ gross−tare `200` |
| `CALC_FORMULA` | 1 | **p40** `V Netto nPZ` inconsistent with net mass × ρ |

## Day-2 warnings (new rules)
| Code | Count | What it caught |
|---|---|---|
| `DATE_BEFORE_PRINT` | 5 | year misreads before the record date — `2016` (p29), `2025` (p24) |
| `DATE_FAR_FUTURE` | 2 | `2028` (p17) — far past the batch window |
| `CALC_ROUNDING` | 1 | **p25** product-mass off-by-one rounding |

## How the new rules work
- **Formula calc** — the reader returns the printed formula with the handwritten numbers substituted
  (`calc_expr`); the engine deterministically re-evaluates and compares. For a `V Netto` written as
  `m / ρ`, it verifies the **domain physics `m × ρ`** (the printed division is misleading), so correct
  volumes pass and only genuine inconsistencies (p40) flag.
- **Date window** — batch-execution dates (signatures, hold times) outside `[print_date−7d, +180d]` flag.

## Honest note on extraction variance
LLM handwriting reads vary run-to-run, which is exactly why **human review against the original-image
bbox** is core to the design. Example: this run the reader misread **p36 `Load Volumen 2021,78` as
`293,78`** — coincidentally the *correct* formula result — so it wasn't flagged; a prior run read the
`2021,78` correctly and the formula rule flagged it (`CALC_FORMULA`). The system is *right or it asks*:
low-confidence reads and rule violations route to a human with the box drawn on the page.

## Still not caught (further Day-2)
- **Cross-reference (Übertrag)** — matching a carried value to its source chapter (needs block segmentation).
- **Known-Kürzel** — validating initials against the p4 personnel registry (catches `ohe→ohr` misreads).

Regenerate anytime: `POST /api/v1/documents/process` then `GET /documents/{id}/export.xlsx`.
