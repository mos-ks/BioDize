# Validation Rules

The validation engine consumes normalized fields (with roles, units, NKS, confidence, applicability)
and emits **flags**. There are exactly **two severities**:

- **`error`** — provably wrong; must be resolved.
- **`warning`** — suspicious / uncertain / acknowledged; a human should glance.

A clean, confident, consistent field produces **no flag** (it passes silently). There is no "info" tier.

Each flag: `{ severity, category, code, field_id|block_id, message, expected, actual }`.
**Categories:** `extraction · calculation · range · temporal · four_eyes · format · applicability ·
cross_reference · deviation · outlier · missing`.

Rules bind to **roles**, not labels (so `m_Tara`/`Tara`/`Leergewicht` all match `tare_mass`). Every rule
only fires inside an **applicable** region (see `applicability`).

---

## A. Format  *(category: format)*
| Code | Rule | Severity | Example |
|---|---|---|---|
| `FMT_DATE_PADDING` | Dates are zero-padded `DD.MM.YYYY` | error | `10.6.2026` → error; `10.06.2026` ok |
| `FMT_TIME_RANGE` | Times within `00:00`–`23:59` | error | `25:14` → error |
| `FMT_NKS` | Value's decimal places == the form's stated `(N NKS)` | warning | `0,75` where `(3 NKS)` expected → warning |
| `FMT_DECIMAL_COMMA` | Decimal comma not dropped where one is expected | error | `450` where `4,50` expected → error |
| `FMT_NUMBER_UNCLEAR` | Token is ambiguous/illegible (low OCR confidence) | warning | feeds UNCERTAINTY |

## B. Four-eyes (👁)  *(category: four_eyes)*
| Code | Rule | Severity |
|---|---|---|
| `4EYES_ORDER` | `Geprüft` date ≥ `Bearbeitet` date (review only after processing) | error |
| `4EYES_DISTINCT` | `Bearbeitet` Kürzel ≠ `Geprüft` Kürzel (two people) | error |
| `4EYES_KNOWN_KUERZEL` | Each Kürzel exists in *Beteiligte Personen* (p4) | warning |
| `4EYES_PROCESSED_PRESENT` | `Bearbeitet` is filled where required (someone processed it) | error |

## C. Calculations  *(category: calculation; physics-based; `c` is a given input)*
| Code | Rule | Severity |
|---|---|---|
| `CALC_NET_MASS` | `net_mass == gross_mass − tare_mass` (± tol) | error |
| `CALC_VOLUME` | `volume == net_mass × ρ` with the **given ρ** (± tol) | error |
| `CALC_FORMULA` | Any printed formula recomputed from its inputs, rounded to its `NKS` (± tol) | error |
| `CALC_DURATION` | A duration computed from two times matches the written duration (in **hours**) | error |
| `CALC_ROUNDING` | Result differs only within rounding tolerance | warning |

Tolerance is per-role and accounts for the stated `NKS`. A hard mismatch (e.g. p36 `2021,78`) is `error`;
a last-digit rounding difference is `warning`.

## D. Ranges  *(category: range)*
| Code | Rule | Severity |
|---|---|---|
| `RANGE_SOLL` | Value within the form's `Soll: min – max` (or `≤ / ≥`) | see deviation rule |
| `RANGE_SETPOINT` | Single `Soll: X` value matched (e.g. `Zyklus Soll 1`) | error if mismatch |

**Out-of-spec ↔ deviation coupling** *(category: deviation)* — the key call:
- OOS value **with** a documented `Abweichung` (e.g. p17 ↔ p44) → **warning** (acknowledged).
- OOS value **without** a deviation → **error**.
- A deviation entry that points to a page with **no** OOS value → **warning** (dangling).

## E. Temporal  *(category: temporal)*
| Code | Rule | Severity |
|---|---|---|
| `TIME_END_AFTER_START` | End timestamp strictly after start (Haltezeit, Auftrag) | error |
| `DATE_NOT_BEFORE_PRINT` | No handwritten date before the generation date `09.06.2026` | error |
| `DATE_PAGE_ORDER` | A later page's date not before an earlier page's date (when causally linked) | warning |
| `HOLD_TIME_UNIT` | Hold/temper durations expressed in **hours** | warning |

## F. Conditional / applicability  *(category: applicability)*
| Code | Rule | Severity |
|---|---|---|
| `APPL_MISSING_REQUIRED` | Required field blank **in an applicable region** | error |
| `APPL_FILLED_IN_NA` | Field filled in a region declared N-A by a gate / Kreuzung | error |
| `APPL_GATE_UNANSWERED` | A gate (`Ja`/`Nein …`) left unchecked | error |
| `CHK_SINGLE_SELECT` | Exactly one option chosen in a single-select group | error |
| `CHK_MANDATORY_YES` | A checkbox where only `Ja` is valid is checked | error |

Applicability scopes: `field · block · chapter · rest_of_chapter · redirect(target) · continue`
(see DOMAIN_KNOWLEDGE §6). The engine propagates the state across pages; trailing **Kreuzung** regions
are N-A and never flagged.

## G. Cross-reference (Übertrag)  *(category: cross_reference)*
| Code | Rule | Severity |
|---|---|---|
| `XREF_CARRIED_MATCH` | A value carried "siehe Kapitel X" equals its source field | error |
| `XREF_NEAR_MISS` | Carried value matches only within rounding | warning |

## H. Statistical outlier  *(category: outlier — needs history)*
| Code | Rule | Severity |
|---|---|---|
| `STAT_OUTLIER` | Value far (≥3σ / low Bayesian posterior) from this role's historical distribution | warning |
| `STAT_NO_HISTORY` | Not enough history to score yet | (no flag; note only) |

## I. Extraction confidence  *(category: extraction — from UNCERTAINTY.md)*
| Code | Rule | Severity |
|---|---|---|
| `EXTRACT_LOW_CONF` | Field posterior confidence below the auto-accept threshold | warning |
| `EXTRACT_MODEL_DISAGREE` | Ensemble voters disagree (when ensemble enabled) | warning |

---

## Severity decision summary
```
provably wrong (calc mismatch, missing-required, 4-eyes order/identity,
                bad date format, filled-in-NA, OOS-without-deviation,
                cross-ref mismatch)                                  -> ERROR
uncertain / acknowledged / statistical
                (low confidence, model disagreement, outlier,
                 OOS-with-deviation, rounding/near-miss, NKS format) -> WARNING
clean + confident + consistent                                       -> NO FLAG
```

## Auto-accept gate (ties to "perfect accuracy")
A field is **auto-accepted** (committed without human review) **only if** it has high posterior
confidence **and** zero `error` flags **and** zero `warning` flags. Anything else routes to the human
review queue, ordered errors-first. See [`UNCERTAINTY.md`](UNCERTAINTY.md).
