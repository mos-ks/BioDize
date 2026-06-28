"""
BioDize Remote Eval
===================
Fetches fields from the cloudflare backend, scores them against the
ground_truth/* waypoints, and asserts that aggregate metrics match
the web app's "AI Evaluation vs Ground Truth" panel.

Bbox data is excluded from all comparisons (discrete location only).
Pass/fail per page mirrors the web app: any rule FP/FN OR field
accuracy error (value, checkbox, signature) counts as FAIL.

Usage:
  py evaluator/eval_remote.py              # single run + assertion check
  py evaluator/eval_remote.py --loop       # retry every 30s until all assertions pass
  py evaluator/eval_remote.py -v           # show per-field mismatches
  py evaluator/eval_remote.py --url https://...   # override backend URL
  py evaluator/eval_remote.py --delay 60          # retry interval (seconds)
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT   = Path(__file__).parent.parent.resolve()
GT_DIR = ROOT / "ground_truth"

BASE = "https://rich-nil-civic-glance.trycloudflare.com"

# ── Reference scores from web app screenshot (2026-06-28) ────────────────────
# Update this when the backend improves and the web app shows new numbers.
REFERENCE = {
    "tp": 14, "fp": 1, "fn": 0,
    "rule_precision_pct": 93,   # round(14/15 * 100)
    "rule_recall_pct":   100,   # 14/14
    "value_acc_pct":      98,
    "checkbox_acc_pct":  100,
    "signature_acc_pct": 100,
    "coverage_pct":      100,
    "page_fail": {9, 10},
    "page_pass": {11, 14, 17, 18, 19, 25, 31},
}

# ── Rule/flag mappings (mirrors backend/app/evaluation/scorer.py) ─────────────

RULE_ALIAS: dict[str, set[str]] = {
    "4EYES_DISTINCT":    {"4EYES_DISTINCT"},
    "4EYES_ORDER":       {"4EYES_ORDER"},
    "CALC_ERROR":        {"CALC_FORMULA", "CALC_VOLUME", "CALC_NET_MASS"},
    "RANGE_SOLL":        {"RANGE_SOLL", "RANGE_SETPOINT"},
    "SIG_INCOMPLETE":    {"SIG_INCOMPLETE"},
    "MISSING_SIG":       {"MISSING_SIGNATURE"},
    "MISSING_CHECKMARK": {"MISSING_CHECKMARK"},
}

EXCLUDED_FROM_FP: set[str] = {
    "EXTRACT_LOW_CONF", "KUERZEL_UNRESOLVED", "KUERZEL_UNKNOWN",
    "XREF_NEAR_MISS", "XREF_MISMATCH", "CALC_ROUNDING",
    "FMT_DATE_PADDING", "DATE_YEAR_SUSPECT", "DATE_BEFORE_PRINT", "DATE_FAR_FUTURE",
}

# ── Label/value helpers (mirrors scorer.py exactly) ───────────────────────────

def _nv(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().replace(",", ".").lower())

def _sig_status(raw: str) -> str:
    parts = (raw or "").split("/")
    has_date = bool(parts[0].strip() and re.search(r"\d", parts[0]))
    has_kz   = bool(len(parts) > 1 and parts[1].strip())
    return "signed" if (has_date or has_kz) else "blank"

def _nl(s: str) -> str:
    s = (s or "").lower().strip()
    s = s.replace("—", " ").replace("–", " ")
    s = re.sub(r"([a-z0-9])-([a-z])", r"\1 \2", s)
    s = re.sub(r"\s*[\[\(][^\]\)]*[\]\)]", "", s)
    s = re.sub(r"\s*(?::|-)\s*(ja|nein\b.*|kein einsatz)\s*$", "", s, flags=re.I)
    s = re.sub(r":\s*[^:]+$", "", s)
    return re.sub(r"\s+", " ", s.rstrip(":. ")).strip()

def _leading_measure_prefix(label: str) -> str | None:
    m = re.match(r"^\s*([mvc])\b", _nl(label))
    return m.group(1) if m else None

def _label_option(lbl: str) -> str | None:
    raw = re.sub(r"\s*\(zeile\s+\d+\)\s*$", "", (lbl or "").strip(), flags=re.I)
    raw = re.sub(r"\s*\([^)]*\)", "", raw).strip()
    m = re.search(r"(?:\:|—|–|-)\s*(ja|nein\b.*|kein einsatz)\s*$", raw, re.I)
    if not m:
        m = re.search(r":\s*([^:—–-]+)\s*$", raw, re.I)
    return re.sub(r"\s+", " ", m.group(1).strip().lower()) if m else None

def _label_matches(gold: str, extr: str | None) -> bool:
    if not extr:
        return False
    a, b = _nl(gold), _nl(extr)
    if not a or not b:
        return False
    pa = _leading_measure_prefix(gold)
    pb = _leading_measure_prefix(extr)
    if pa and pb and pa != pb:
        return False
    if a in b or b in a:
        return True
    a_ns = re.sub(r"\s+", "", a); b_ns = re.sub(r"\s+", "", b)
    if a_ns in b_ns or b_ns in a_ns:
        return True
    a_tok = [t for t in a.split() if len(t) >= 3]
    b_tok = [t for t in b.split() if len(t) >= 3]
    if a_tok and b_tok and a_tok[0] == b_tok[0]:
        if sum(1 for t in a_tok[:4] if t in b_tok) >= min(2, len(a_tok)):
            return True
    return False

def _label_score(gold: str, extr: str | None) -> tuple[int, int]:
    gl, el = _nl(gold), _nl(extr or "")
    return (0 if gl == el else 1), abs(len(el) - len(gl))

def _value_matches(gold: str, pipe: str | None) -> bool:
    gn, pn = _nv(gold), _nv(pipe or "")
    if gn == pn: return True
    if not gn or not pn: return False
    if re.fullmatch(r"\d{1,2}\.\d{1,2}\.\d{4}", gn) and gn in pn: return True
    if re.fullmatch(r"\d{1,2}:\d{2}", gn) and gn in pn: return True
    if re.search(r"[a-z]", gn):
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(gn)}(?![a-z0-9])", pn))
    if re.fullmatch(r"-?\d+(?:\.\d+)?", gn):
        return bool(re.search(rf"(?<![0-9.]){re.escape(gn)}(?![0-9.])", pn))
    return False

def _cb_for_option(option: str, raw: str) -> bool:
    opt = re.sub(r"\s+", " ", (option or "").strip().lower())
    pv  = re.sub(r"\s+", " ", (raw or "").strip().lower())
    if not opt or not pv: return False
    if opt == "ja":           return bool(re.search(r"(?<![a-z0-9])ja(?![a-z0-9])", pv))
    if opt.startswith("nein"): return pv.startswith("nein") or opt in pv
    if opt == "kein einsatz": return "kein einsatz" in pv
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(opt)}(?![a-z0-9])", pv))

def _cb_truthy(raw: str) -> bool:
    pv = re.sub(r"\s+", " ", (raw or "").strip().lower())
    if not pv or pv in {"no", "false", "0"}: return False
    if pv.startswith("nein") or "kein einsatz" in pv or "findet keine anwendung" in pv:
        return False
    return True

# ── API ───────────────────────────────────────────────────────────────────────

def _get(path: str, base: str) -> dict | list | None:
    try:
        req = urllib.request.Request(base + path, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {path}", file=sys.stderr)
    except Exception as e:
        print(f"  Unreachable: {e}", file=sys.stderr)
    return None

def fetch_fields(base: str) -> dict[int, list[dict]]:
    """Fetch fields from the document with the most fields, grouped by page. Bbox dropped."""
    docs = _get("/api/v1/documents", base)
    if not docs: return {}
    # Pick document with most fields so simulated/stub docs are skipped automatically
    best = max(docs, key=lambda d: d.get("n_fields", 0))
    print(f"  Document : {best.get('doc_no', best['id'])} ({best.get('n_fields', '?')} fields)", end="  ")
    fields = _get(f"/api/v1/documents/{best['id']}/fields", base)
    if not fields: return {}
    by_page: dict[int, list[dict]] = {}
    for f in fields:
        f.pop("bbox", None)   # bbox excluded from all comparisons
        by_page.setdefault(f["page_no"], []).append(f)
    return by_page

# ── Page scorer (mirrors scorer.py score_ground_truth logic) ──────────────────

def score_page(gold: dict, pipe: list[dict]) -> dict:
    gold_fields     = gold.get("fields", [])
    gold_violations = gold.get("expected_violations", [])

    emitted: set[str] = {fl["code"] for f in pipe for fl in f.get("flags", [])}

    # Rule TP / FN
    tp, fn = [], []
    expected_aliases: set[str] = set()
    for gv in gold_violations:
        aliases = RULE_ALIAS.get(gv["rule"], {gv["rule"]})
        expected_aliases.update(aliases)
        (tp if emitted & aliases else fn).append(gv["rule"])

    # Rule FP (extraction errors excluded)
    gold_sigs         = [gf for gf in gold_fields if gf["kind"] == "signature"]
    gold_no_4eyes     = not any(gv["rule"] in ("4EYES_DISTINCT", "4EYES_ORDER") for gv in gold_violations)
    gold_diff_signers = len({
        (gf["value"] or "").split("/")[-1].strip().lower()
        for gf in gold_sigs if gf.get("signature_status") == "signed"
    }) >= 2
    fp = []
    for code in emitted:
        if code in expected_aliases or code in EXCLUDED_FROM_FP:
            continue
        if code == "4EYES_DISTINCT" and gold_no_4eyes and gold_diff_signers:
            continue
        fp.append(code)

    # Field accuracy (no bbox)
    val_ok = val_err = cb_ok = cb_err = sig_ok = sig_err = covered = missing = 0
    details: list[dict] = []
    used: set[int] = set()

    for gf in gold_fields:
        cands = [f for f in pipe if _label_matches(gf["label"], f.get("label_raw"))]
        if gf["kind"] in {"value", "signature"}:
            unused = [f for f in cands if id(f) not in used]
            if unused: cands = unused
        if gf["kind"] == "checkbox" and gf.get("value") and len(cands) > 1:
            hits = [f for f in cands if _value_matches(gf["value"], f.get("value_raw"))]
            if hits: cands = hits
        if len(cands) > 1:
            cands.sort(key=lambda f: _label_score(gf["label"], f.get("label_raw")))
        pf = cands[0] if cands else None

        if pf is None:
            missing += 1; continue
        covered += 1
        if gf["kind"] in {"value", "signature"}:
            used.add(id(pf))

        if gf["kind"] == "value" and not gf.get("is_blank"):
            v = gf.get("value", "")
            if v.startswith("…") or v.lower().startswith("siehe"):
                val_ok += 1; continue
            if _value_matches(v, pf.get("value_raw")):
                val_ok += 1
            else:
                val_err += 1
                details.append({"label": gf["label"], "gold": v, "got": pf.get("value_raw")})

        elif gf["kind"] == "checkbox" and gf.get("checkbox_state"):
            gold_chk = gf["checkbox_state"] == "checked"
            opt = _label_option(gf["label"])
            if opt:
                pipe_chk = _cb_for_option(opt, pf.get("value_raw") or "")
            elif gold_chk:
                pipe_chk = (
                    _value_matches(gf.get("value", ""), pf.get("value_raw"))
                    if gf.get("value") else _cb_truthy(pf.get("value_raw") or "")
                )
            else:
                pipe_chk = _cb_truthy(pf.get("value_raw") or "")
            if pipe_chk == gold_chk: cb_ok  += 1
            else:                     cb_err += 1

        elif gf["kind"] == "signature" and gf.get("signature_status"):
            if _sig_status(pf.get("value_raw") or "") == gf["signature_status"]:
                sig_ok  += 1
            else:
                sig_err += 1

    prec = len(tp) / (len(tp) + len(fp)) if (tp or fp) else 1.0
    rec  = len(tp) / (len(tp) + len(fn)) if (tp or fn) else 1.0
    # Page passes only when rules AND all field accuracy metrics are clean
    passed = not fn and not fp and not val_err and not cb_err and not sig_err
    return {
        "pass": passed,
        "tp": tp, "fp": fp, "fn": fn,
        "prec": prec, "rec": rec,
        "val_ok": val_ok, "val_err": val_err,
        "cb_ok": cb_ok, "cb_err": cb_err,
        "sig_ok": sig_ok, "sig_err": sig_err,
        "covered": covered, "missing": missing,
        "details": details,
    }

# ── Assertion helpers ─────────────────────────────────────────────────────────

def _check(label: str, expected, actual, tol: int = 0) -> bool:
    ok = abs(round(actual) - expected) <= tol
    mark = "OK  " if ok else "FAIL"
    print(f"  [{mark}] {label:30s}  expected={expected}  got={round(actual)}")
    return ok

# ── Eval runner ───────────────────────────────────────────────────────────────

def run_eval(base: str, verbose: bool = False) -> tuple[bool, bool]:
    """Returns (all_waypoints_pass, all_assertions_pass)."""
    if not GT_DIR.exists():
        print(f"[ERROR] ground_truth/ not found: {GT_DIR}", file=sys.stderr)
        sys.exit(1)
    gt_files = sorted(GT_DIR.glob("page_*.json"))
    if not gt_files:
        print(f"[ERROR] No page_*.json in {GT_DIR}", file=sys.stderr)
        sys.exit(1)

    print(f"\nBioDize Remote Eval")
    print(f"  Backend  : {base}")
    print(f"  Waypoints: {len(gt_files)} pages in ground_truth/")
    print("=" * 66)

    print("  Fetching fields ...", end="", flush=True)
    by_page = fetch_fields(base)
    if not by_page:
        print(" FAILED (no data)\n")
        return False, False
    n_fields = sum(len(v) for v in by_page.values())
    print(f" {n_fields} fields on {len(by_page)} pages")
    print()

    all_pass = True
    agg = dict(tp=0, fp=0, fn=0, val_ok=0, val_err=0,
               cb_ok=0, cb_err=0, sig_ok=0, sig_err=0,
               covered=0, missing=0)
    page_results: dict[int, bool] = {}

    for gt_file in gt_files:
        gold    = json.loads(gt_file.read_text(encoding="utf-8"))
        page_no = gold["page"]
        r       = score_page(gold, by_page.get(page_no, []))
        page_results[page_no] = r["pass"]

        if not r["pass"]:
            all_pass = False

        tag  = "PASS" if r["pass"] else "FAIL"
        val_t = r["val_ok"] + r["val_err"]
        cb_t  = r["cb_ok"]  + r["cb_err"]
        sig_t = r["sig_ok"] + r["sig_err"]
        line  = (
            f"  p{page_no:02d} [{tag}]  "
            f"prec={r['prec']:.0%} rec={r['rec']:.0%}  "
            f"val={r['val_ok']}/{val_t}  cb={r['cb_ok']}/{cb_t}  sig={r['sig_ok']}/{sig_t}"
        )
        if r["fp"]: line += f"  FP:{r['fp']}"
        if r["fn"]: line += f"  FN:{r['fn']}"
        print(line)

        if r["details"]:
            for d in r["details"]:
                lbl = d["label"][:46]
                print(f"        {lbl:<46}  gold={d['gold']!r:18}  got={d['got']!r}")
            if not verbose and r["pass"]:
                pass   # value details only shown when verbose or page fails

        for k in ("val_ok","val_err","cb_ok","cb_err","sig_ok","sig_err","covered","missing"):
            agg[k] += r[k]
        agg["tp"] += len(r["tp"]); agg["fp"] += len(r["fp"]); agg["fn"] += len(r["fn"])

    # Aggregate metrics
    val_tot = agg["val_ok"]  + agg["val_err"]
    cb_tot  = agg["cb_ok"]   + agg["cb_err"]
    sig_tot = agg["sig_ok"]  + agg["sig_err"]
    cov_tot = agg["covered"] + agg["missing"]

    tot_prec = agg["tp"] / (agg["tp"] + agg["fp"]) if agg["tp"] + agg["fp"] else 1.0
    tot_rec  = agg["tp"] / (agg["tp"] + agg["fn"]) if agg["tp"] + agg["fn"] else 1.0
    tot_f1   = 2*tot_prec*tot_rec/(tot_prec+tot_rec) if tot_prec+tot_rec else 0.0
    val_acc  = agg["val_ok"]  / val_tot if val_tot else None
    cb_acc   = agg["cb_ok"]   / cb_tot  if cb_tot  else None
    sig_acc  = agg["sig_ok"]  / sig_tot if sig_tot else None
    coverage = agg["covered"] / cov_tot if cov_tot else None

    print()
    print("=" * 66)
    print(f"  Rule   TP={agg['tp']}  FP={agg['fp']}  FN={agg['fn']}")
    print(f"         Prec={tot_prec:.1%}  Rec={tot_rec:.1%}  F1={tot_f1:.1%}")
    if val_tot:  print(f"  Value  {agg['val_ok']}/{val_tot} ({val_acc:.0%})")
    if cb_tot:   print(f"  Check  {agg['cb_ok']}/{cb_tot}  ({cb_acc:.0%})")
    if sig_tot:  print(f"  Sig    {agg['sig_ok']}/{sig_tot}  ({sig_acc:.0%})")
    if cov_tot:  print(f"  Cover  {agg['covered']}/{cov_tot}  ({coverage:.0%})")
    print("=" * 66)
    print(f"  Waypoints: {'ALL PASS' if all_pass else 'SOME FAIL'}")

    # ── Assert scores match web app reference ─────────────────────────────────
    print()
    print("  Assertions vs web app reference:")
    ok_list = [
        _check("TP",                REFERENCE["tp"],                agg["tp"]),
        _check("FP",                REFERENCE["fp"],                agg["fp"]),
        _check("FN",                REFERENCE["fn"],                agg["fn"]),
        _check("Rule precision %",  REFERENCE["rule_precision_pct"], tot_prec * 100, tol=1),
        _check("Rule recall %",     REFERENCE["rule_recall_pct"],    tot_rec  * 100, tol=1),
        _check("Value accuracy %",  REFERENCE["value_acc_pct"],      (val_acc or 0) * 100, tol=1),
        _check("Checkbox acc %",    REFERENCE["checkbox_acc_pct"],   (cb_acc  or 0) * 100, tol=1),
        _check("Signature acc %",   REFERENCE["signature_acc_pct"],  (sig_acc or 0) * 100, tol=1),
        _check("Coverage %",        REFERENCE["coverage_pct"],       (coverage or 0) * 100, tol=1),
    ]
    # Per-page pass/fail
    ref_fail = REFERENCE["page_fail"]
    ref_pass = REFERENCE["page_pass"]
    for pg, passed in sorted(page_results.items()):
        expected_pass = pg in ref_pass
        expected_fail = pg in ref_fail
        if expected_pass:
            ok = _check(f"p{pg:02d} == PASS", 1, int(passed))
        elif expected_fail:
            ok = _check(f"p{pg:02d} == FAIL", 0, int(passed))
        else:
            ok = True  # page not in reference, skip
        ok_list.append(ok)

    all_asserts = all(ok_list)
    print()
    print(f"  Assertions: {'ALL PASS' if all_asserts else 'SOME FAIL'}")
    return all_pass, all_asserts


def main() -> None:
    args    = sys.argv[1:]
    base    = BASE
    loop    = False
    verbose = False
    delay   = 30
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--loop":
            loop = True
        elif a in ("-v", "--verbose"):
            verbose = True
        elif a == "--url" and i + 1 < len(args):
            i += 1; base = args[i]
        elif a == "--delay" and i + 1 < len(args):
            i += 1; delay = int(args[i])
        i += 1

    attempt = 0
    while True:
        attempt += 1
        if loop:
            print(f"\n[attempt {attempt}]", end="")
        _waypoints_ok, asserts_ok = run_eval(base, verbose=verbose)
        if asserts_ok or not loop:
            sys.exit(0 if asserts_ok else 1)
        print(f"\n  Retrying in {delay}s ...  (Ctrl+C to stop)")
        time.sleep(delay)


if __name__ == "__main__":
    main()
