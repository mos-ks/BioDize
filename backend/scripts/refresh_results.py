"""Regenerate the live extracted-fields snapshot from a processed document.

Same job the "Re-eval" button triggers, but from the CLI/CI: dumps a document's
current DB rows (incl. stored flags) to ``results/extracted_fields.live.json`` so
the evaluation scorecard reflects the latest pipeline run instead of the frozen
committed baseline. No model calls — never spends credits.

Run (after a reprocess):
    PYTHONPATH=. python scripts/refresh_results.py                # latest real doc
    PYTHONPATH=. python scripts/refresh_results.py --doc d_xxxx
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.db.base import SessionLocal
from app.db import models
from app.evaluation.results_dump import write_results

try:  # titles/labels contain German + symbols; force UTF-8 on any console
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LIVE_JSON = _REPO_ROOT / "results" / "extracted_fields.live.json"


def _pick_doc(db, doc_id: str | None) -> models.Document | None:
    if doc_id:
        return db.get(models.Document, doc_id)
    # Latest real (non-simulated) document by creation time.
    q = db.query(models.Document).order_by(models.Document.created_at.desc())
    for d in q.all():
        if not (d.source_path or "").lower().startswith("simulated"):
            return d
    return q.first()


def main() -> int:
    p = argparse.ArgumentParser(description="Refresh results/extracted_fields.live.json from the DB")
    p.add_argument("--doc", metavar="DOC_ID", help="document id (default: latest real doc)")
    p.add_argument("--out", metavar="PATH", help=f"output path (default: {_LIVE_JSON})")
    args = p.parse_args()

    out = Path(args.out) if args.out else _LIVE_JSON
    with SessionLocal() as db:
        doc = _pick_doc(db, args.doc)
        if doc is None:
            print("[ERROR] no document found in the DB")
            return 1
        n = write_results(doc, db, out)
    print(f"  wrote {n} fields for {doc.id} ({doc.title}) -> {out}")
    print("  open Eval AI (or hit Re-eval) to score against gold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
