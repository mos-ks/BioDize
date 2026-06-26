# Challenge — Digital Workflow Transformation of Production Records in Pharma

**Category:** Digitalization · **Host:** Rentschler Biopharma · **Duration:** 72 hours

## Problem
We produce medicines in repeated batch campaigns, generating large volumes of **handwritten**
documentation for each batch. These paper-based records are difficult to access, search, and analyze,
limiting our ability to gain process insights and efficiently use historical data. To improve
understanding and enable data-driven decisions, the information needs to be **digitized and stored in a
structured database**.

### Long version
Each batch typically produces **~20 forms with 100–200 pages**, where parameters and values are manually
recorded in slightly varying formats. Records are scanned and stored on SharePoint, but the data remains
**unstructured**, hard to access, and cannot be efficiently searched or analyzed. The handwritten
information must be automatically **extracted, structured, and stored**, by a flexible system that can
handle varying form layouts, correctly **associate parameters with values**, and support validation,
review, and long-term usability within a **controlled, secure infrastructure**.

## Expected solution

### Requirements (must-have)
- System must run **locally or on controlled infrastructure**. No public services without complete control of the data.
- **Read in all information.**
- **Associate the response to the parameter.**
- Explanations and other prose from the form should **not** be kept.
- **Do not hard-code the parameters** — each form looks slightly different.
- You **can/should** hard-code information such as **document and page number**.
- **Write into Excel.**

### Wishlist (nice-to-have)
- **Highlight responses if the value is unexpected:**
  - Impossible values (e.g., a date on page 6 before a date on page 3, or before the print date).
  - Values outside the range stated in the documents.
  - Values unlikely (e.g., 3 standard deviations from previous values of the component).
  - Calculation would be wrong (e.g., if two times are used to calculate a hold time).
- **Easy review** of the original data from a review interface.
- Allow a human review to **correct** detected values.
- **Highlight missing data.**
- No empty (blank template) form required.

## Host clarifications (from meeting notes — see DOMAIN_KNOWLEDGE.md / VALIDATION_RULES.md)
- The goal is **perfect accuracy**: the system is *right or it asks* — never silently wrong.
- Output is graded into **two categories: `warning` and `error`** (not everything is an error).
- Lean into **uncertainty quantification** (Bayesian / confidence-driven review).
- Dates must be **zero-padded** `DD.MM.YYYY` (`10.6.2026` → error).
- `Geprüft` cannot predate `Bearbeitet` (review only happens after processing — 4-eyes).
- Calculations are **physics-based** (e.g. `V = m × ρ`); concentration `c` is a **given** input.
- Parameter names are **fuzzy** — bind rules to the *role*, not the literal word.
- "findet keine Anwendung" has a **scope** (field / block / chapter / rest-of-chapter / redirect).
- Bounding boxes must take the reviewer to the **exact location** in the PDF.
- Eventual model target: a **local model** / the new **Mistral** OCR model; access to **all models + Codex** now.
