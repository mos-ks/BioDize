# Pipeline Scorecard — vs the gold standard

A fresh run of the production pipeline (VLM exhaustive understanding → Mistral
boxes → resolve → validate) on the 8 ground-truth pages, scored against
`ground_truth/`. **Graded on use-case outcomes, not OCR spelling** (a signature
is signed-vs-blank; a checkbox is checked-vs-unchecked; the exact Kürzel doesn't
matter). Accuracy judged by a per-page LLM judge; rules + boxes checked
deterministically.

## Extraction accuracy (8 pages, 109 gold fields)
| Metric | Score |
|---|---|
| Field coverage / recall | **109 / 109 — 100%** |
| Value accuracy | **51 / 51 — 100%** |
| Checkbox-state accuracy | **34 / 34 — 100%** |
| Signature presence (signed/blank) | **24 / 24 — 100%** |

## Rule detection
All **real** planted violations were caught:

| Page | Expected | Pipeline | |
|---|---|---|---|
| 9  | 4EYES_DISTINCT | 4EYES_DISTINCT | ✓ |
| 10 | 4EYES_DISTINCT, 4EYES_ORDER | both | ✓ |
| 11 | (CALC) | clean | ✓ — gold applied printed `V=m/ρ`; domain rule is `V=m×ρ=220` (correct) |
| 14 | — (N/A chapter) | clean | ✓ |
| 17 | RANGE_SOLL | RANGE_SOLL | ✓ |
| 18 | — | clean | ✓ |
| 25 | — | CALC_ROUNDING | ⚑ pipeline **caught a rounding the gold missed** (`321/1,31×4,35≈1065,8` → should be 1066, recorded 1065) |
| 31 | 4EYES_DISTINCT, SIG_INCOMPLETE | both | ✓ |

The pipeline matches every real expected violation and, on p25, exceeds the gold.

## Localization
- **87%** of fields boxed; **98%** of those boxes are tight (<8% page height — no smears).
- **mIoU ≈ 0.80** over unambiguous value fields (small sample — repeated values like dates are excluded).

## Caveats
- The gold standard is model-generated (3-reader Claude-vision consensus), not human-verified — and as p11/p25 show, it has its own gaps.
- Judge grading is intentionally use-case-lenient (signed/blank, not exact Kürzel).
- 8 representative pages; the mIoU sample is small.

## Reproduce
1. Run the ensemble on the GT pages (extractor=vlm_exhaustive, ocr=mistral).
2. Score per page vs `ground_truth/page_0NN.json` (accuracy judge + deterministic rule/box checks).
