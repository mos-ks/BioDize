"""Solution-Excel recall scorer.

Compares OUR stored detections for a processed document against the host's
grading sheet (`Solution example-2.xlsx`) to answer the only question that
matters for the challenge: are we catching EVERY error the host marked?

The host's "Suspect / ..." rows are the ground-truth errors; "Online" rows are
clean. We match each host parameter row to our field(s) by normalized label and
check whether we flagged it. Output: recall (caught vs missed), the explicit
MISSED list (false negatives — what to fix), and our extra flags (false
positives — acceptable per "FP over FN", but listed so they're not silent).

Run (after a reprocess):
    PYTHONPATH=. python scripts/solution_recall.py                # latest real doc
    PYTHONPATH=. python scripts/solution_recall.py --doc d_xxxx
    PYTHONPATH=. python scripts/solution_recall.py --xlsx "../Solution example-2.xlsx"
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from app.db.base import SessionLocal
from app.db import models

try:  # the report contains German + symbols (≤, ·); force UTF-8 on any console
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_XLSX = _REPO_ROOT / "Solution example-2.xlsx"


def _norm(label: str | None) -> str:
    """Normalize a parameter label for matching: lowercase, drop bracketed hints,
    units and punctuation, collapse whitespace."""
    s = (label or "").lower()
    s = re.sub(r"\[.*?\]|\(.*?\)", " ", s)          # drop (Datum/Kürzel), [kg], ...
    s = re.sub(r"[^a-zäöüß0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _is_suspect(condition: str) -> bool:
    # host uses both "Suspect" and the typo "Supect"
    return condition.strip().lower().startswith(("suspect", "supect"))


def load_solution(xlsx: Path) -> list[dict]:
    import openpyxl
    wb = openpyxl.load_workbook(xlsx, data_only=True)
    ws = wb["Sheet1"]
    rows = list(ws.iter_rows(values_only=True))
    out = []
    for r in rows[1:]:
        param = r[5]  # Parameter 1
        cond = r[8]   # Condition
        if not param or not cond:
            continue
        out.append({"label": str(param), "norm": _norm(str(param)),
                    "condition": str(cond).strip(), "text": r[9], "value": r[10]})
    return out


def our_fields(db, document_id: str) -> list[models.Field]:
    return (db.query(models.Field)
            .filter(models.Field.document_id == document_id)
            .order_by(models.Field.page_no).all())


def latest_real_doc(db) -> models.Document | None:
    docs = db.query(models.Document).order_by(models.Document.created_at.desc()).all()
    for d in docs:
        if "sim" not in (d.doc_no or "").lower():
            return d
    return docs[0] if docs else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", default=None, help="document_id (default: latest non-simulated)")
    ap.add_argument("--xlsx", default=str(_DEFAULT_XLSX))
    args = ap.parse_args()

    db = SessionLocal()
    doc = db.get(models.Document, args.doc) if args.doc else latest_real_doc(db)
    if not doc:
        print("no document found — process one first"); return
    fields = our_fields(db, doc.id)

    # Fuzzy match each host row to our field(s): exact normalized label, OR strong
    # token overlap (host label is a substring of a longer field label), OR same
    # numeric value. A host error is "caught" if any matched field carries a flag.
    def _num(v):
        try:
            return float(str(v).replace(",", "."))
        except (TypeError, ValueError):
            return None

    field_info = [(f, _norm(f.label_raw), _num(f.value_norm)) for f in fields]
    our_flag_count = sum(1 for f in fields if f.flags)

    def candidates(r) -> list[models.Field]:
        toks = [t for t in r["norm"].split() if len(t) > 2]
        need = max(2, round(len(toks) * 0.7))
        hv = _num(r["value"] if r["value"] is not None else r["text"])
        out = []
        for f, fnl, fv in field_info:
            same = fnl == r["norm"]
            overlap = bool(toks) and sum(1 for t in toks if t in fnl) >= need
            sub = len(r["norm"]) >= 4 and r["norm"] in fnl   # short host label inside a longer field label
            valmatch = hv is not None and fv is not None and abs(hv - fv) < 1e-6
            if same or overlap or sub or valmatch:
                out.append(f)
        return out

    sol = load_solution(Path(args.xlsx))
    host_suspect = [r for r in sol if _is_suspect(r["condition"])]

    caught, missed = [], []
    matched_ids: set[int] = set()
    for r in host_suspect:
        cands = candidates(r)
        matched_ids.update(id(f) for f in cands)
        present = bool(cands)
        hit = any(f.flags for f in cands)
        (caught if hit else missed).append({**r, "extracted": present})

    # our flagged fields not matched to any host-suspect row (potential false positives)
    extra = sorted({f.label_raw for f in fields if f.flags and id(f) not in matched_ids})

    n = len(host_suspect)
    rec = len(caught) / n if n else 0.0
    print(f"\n=== Solution recall: {doc.doc_no}  ({doc.id}) ===")
    print(f"host suspect rows : {n}")
    print(f"  caught (TP)     : {len(caught)}")
    print(f"  MISSED (FN)     : {len(missed)}")
    print(f"recall            : {rec:.0%}   (target: 100% — FP over FN)")
    print(f"our total flags   : {our_flag_count}")

    by_cond = Counter(r["condition"] for r in missed)
    if by_cond:
        print("\nmissed by host verdict:")
        for cond, c in by_cond.most_common():
            print(f"  [{c:>3}] {cond}")

    if missed:
        print("\n--- MISSED (fix these) ---")
        for r in missed:
            why = "" if r["extracted"] else "  (NOT EXTRACTED)"
            print(f"  {r['label']!r}  <- {r['condition']}  text={r['text']!r}{why}")

    if extra:
        print(f"\n--- our flags with no matching host-suspect row ({len(extra)}; review) ---")
        for lab in extra[:40]:
            print(f"  {lab!r}")
    db.close()


if __name__ == "__main__":
    main()
