# Ground Truth — gold standard for the extraction accuracy eval

Hand-verifiable **gold labels** for a set of representative pages of the sample
batch record, used to score the pipeline. Built by a **3-reader Claude-vision
consensus** (each page read independently 3×, then adjudicated) so it does not
depend on any single model.

It is graded on **use-case outcomes, not OCR spelling**: a signature is "signed
vs blank" (the exact Kürzel `ohe`/`ohp` is irrelevant — 4-eyes only needs
same-vs-different), a checkbox is "checked vs unchecked", a value is its content.

## Files
- `page_0NN.json` — one per gold page:
  - `fields[]` — every field on the page (exhaustive, nothing dropped): `label`,
    `kind` (`value` | `checkbox` | `signature`), `value`, `checkbox_state`
    (`checked`/`unchecked`), `signature_status` (`signed`/`blank`), `is_blank`.
  - `expected_violations[]` — the GxP rules that **should** fire on this page
    (`rule`, `field`, `explanation`).
- `index.json` — per-page counts + the violation list.

## Pages chosen (cover all field types + the rules NOT adhered to)
| Page | Section | Expected violation(s) |
|---|---|---|
| 9  | Line Clearance | `4EYES_DISTINCT` (Bearbeitet & Geprüft both signed `ohe`) |
| 10 | Zyklus / Produktionsbereich | `4EYES_DISTINCT`, `4EYES_ORDER` (Geprüft 09.06 before Bearbeitet 10.06) |
| 11 | Bilanzierung | — (`V = m × ρ`: 200 × 1,10 = 220) |
| 14 | Temperierung B10-PP | — (chapter marked *findet keine Anwendung*; blank signatures are OK) |
| 17 | Durchführung | `RANGE_SOLL` (Wippgeschwindigkeit 32 > Soll max 30) |
| 18 | Geräte | — (all equipment checks marked) |
| 25 | Berechnung der Beladung | — |
| 31 | SAP Etiketten | `4EYES_DISTINCT`, `SIG_INCOMPLETE` ×2 (date written, Kürzel missing) |

8 pages · 109 fields · 7 expected violations.

## How the scorer uses it
For each pipeline approach, on these pages, measure:
- **Coverage / recall** — was every gold field caught?
- **Value accuracy** — right value (locale-aware compare; signatures graded as signed/blank).
- **Checkbox-state accuracy** — checked/unchecked correct.
- **Rule precision/recall** — did the expected violations fire, and only those?

Regenerate after adding pages by re-running the `gold-standard` workflow.
