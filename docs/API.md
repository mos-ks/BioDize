# API Contract (Backend ↔ Frontend)

FastAPI, JSON, REST. Base path `/api/v1`. This is the contract the frontend builds against; the
`StubExtractor` makes every endpoint return realistic data without spending API calls.

## Conventions
- IDs are strings (UUIDs). Timestamps ISO-8601 UTC. `bbox` is `[x0, y0, x1, y1]` **normalized 0–1** to the
  page (origin top-left). Severity ∈ `{error, warning}`. Currency of truth = the DB.

## Resources & endpoints

### Documents (ingest)
| Method | Path | Purpose |
|---|---|---|
| `POST` | `/documents` | Upload a PDF (multipart) or reference `data/…`. Returns `document_id`, page count. |
| `GET` | `/documents` | List documents (status, counts of errors/warnings/needs_review). |
| `GET` | `/documents/{id}` | Document detail + chapter/block tree summary. |
| `POST` | `/documents/{id}/process` | Run extract → localize → normalize → validate (async job). |
| `GET` | `/documents/{id}/status` | Job progress: `queued\|running\|done\|failed` + per-stage. |

`POST /documents/{id}/process` can also be split into `/extract` and `/validate` for debugging.

### Fields (review)
| Method | Path | Purpose |
|---|---|---|
| `GET` | `/documents/{id}/fields` | All fields. Filters: `status`, `severity`, `category`, `page_no`, `role`. |
| `GET` | `/fields/{id}` | One field with `reads[]`, flags, confidence, bbox. |
| `PATCH` | `/fields/{id}` | Human confirm/correct. Body: `{ value, action: confirm\|correct, reason? }`. Audited; re-runs dependent rules. |
| `GET` | `/documents/{id}/queue` | Review queue, ordered errors → warnings → low-confidence. |

**Field object**
```json
{
  "id": "f_123",
  "document_id": "d_1",
  "chapter": "5.3.1",
  "block_id": "b_45",
  "page_no": 11,
  "role": "net_mass",
  "label_raw": "m Netto",
  "value": 200.0,
  "value_raw": "200",
  "unit": "kg",
  "nks": 0,
  "bbox": [0.61, 0.34, 0.78, 0.37],
  "confidence": 0.91,
  "status": "needs_review",
  "reads": [ { "model": "gpt-vision", "value_raw": "200", "confidence": 0.91 } ],
  "flags": [
    { "severity": "error", "category": "calculation", "code": "CALC_NET_MASS",
      "message": "net_mass should equal gross_mass − tare_mass = 300 − 100 = 200",
      "expected": "200", "actual": "200" }
  ]
}
```

### Flags
| Method | Path | Purpose |
|---|---|---|
| `GET` | `/documents/{id}/flags` | All flags. Filters: `severity`, `category`. For the dashboard. |

### Page images & crops (for the bbox overlay)
| Method | Path | Purpose |
|---|---|---|
| `GET` | `/pages/{id}/image` | Rendered page PNG (the review canvas). |
| `GET` | `/fields/{id}/crop` | Cropped image around the field's bbox (thumbnail in the queue). |

### Statistics (for distribution plots / priors)
| Method | Path | Purpose |
|---|---|---|
| `GET` | `/stats/roles/{role}/distribution` | Histogram/KDE + mean/σ for a role across batches; marks the current value's percentile. |

### Export
| Method | Path | Purpose |
|---|---|---|
| `GET` | `/documents/{id}/export.xlsx` | Excel: **tidy** sheet (1 row/param) + **wide pivot** (1 row/batch). |
| `GET` | `/batches/{id}/export.xlsx` | Same, aggregated across a batch's documents. |

### Health
`GET /health` → `{ status, extractor, db }`.

## Status & severity enums
- `document.status`: `uploaded · processing · processed · failed`
- `field.status`: `extracted · validated · auto_accepted · needs_review · confirmed · corrected`
- `flag.severity`: `error · warning`
- `flag.category`: `extraction · calculation · range · temporal · four_eyes · format · applicability ·
  cross_reference · deviation · outlier · missing`

## Notes for the frontend
- The **queue** is the main screen: each item = a field with a flag, its confidence, a crop thumbnail,
  and a button that opens the full page image with the `bbox` rectangle drawn.
- Confirming/correcting one field may change others' flags — re-fetch the affected fields (the PATCH
  response returns the recomputed dependents).
- Auto-accepted fields are hidden by default but available via `?status=auto_accepted` for spot checks.
