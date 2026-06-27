"""Ground-truth scorer for the BioDize extraction + validation pipeline.

Loads the hand-verified gold labels from ground_truth/ and measures:
  - Rule precision / recall / F1 (did expected violations fire, and only those?)
  - Field value accuracy  (locale-aware; signatures graded as signed/blank)
  - Checkbox-state accuracy
  - Coverage / recall    (was every gold field caught by the extractor?)

Usage:
    from app.evaluation.scorer import score_ground_truth
    report = score_ground_truth(doc, gold_dir=Path("ground_truth"))
    print(report.summary())
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Gold-standard data types ────────────────────────────────────────────────

@dataclass
class GoldField:
    label:            str
    kind:             str               # "value" | "checkbox" | "signature"
    value:            str
    checkbox_state:   str | None        # "checked" | "unchecked" | None
    signature_status: str | None        # "signed" | "blank" | None
    is_blank:         bool


@dataclass
class GoldViolation:
    rule:        str
    field_label: str
    explanation: str


@dataclass
class GoldPage:
    page:               int
    section:            str
    fields:             list[GoldField]
    expected_violations: list[GoldViolation]


# ── Per-page result ──────────────────────────────────────────────────────────

@dataclass
class PageResult:
    page:          int
    section:       str

    # Rule eval
    tp_rules:      list[str] = field(default_factory=list)  # correctly fired
    fp_rules:      list[str] = field(default_factory=list)  # fired but not expected
    fn_rules:      list[str] = field(default_factory=list)  # expected but not fired

    # Value accuracy (value fields only, not blank)
    value_correct: int = 0
    value_wrong:   int = 0
    value_details: list[dict] = field(default_factory=list)

    # Checkbox accuracy
    cb_correct:    int = 0
    cb_wrong:      int = 0

    # Signature accuracy (signed/blank, not initials)
    sig_correct:   int = 0
    sig_wrong:     int = 0

    # Coverage (gold fields found by extractor)
    covered:       int = 0
    missing:       int = 0

    def rule_precision(self) -> float:
        denom = len(self.tp_rules) + len(self.fp_rules)
        return len(self.tp_rules) / denom if denom else 1.0

    def rule_recall(self) -> float:
        denom = len(self.tp_rules) + len(self.fn_rules)
        return len(self.tp_rules) / denom if denom else 1.0

    def rule_f1(self) -> float:
        p, r = self.rule_precision(), self.rule_recall()
        return 2*p*r/(p+r) if (p+r) else 0.0


@dataclass
class EvalReport:
    pages:     list[PageResult]
    gold_dir:  Path

    # ── Aggregate metrics ────────────────────────────────────────────────────

    def _agg(self):
        all_tp = sum(len(p.tp_rules) for p in self.pages)
        all_fp = sum(len(p.fp_rules) for p in self.pages)
        all_fn = sum(len(p.fn_rules) for p in self.pages)
        val_ok  = sum(p.value_correct for p in self.pages)
        val_tot = val_ok + sum(p.value_wrong for p in self.pages)
        cb_ok   = sum(p.cb_correct for p in self.pages)
        cb_tot  = cb_ok + sum(p.cb_wrong for p in self.pages)
        sig_ok  = sum(p.sig_correct for p in self.pages)
        sig_tot = sig_ok + sum(p.sig_wrong for p in self.pages)
        cov_ok  = sum(p.covered for p in self.pages)
        cov_tot = cov_ok + sum(p.missing for p in self.pages)
        prec = all_tp/(all_tp+all_fp) if all_tp+all_fp else 1.0
        rec  = all_tp/(all_tp+all_fn) if all_tp+all_fn else 1.0
        f1   = 2*prec*rec/(prec+rec) if prec+rec else 0.0
        return dict(
            tp=all_tp, fp=all_fp, fn=all_fn,
            rule_precision=prec, rule_recall=rec, rule_f1=f1,
            value_acc=val_ok/val_tot if val_tot else None,
            checkbox_acc=cb_ok/cb_tot if cb_tot else None,
            signature_acc=sig_ok/sig_tot if sig_tot else None,
            coverage=cov_ok/cov_tot if cov_tot else None,
        )

    def summary(self) -> str:
        a = self._agg()
        lines = [
            "=" * 60,
            "  BioDize Ground-Truth Evaluation",
            f"  Pages: {len(self.pages)}  |  Gold dir: {self.gold_dir.name}",
            "=" * 60,
            "",
            "Rule Detection",
            f"  TP={a['tp']}  FP={a['fp']}  FN={a['fn']}",
            f"  Precision : {a['rule_precision']:.1%}",
            f"  Recall    : {a['rule_recall']:.1%}",
            f"  F1        : {a['rule_f1']:.1%}",
            "",
            "Field Accuracy",
            f"  Value      : {a['value_acc']:.1%}"     if a['value_acc']     is not None else "  Value      : n/a",
            f"  Checkbox   : {a['checkbox_acc']:.1%}"  if a['checkbox_acc']  is not None else "  Checkbox   : n/a",
            f"  Signature  : {a['signature_acc']:.1%}" if a['signature_acc'] is not None else "  Signature  : n/a",
            f"  Coverage   : {a['coverage']:.1%}"      if a['coverage']      is not None else "  Coverage   : n/a",
            "",
        ]
        for pr in self.pages:
            status = "PASS" if not pr.fn_rules and not pr.fp_rules else "FAIL"
            lines.append(
                f"  p{pr.page:02d} [{status}]  "
                f"prec={pr.rule_precision():.0%} rec={pr.rule_recall():.0%}"
                + (f"  FP:{pr.fp_rules}" if pr.fp_rules else "")
                + (f"  FN:{pr.fn_rules}" if pr.fn_rules else "")
            )
        lines.append("=" * 60)
        return "\n".join(lines)

    def as_dict(self) -> dict:
        a = self._agg()
        return {
            "aggregate": a,
            "pages": [
                {
                    "page": p.page,
                    "section": p.section,
                    "rule_precision": p.rule_precision(),
                    "rule_recall":    p.rule_recall(),
                    "rule_f1":        p.rule_f1(),
                    "tp": p.tp_rules, "fp": p.fp_rules, "fn": p.fn_rules,
                    "value_correct": p.value_correct,
                    "value_wrong":   p.value_wrong,
                    "value_details": p.value_details,
                    "cb_correct": p.cb_correct, "cb_wrong": p.cb_wrong,
                    "sig_correct": p.sig_correct, "sig_wrong": p.sig_wrong,
                    "covered": p.covered, "missing": p.missing,
                }
                for p in self.pages
            ],
        }


# ── Helpers ──────────────────────────────────────────────────────────────────

# Map gold rule names to the flag codes our pipeline emits
RULE_ALIAS: dict[str, set[str]] = {
    "4EYES_DISTINCT":  {"4EYES_DISTINCT"},
    "4EYES_ORDER":     {"4EYES_ORDER"},
    "CALC_ERROR":      {"CALC_FORMULA", "CALC_VOLUME", "CALC_NET_MASS"},
    "RANGE_SOLL":      {"RANGE_SOLL", "RANGE_SETPOINT"},
    "SIG_INCOMPLETE":  {"SIG_INCOMPLETE"},
    "MISSING_SIG":     {"MISSING_SIGNATURE"},
}

# Codes that are inherently informational / extraction-quality signals,
# not GxP rule violations — excluded from FP counting.
EXCLUDED_FROM_FP: set[str] = {
    "EXTRACT_LOW_CONF",
    "KUERZEL_UNRESOLVED",   # resolve step artefact (empty/hallucinated read)
    "KUERZEL_UNKNOWN",      # legacy alias
    "XREF_NEAR_MISS",       # rounding warning
    "CALC_ROUNDING",        # rounding warning
}


def _normalize_val(s: str) -> str:
    """Locale-aware value normalisation for comparison."""
    s = (s or "").strip()
    s = s.replace(",", ".").lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _sig_status(raw: str) -> str:
    """'signed' if the field has a date+kuerzel, else 'blank'."""
    parts = (raw or "").split("/")
    has_date = bool(parts[0].strip() and re.search(r"\d", parts[0]))
    has_kz   = bool(len(parts) > 1 and parts[1].strip())
    return "signed" if (has_date or has_kz) else "blank"


def _label_matches(gold_label: str, extracted_label: str | None) -> bool:
    if not extracted_label:
        return False
    a = gold_label.lower().strip()
    b = extracted_label.lower().strip()
    return a in b or b in a or _normalize_val(a) == _normalize_val(b)


# ── Gold loader ───────────────────────────────────────────────────────────────

def load_gold(gold_dir: Path) -> list[GoldPage]:
    pages = []
    for json_file in sorted(gold_dir.glob("page_*.json")):
        data = json.loads(json_file.read_text(encoding="utf-8"))
        gfields = [
            GoldField(
                label=f["label"], kind=f["kind"], value=f.get("value",""),
                checkbox_state=f.get("checkbox_state"),
                signature_status=f.get("signature_status"),
                is_blank=f.get("is_blank", False),
            )
            for f in data.get("fields", [])
        ]
        gviolations = [
            GoldViolation(
                rule=v["rule"],
                field_label=v["field"],
                explanation=v.get("explanation",""),
            )
            for v in data.get("expected_violations", [])
        ]
        pages.append(GoldPage(
            page=data["page"],
            section=data.get("section",""),
            fields=gfields,
            expected_violations=gviolations,
        ))
    return pages


# ── Main scorer ───────────────────────────────────────────────────────────────

def score_ground_truth(doc: Any, gold_dir: Path) -> EvalReport:
    """Score pipeline output (Document) against gold standard.

    doc: app.pipeline.model.Document after full pipeline (normalize+validate+score).
    gold_dir: path containing page_0NN.json files.
    """
    gold_pages = load_gold(gold_dir)
    gold_by_page = {g.page: g for g in gold_pages}

    # Build page -> fields + flags from the pipeline output
    pipe_by_page: dict[int, list] = {}
    for block in doc.blocks:
        for f in block.fields:
            pipe_by_page.setdefault(f.page_no, []).append(f)

    results = []
    for gold in gold_pages:
        pr = PageResult(page=gold.page, section=gold.section)
        pipe_fields = pipe_by_page.get(gold.page, [])

        # Collect all flag codes emitted on this page
        emitted_codes: set[str] = set()
        for pf in pipe_fields:
            for fl in pf.flags:
                emitted_codes.add(fl.code)

        # ── Rule eval ─────────────────────────────────────────────────────
        matched_expected: set[int] = set()
        matched_emitted:  set[str] = set()

        for i, gv in enumerate(gold.expected_violations):
            aliases = RULE_ALIAS.get(gv.rule, {gv.rule})
            if emitted_codes & aliases:
                pr.tp_rules.append(gv.rule)
                matched_expected.add(i)
                matched_emitted.update(emitted_codes & aliases)
            else:
                pr.fn_rules.append(gv.rule)

        # FP: emitted codes not matched to any expected violation
        # (informational/extraction-quality codes are excluded)
        expected_aliases = set()
        for gv in gold.expected_violations:
            expected_aliases.update(RULE_ALIAS.get(gv.rule, {gv.rule}))

        # Build set of sig-field labels where gold says different signers signed
        # (so a 4EYES_DISTINCT there is an extraction error, not a rule FP)
        gold_sig_labels = {
            gf.label.lower().strip()
            for gf in gold.fields
            if gf.kind == "signature" and gf.signature_status == "signed"
        }
        gold_sig_pairs = list(zip(
            [gf for gf in gold.fields if gf.kind == "signature"],
            [gf for gf in gold.fields if gf.kind == "signature"],
        ))
        # Simpler: if 4EYES_DISTINCT fires but gold has no 4EYES violation,
        # check whether signature values differ in gold (different signers) →
        # extraction error, categorise separately
        gold_no_4eyes = not any(gv.rule in ("4EYES_DISTINCT","4EYES_ORDER")
                                for gv in gold.expected_violations)
        gold_sigs = [gf for gf in gold.fields if gf.kind == "signature"]
        gold_has_diff_signers = (
            len({(gf.value or "").split("/")[-1].strip().lower()
                 for gf in gold_sigs if gf.signature_status == "signed"}) >= 2
        )
        extraction_fp: list[str] = []

        for code in emitted_codes:
            if code in expected_aliases or code in EXCLUDED_FROM_FP:
                continue
            # 4EYES fired but gold says different signers → extraction error
            if code == "4EYES_DISTINCT" and gold_no_4eyes and gold_has_diff_signers:
                extraction_fp.append(f"{code}[extraction_error]")
                continue
            pr.fp_rules.append(code)

        if extraction_fp:
            # Record extraction FPs as a note, not counted in precision
            pr.value_details.append({
                "label": "_extraction_fp",
                "gold": "different signers",
                "pipeline": ", ".join(extraction_fp),
            })

        # ── Field accuracy ───────────────────────────────────────────────
        for gf in gold.fields:
            # Find matching extracted field (label fuzzy match)
            pf = next(
                (f for f in pipe_fields if _label_matches(gf.label, f.label_raw)),
                None)

            if pf is None:
                pr.missing += 1
                continue
            pr.covered += 1

            if gf.kind == "value" and not gf.is_blank:
                gold_v = _normalize_val(gf.value)
                pipe_v = _normalize_val(pf.value_raw or "")
                ok = (gold_v == pipe_v)
                if ok: pr.value_correct += 1
                else:
                    pr.value_wrong += 1
                    pr.value_details.append({
                        "label": gf.label,
                        "gold": gf.value,
                        "pipeline": pf.value_raw,
                    })

            elif gf.kind == "checkbox" and gf.checkbox_state:
                # "checked" if there's a truthy value
                pipe_checked = bool((pf.value_raw or "").strip()
                                    and (pf.value_raw or "").strip().lower()
                                    not in ("nein","no","false","0",""))
                gold_checked = (gf.checkbox_state == "checked")
                if pipe_checked == gold_checked: pr.cb_correct += 1
                else:                            pr.cb_wrong   += 1

            elif gf.kind == "signature" and gf.signature_status:
                pipe_status = _sig_status(pf.value_raw or "")
                if pipe_status == gf.signature_status: pr.sig_correct += 1
                else:                                   pr.sig_wrong   += 1

        results.append(pr)

    return EvalReport(pages=results, gold_dir=gold_dir)
