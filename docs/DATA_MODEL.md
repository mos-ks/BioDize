# Data Model

SQLAlchemy ORM, SQLite by default (`DATABASE_URL`-swappable to Postgres/Supabase). The hierarchy mirrors
the document's own definitions (page 6): **Document → Chapter → Block → Field**.

## Entity overview
```
Batch 1───* Document 1───* Chapter 1───* Block 1───* Field 1───* FieldRead
                                                       │
                                                       ├──* Flag
                                                       ├──* Correction
                                                       └──(audited via AuditLog)
Role 1───* RoleStat            (historical aggregates → Bayesian priors / distributions)
```

## Tables

### batch
`id, product, campaign, batch_no, created_at`

### document
`id, batch_id→batch, doc_no (hardcoded, e.g. AB-ABC-123456), title, rev, project_code,
 source_path, page_count, declared_page_count, generated_at (print date), status, created_at`

### page
`id, document_id→document, page_no (hardcoded), image_path, is_blank, has_kreuzung, print_date_seen`

### chapter
`id, document_id→document, number_body (e.g. "5.3.1"), number_toc, title, page_from, page_to`

### block
`id, chapter_id→chapter, page_id→page, template (bilanzierung|calc|equipment|gate|signature|...),
 applicability (applicable|na_field|na_block|na_chapter|na_rest|redirect), applicability_source`

### field
Core record. One per parameter occurrence.
`id, block_id→block, page_id→page, role, label_raw, value_raw, value_norm, value_type
 (number|date|time|datetime|bool|text|checkbox), unit, nks (required decimals),
 bbox (json [x0,y0,x1,y1] normalized), confidence (posterior), source (model|ocr|human),
 status (extracted|validated|auto_accepted|needs_review|confirmed|corrected),
 is_required, created_at, updated_at`

### field_read
One model's reading of a field (ensemble-ready; usually 1 row now).
`id, field_id→field, model, value_raw, confidence, bbox_raw, created_at`

### flag
`id, field_id→field (nullable), block_id→block (nullable), severity (error|warning), category, code,
 message, expected, actual, is_resolved, created_at`

### correction
Human edits (the GxP trail of what changed).
`id, field_id→field, old_value, new_value, action (confirm|correct), reason, actor, created_at`

### audit_log
Append-only, ALCOA+.
`id, entity_type, entity_id, action, actor, before (json), after (json), created_at`

### role / role_stat
Historical aggregates for priors and distribution plots.
- `role`: `id, name, unit, value_type`
- `role_stat`: `id, role_id→role, n, mean, m2 (for running variance), min, max, histogram (json),
   updated_at` — updated on each confirmed value; powers `STAT_OUTLIER` and `/stats/roles/{role}/distribution`.

## Notes
- **bbox** is stored normalized so it survives re-rendering at any DPI.
- **field.role** is the join key for validation rules and stats — never the label.
- **applicability** on `block` lets the validation engine suppress "missing" inside N-A regions and flag
  "filled-in-NA" — both directions (see VALIDATION_RULES §F).
- The **prior** uses only `confirmed`/`auto_accepted` values (not raw extractions) so history stays clean.
- Swapping to Postgres/Supabase is just `DATABASE_URL`; JSON columns use SQLite `JSON` / Postgres `JSONB`.
