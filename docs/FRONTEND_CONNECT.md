# Frontend ↔ Backend Connection Guide

Everything the UI needs to build the **review screen** against the live API. No backend code required.

## 1. Base URL
The backend runs locally and is exposed via a Cloudflare quick-tunnel:

```
API_BASE = https://<something>.trycloudflare.com/api/v1
```

> ⚠️ The `trycloudflare.com` URL **changes every time the tunnel restarts** — grab the current one from the
> tunnel window and update one constant. (Last known: `https://interfaces-offices-listings-whenever.trycloudflare.com`.)

CORS is wide-open, so the browser can call it directly. Health check:
```js
await fetch(`${API_BASE.replace('/api/v1','')}/health`).then(r => r.json())
// { status:"ok", extractor:"openai", ocr_engine:"mistral", db:"sqlite" }
```

## 2. The review flow (what the UI does)
1. **(once, backend job)** A document is processed → fields land in the DB. The UI usually just *reads* results.
2. `GET /documents` → pick a document (shows error/warning/needs-review counts).
3. `GET /documents/{id}/queue` → the **review queue**, already ordered: errors → warnings → low-confidence.
4. For each item: show the value, confidence, and flags; **click → open the page image with the bbox drawn**.
5. `PATCH /fields/{id}` → human confirms or corrects (audit-logged on the backend).
6. `GET /documents/{id}/export.xlsx` → download the Excel.

## 3. Endpoints

### Documents
```
POST  /documents/process?max_pages=12      # run the pipeline (backend job). omit max_pages for all pages.
GET   /documents                           # list + counts
GET   /documents/{id}                      # one document summary
```
`POST /documents/process` response:
```json
{ "document_id":"d_2a83...", "status":"processed",
  "n_fields":326, "n_errors":18, "n_warnings":119,
  "n_auto_accepted":186, "n_needs_review":140 }
```
`GET /documents` item (`DocumentSummary`):
```json
{ "id":"d_2a83...", "doc_no":"scanned_batch_documentation.pdf", "title":"...",
  "status":"processed", "page_count":46,
  "n_fields":326, "n_errors":18, "n_warnings":119, "n_needs_review":140 }
```

### Fields & the review queue  ← the main screen
```
GET   /documents/{id}/queue                # needs_review, errors-first (USE THIS for the review list)
GET   /documents/{id}/fields?status=needs_review&severity=error&category=calculation&page_no=12&role=net_mass
GET   /fields/{id}
PATCH /fields/{id}                         # confirm / correct
```
A **field** object (this is the core shape):
```json
{
  "id": "f_1a2b...",
  "document_id": "d_2a83...",
  "chapter": "",
  "block_key": "b_...",
  "page_no": 12,
  "role": "net_mass",
  "label_raw": "m Netto",
  "value": "300",                       // normalized, display this
  "value_raw": "300",                   // exactly what was read
  "unit": "kg",
  "nks": null,
  "bbox": [0.61, 0.50, 0.78, 0.53],     // normalized [x0,y0,x1,y1], 0..1 of the page (top-left origin). may be null.
  "confidence": 0.4,                    // 0..1
  "status": "needs_review",
  "reads": [ { "model":"gpt-5.5", "value_raw":"300", "confidence":0.94 } ],
  "flags": [
    { "id":"fl_...", "severity":"error", "category":"calculation", "code":"CALC_NET_MASS",
      "message":"net_mass should equal gross - tare = 400 - 200 = 200",
      "expected":"200", "actual":"300" }
  ]
}
```
**Correcting/confirming** — `PATCH /fields/{id}`:
```js
await fetch(`${API_BASE}/fields/${id}`, {
  method:"PATCH", headers:{ "Content-Type":"application/json" },
  body: JSON.stringify({ action:"correct", value:"200", reason:"misread digit", actor:"anna" })
  // action:"confirm" to accept as-is (no value needed)
}).then(r => r.json())   // returns the updated field
```

### Flags (dashboard counts)
```
GET /documents/{id}/flags?severity=error&category=four_eyes
```

### Page images (for the bbox overlay)
```
GET /documents/{document_id}/pages/{page_no}/image     # PNG of the rendered page  ← use this
GET /pages/{page_id}/image                             # same, by page id
```

### Stats (distribution plots, later)
```
GET /stats/roles/{role}/distribution                   # histogram + mean/std for a parameter
```

### Export
```
GET /documents/{id}/export.xlsx                        # Excel (tidy + pivot sheets)
```

## 4. Drawing the bbox (the click-to-locate feature)
`bbox` is **normalized 0..1**. Load the page image, then scale the box to the rendered image size:

```jsx
function FieldOverlay({ documentId, field }) {
  const src = `${API_BASE}/documents/${documentId}/pages/${field.page_no}/image`;
  return (
    <div style={{ position: "relative", display: "inline-block" }}>
      <img src={src} alt={`page ${field.page_no}`} style={{ maxWidth: "100%" }} />
      {field.bbox && (
        <div style={{
          position: "absolute",
          left:   `${field.bbox[0] * 100}%`,
          top:    `${field.bbox[1] * 100}%`,
          width:  `${(field.bbox[2] - field.bbox[0]) * 100}%`,
          height: `${(field.bbox[3] - field.bbox[1]) * 100}%`,
          border: "2px solid red", boxSizing: "border-box", pointerEvents: "none",
        }} />
      )}
    </div>
  );
}
```
Using percentages means you don't need the image's natural pixel size — the box scales with the displayed image. (If `bbox` is `null`, just show the page; not every field localizes.)

## 5. Suggested screen
- **Left:** the review queue (`/documents/{id}/queue`). Each row = label + value + a colored chip per flag
  (`error`=red, `warning`=amber) + confidence. Group/sort by page or by `flag.category`.
- **Right:** the selected field's page image with its red bbox drawn, plus an inline edit box → `PATCH`.
- Show the auto-accepted count as "N fields auto-verified" (hidden by default; available via `?status=auto_accepted`).

## 6. Enums (stable)
- `flag.severity`: `error` · `warning`  *(no other values; a clean field has an empty `flags` array)*
- `flag.category`: `extraction · calculation · range · temporal · four_eyes · format · applicability · cross_reference · deviation · outlier · missing`
- `field.status`: `auto_accepted · needs_review · confirmed · corrected` *(also `extracted`/`validated` transiently)*

## 7. Gotchas
- **Tunnel URL changes** on restart — keep it in one config constant.
- **Page images only exist for live-processed docs** (the offline stub renders none → image endpoint 404s).
- **Processing is the slow part** (~seconds/page); reads are instant. Trigger `process` once, then the UI just GETs.
- **`value` vs `value_raw`**: show `value` (normalized); keep `value_raw` for "what was actually written".
