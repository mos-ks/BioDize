# Uncertainty Quantification & Confidence-Gated Review

This is the mechanism behind **"perfect accuracy"**: the system is *right or it asks*. It never silently
commits a value it isn't sure about. UQ decides **what a human must look at**; severity decides **the order**.

## Definition of the goal
> Every value in the database is either (a) machine-certain **and** consistent with all rules, or
> (b) human-confirmed. The system is never *confidently wrong*.

Two targets, in priority order:
1. **Precision of auto-accept ≈ 100%** — zero wrong values committed without a human.
2. **Minimize human review load** — auto-accept as much as is safely possible.

(OCR accuracy % is *not* the target — it can't reach 100% on handwriting and isn't the contract.)

## Per-field posterior confidence
Each field gets one calibrated number in `[0,1]`, fused from independent signals:

| Signal | Where it comes from | Intuition |
|---|---|---|
| Token/char confidence | OCR engine per-word confidence | how legible the ink is |
| Model agreement | spread across ensemble reads (when enabled) | do independent readers agree |
| Rule-consistency | does the value satisfy its calc/range/cross-ref constraints | a value that passes its physics check is more trustworthy |
| Character ambiguity | EU traps: `1`↔`7` crossbar, `0`↔`6`, missing decimal comma | known confusable glyphs |
| **Bayesian prior** | `P(value \| historical distribution of this role)` | is the value normal for this parameter |

### Bayesian framing
For a field of role *r* with read value *x*:
```
posterior(x)  ∝  likelihood(read = x | ink, model)  ×  prior(x | history of role r)
```
- **Prior** = the distribution of role *r* across past batches (the "plot distribution" feature). Stored
  per role in `role_stats` (running mean/variance, optionally a KDE / conjugate model).
- **Likelihood** = the extraction's own confidence (OCR + model agreement + glyph ambiguity).
- A value that is **visually shaky _and_ statistically unusual** → low posterior → review.
  A clean read in the fat part of the distribution → high posterior → eligible for auto-accept.
- Cold start (no history): fall back to OCR+rule confidence only; emit `STAT_NO_HISTORY` note (no flag).

### Calibration
Raw scores are mapped to a calibrated probability (isotonic / Platt on a small golden set). The
**auto-accept threshold** is set **conservatively** to keep auto-accept precision ≈ 100%, accepting more
human review rather than risk a wrong commit. The threshold is a config value and can be tuned per role.

## The gate (commit decision)
```
auto_accept  ⇔  posterior ≥ threshold(role)
                AND  no error flags
                AND  no warning flags
otherwise    → status = needs_review   (queued, errors first, then warnings, then low-confidence)
```
- Verification policy (chosen): **confidence-gated**. A `verify_everything` mode (every field
  human-confirmed; confidence only orders the queue) is a single config switch — the schema's `status`
  field supports both.

## Field lifecycle (status)
```
extracted → validated → ┌─ auto_accepted        (high conf, no flags)
                        └─ needs_review → confirmed | corrected   (human, audit-logged)
```
Every transition is written to the audit log with actor + timestamp + before/after value.

## What the frontend shows
- A **prioritized queue** (errors → warnings → low-confidence). Most fields aren't in it.
- Per field: proposed value, **confidence**, the **flags** (severity + category + message), and a
  one-click **bbox** jump to the exact spot on the page image.
- Correcting a value re-runs dependent rules (e.g. fixing `tare_mass` re-checks `net_mass`).

## Roadmap of UQ depth (fits 72h)
1. **MVP:** OCR confidence + rule-consistency + glyph-ambiguity → threshold gate. (No history needed.)
2. **+History:** build `role_stats` from processed batches → Bayesian prior → `STAT_OUTLIER` warnings +
   distribution plots via `GET /stats/roles/{role}/distribution`.
3. **+Ensemble:** add model voters → agreement sharpens the likelihood term.
