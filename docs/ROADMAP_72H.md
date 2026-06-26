# 72-Hour Roadmap

Backend-focused. Frontend runs in parallel against [`API.md`](API.md) using the `StubExtractor`.

## Day 1 — End-to-end skeleton (make the whole pipe move)
- [ ] Repo scaffold: FastAPI app, config, SQLite, models from [`DATA_MODEL.md`](DATA_MODEL.md).
- [ ] `INGEST`: PDF → page images (PyMuPDF), hardcoded doc/page metadata, blank/Kreuzung detection.
- [ ] `Extractor` interface + **`StubExtractor`** (real-shaped fake data from the sample) → frontend unblocked.
- [ ] `OpenAIExtractor` (configurable `base_url`/`model`) → structured JSON fields.
- [ ] `NORMALIZE`: EU number/date/time/unit parsing + role assignment.
- [ ] `STORE` + `GET /documents/{id}/fields` + `GET /pages/{id}/image`.
- [ ] Excel export (tidy + pivot).
- **Milestone:** sample PDF → fields in DB → Excel, via API.

## Day 2 — Validation engine + review (the differentiator)
- [ ] OCR layer + `LOCALIZE` → real **bboxes** for the click-to-locate review.
- [ ] Rule engine (`rules.py`) — full catalog from [`VALIDATION_RULES.md`](VALIDATION_RULES.md):
      format, four_eyes, calculation, range, temporal, applicability (gate state machine), cross_reference.
- [ ] Flags (error/warning) + categories on every field.
- [ ] UQ scorer (MVP): OCR conf + rule-consistency + glyph ambiguity → posterior → **confidence-gate**.
- [ ] Review endpoints: queue, `PATCH /fields/{id}` (confirm/correct) + **audit log**.
- **Milestone:** all 8 planted errors in the sample are caught with correct severities; reviewer can
      jump to each box and correct it.

## Day 3 — Stats, polish, demo
- [ ] `role_stats` history → Bayesian prior → `STAT_OUTLIER` warnings + `/stats/roles/{role}/distribution`.
- [ ] Out-of-spec ↔ deviation coupling (p17 ↔ p44).
- [ ] Golden-set check: field-level exact-match on numeric/date fields (de-risk handwriting/German).
- [ ] Dockerize; document the **on-prem swap** (`base_url` → vLLM `dots.ocr`) for the judges.
- [ ] Demo script + README polish.
- **Milestone:** clean demo — upload → mostly-quiet review screen with a short prioritized flag list →
      one-click corrections → Excel + DB, plus a credible local-deployment story.

## Definition of done (per the brief)
- Reads all information; associates value↔parameter by **role**; drops prose. ✓
- Parameters **not** hardcoded; doc/page **are**. ✓
- Writes to **Excel** + structured **DB**. ✓
- Wishlist: unexpected-value highlighting (range, impossible dates, 3σ, wrong calc), easy review with
  correction, missing-data highlighting, no blank template needed. ✓
- Runs locally / controlled infra; OpenAI→on-prem is a config change. ✓

## Risks & mitigations
| Risk | Mitigation |
|---|---|
| Handwriting mis-reads | confidence-gate + rule cross-checks + human review; golden-set measurement |
| VLM can't box | OCR-engine polygons for geometry (decided) |
| German/Kurrent weakness | modern print-handwriting is fine; flag low-confidence; Transkribus noted as fallback |
| Layout variation | role-based binding + page anchoring; template detection, not fixed coordinates |
| API cost/latency | `StubExtractor` for dev; batch pages; cache reads |
