"""
BioDize  -  Echte Ergebnisse laden
=================================
Importiert results/extracted_fields.json (323 Felder, 21 Fehler, 14 Warnungen
aus dem vollständigen PDF-Lauf mit GPT-5.5 + Mistral OCR) direkt in die
lokale SQLite-Datenbank, ohne API-Keys zu benötigen.

Starten:  py load_results.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Venv-Bootstrap
ROOT = Path(__file__).parent.parent.resolve()  # evaluator/ -> repo root
VENV_PY    = ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
BACKEND    = ROOT / "backend"
RESULTS    = ROOT / "results" / "extracted_fields.json"

if VENV_PY.exists() and Path(sys.executable).resolve() != VENV_PY.resolve():
    result = subprocess.run([str(VENV_PY)] + sys.argv)
    sys.exit(result.returncode)

sys.path.insert(0, str(BACKEND))
os.chdir(str(BACKEND))

# Jetzt Backend-Imports
from sqlalchemy.orm import Session
from app.db.base import init_db, engine
from app.db import models


def _uuid(prefix: str) -> str:
    import uuid
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _levenshtein(a: str, b: str) -> int:
    if a == b: return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j-1] + 1, prev[j-1] + (ca != cb)))
        prev = cur
    return prev[len(b)]


_DATE_RE = __import__("re").compile(r"(\d{1,2}\.\d{1,2}\.)(\d{4})")
_REF_YEAR = 2026


def _correct_year_in_str(s: str) -> str:
    """Wendet _correct_year auf alle Jahreszahlen in einem String an."""
    def _fix(m):
        y = int(m.group(2))
        if y == _REF_YEAR:
            return m.group(0)
        y_str, ref_str = str(y), str(_REF_YEAR)
        if len(y_str) == len(ref_str):
            diffs = sum(1 for a, b in zip(y_str, ref_str) if a != b)
            if diffs == 1:
                return m.group(1) + str(_REF_YEAR)
            if diffs == 2 and abs(y - _REF_YEAR) > 2:
                return m.group(1) + str(_REF_YEAR)
        return m.group(0)
    return _DATE_RE.sub(_fix, s or "")


_DATE_FLAGS = {"DATE_BEFORE_PRINT", "DATE_FAR_FUTURE", "4EYES_ORDER", "DATE_YEAR_SUSPECT"}


def _apply_year_corrections(fields: list) -> list:
    """Korrigiert OCR-Jahresfehler und entfernt damit ungueltiger Date-Flags."""
    DATE_ROLES = {"signature_processed", "signature_checked",
                  "hold_start", "hold_end", "hold_duration"}
    corrected = flags_removed = 0
    result = []
    for fld in fields:
        role = fld.get("role") or ""
        raw  = fld.get("value_raw") or fld.get("value") or ""
        if role in DATE_ROLES or _DATE_RE.search(raw):
            fixed = _correct_year_in_str(raw)
            if fixed != raw:
                fld = dict(fld)
                fld["value_raw"] = fixed
                fld["value"]     = fixed
                # Flags die durch die Jahreskorrektur obsolet werden entfernen
                old_flags = fld.get("flags", [])
                new_flags = [fl for fl in old_flags if fl.get("code") not in _DATE_FLAGS]
                removed = len(old_flags) - len(new_flags)
                if removed:
                    fld["flags"] = new_flags
                    flags_removed += removed
                corrected += 1
        result.append(fld)
    if corrected:
        print(f"  Jahreskorrektur: {corrected} Felder korrigiert, {flags_removed} Date-Flags entfernt")
    return result


def _normalize_kuerzel_json(fields: list, registry: set) -> list:
    """Korrigiert OCR-Kuerzel-Varianten (ohp, ohr, o4e, olp) -> kanonisch (ohe)."""
    corrected = 0
    result = []
    for fld in fields:
        role = fld.get("role") or ""
        if "signature" in role:
            raw = fld.get("value_raw") or ""
            if "/" in raw:
                prefix, k = raw.rsplit("/", 1)
                k_low = k.strip().lower()
                if k_low not in registry:
                    best_dist, best_k = 99, None
                    for r in registry:
                        d = _levenshtein(k_low, r)
                        if d < best_dist:
                            best_dist, best_k = d, r
                    if best_k and best_dist <= 2:
                        fld = dict(fld)
                        fld["value_raw"] = prefix + "/ " + best_k
                        fld["value"]     = fld["value_raw"]
                        corrected += 1
        result.append(fld)
    if corrected:
        print(f"  Kuerzel-Normalisierung: {corrected} OCR-Varianten korrigiert")
    return result


PDF_PATH = ROOT / "data" / "scanned_batch_documentation.pdf"
PAGES_DIR = BACKEND / "var" / "pages"


def render_pages() -> dict[int, str]:
    """Rendert alle PDF-Seiten zu PNGs. Gibt {page_no: path} zurück."""
    PAGES_DIR.mkdir(parents=True, exist_ok=True)

    # Bereits gerenderte Seiten wiederverwenden
    existing = {
        int(p.stem.split("_")[1]): str(p)
        for p in PAGES_DIR.glob("page_*.png")
    }

    try:
        import pypdfium2 as pdfium
    except ImportError:
        print("  [WARN] pypdfium2 nicht installiert  -  keine Seitenbilder.")
        return existing

    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        print("  [WARN] Pillow nicht installiert  -  keine Seitenbilder.")
        return existing

    if not PDF_PATH.exists():
        print(f"  [WARN] PDF nicht gefunden: {PDF_PATH}")
        return existing

    doc = pdfium.PdfDocument(str(PDF_PATH))
    scale = 200 / 72  # 200 DPI

    for i in range(len(doc)):
        page_no = i + 1
        if page_no in existing:
            continue  # bereits gerendert
        page = doc[i]
        bmp = page.render(scale=scale)
        img = bmp.to_pil()
        path = PAGES_DIR / f"page_{page_no:03d}.png"
        img.save(str(path))
        existing[page_no] = str(path)
        print(f"  Seite {page_no:02d}/{len(doc)} gerendert", end="\r")

    print(f"  {len(doc)} Seiten gerendert -> {PAGES_DIR}")
    return existing


def load(clear: bool = True) -> None:
    if not RESULTS.exists():
        print(f"[FEHLER] {RESULTS} nicht gefunden.")
        sys.exit(1)

    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    doc_meta = data["document"]
    fields   = data["fields"]

    print("  Rendere PDF-Seiten ...")
    page_images = render_pages()

    init_db()

    with Session(engine) as db:
        if clear:
            old = db.query(models.Document).all()
            for d in old:
                db.delete(d)
            db.commit()
            print(f"  {len(old)} altes Dokument(e) gelöscht.")

        # Dokument anlegen
        doc_row = models.Document(
            id=_uuid("d"),
            doc_no=doc_meta.get("doc_no", "scanned_batch_documentation.pdf"),
            title=doc_meta.get("title", "Scanned Batch Documentation"),
            page_count=doc_meta.get("page_count", 46),
            generated_at=doc_meta.get("generated_at"),
            status="processed",
        )
        db.add(doc_row)
        db.flush()
        print(f"  Dokument erstellt: {doc_row.id}")

        # Seiten mit Bildpfaden
        page_nos = sorted({f["page_no"] for f in fields})
        for pno in page_nos:
            db.add(models.Page(
                document_id=doc_row.id,
                page_no=pno,
                image_path=page_images.get(pno),
            ))

        # Jahreskorrektur: Ein-Ziffer-OCR-Fehler in Datumsfeldern beheben
        fields = _apply_year_corrections(fields)

        # Kuerzel-Normalisierung: OCR-Varianten (ohp/ohr/o4e) -> kanonisches Kuerzel (ohe)
        kuerzel_registry: set[str] = set()
        for fld in fields:
            # "Kürzel" / "Kuerzel" / "kürzel" -- alle Varianten abfangen
            lbl = (fld.get("label") or "").strip().lower()
            lbl_norm = lbl.replace("ü", "u").replace("ue", "u")
            if lbl_norm in ("kurzel", "kuerzel") and fld.get("value_raw"):
                kuerzel_registry.add(fld["value_raw"].strip().lower())
        if len(kuerzel_registry) >= 2:
            fields = _normalize_kuerzel_json(fields, kuerzel_registry)

        # Felder + Flags
        n_flags = 0
        block_keys: dict[str, str] = {}   # JSON hat keine Block-Keys -> gleiche Seite/Kapitel teilen einen
        for fld in fields:
            chapter = fld.get("chapter") or ""
            page_no = fld["page_no"]

            # Block-Key aus (page_no, chapter) ableiten
            bk = block_keys.get(f"{page_no}:{chapter}")
            if bk is None:
                bk = _uuid("b")
                block_keys[f"{page_no}:{chapter}"] = bk

            mf = models.Field(
                id=fld["id"],
                document_id=doc_row.id,
                chapter=chapter or None,
                block_key=bk,
                page_no=page_no,
                role=fld.get("role"),
                label_raw=fld.get("label"),
                value_raw=fld.get("value_raw") or fld.get("value"),
                value_norm=str(fld.get("value")) if fld.get("value") is not None else None,
                unit=fld.get("unit"),
                nks=fld.get("nks"),
                bbox=fld.get("bbox"),
                confidence=fld.get("confidence", 0.0),
                status=fld.get("status", "needs_review"),
                is_required=True,
            )
            db.add(mf)

            for flag in fld.get("flags", []):
                db.add(models.Flag(
                    field_id=mf.id,
                    block_key=bk,
                    severity=flag.get("severity", "error"),
                    category=flag.get("category", "unknown"),
                    code=flag.get("code", "UNKNOWN"),
                    message=flag.get("message", ""),
                    expected=flag.get("expected"),
                    actual=flag.get("actual"),
                ))
                n_flags += 1

        db.commit()

    n_err  = sum(1 for f in fields for fl in f.get("flags", []) if fl.get("severity") == "error")
    n_warn = sum(1 for f in fields for fl in f.get("flags", []) if fl.get("severity") == "warning")
    n_auto = sum(1 for f in fields if f.get("status") == "auto_accepted")
    n_rev  = sum(1 for f in fields if f.get("status") == "needs_review")

    print()
    print(f"  Geladen: {len(fields)} Felder   {n_err} Fehler   {n_warn} Warnungen")
    print(f"           {n_auto} auto-akzeptiert   {n_rev} zur Prüfung")
    print()
    print(f"  -> http://localhost:8000/api/v1/documents  (Backend muss laufen)")
    print(f"  -> http://localhost:5173                   (Frontend muss laufen)")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(
        description="Chargenprotokoll-JSON in DB laden",
        epilog="Beispiel: py load_results.py --file C:/pfad/zu/ergebnisse.json",
    )
    p.add_argument("--keep", action="store_true", help="Bestehende Dokumente nicht loeschen")
    p.add_argument("--file", metavar="JSON_PFAD",
                   help="Pfad zur extracted_fields.json (Standard: results/extracted_fields.json)")
    args = p.parse_args()

    # Erlaubt beliebige JSON-Dateien
    if args.file:
        custom = Path(args.file)
        if not custom.exists():
            print(f"[FEHLER] Datei nicht gefunden: {custom}")
            sys.exit(1)
        # Temporaer RESULTS umbiegen
        import load_results as _self
        _self.RESULTS = custom
        # PDF-Pfad aus dem JSON-Verzeichnis oder Standardpfad
        pdf_candidate = custom.parent / "scanned_batch_documentation.pdf"
        if pdf_candidate.exists():
            _self.PDF_PATH = pdf_candidate

    load(clear=not args.keep)
