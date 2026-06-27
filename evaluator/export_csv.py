"""CSV-Export via API speichern und oeffnen."""
import sys, os, subprocess, urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()  # evaluator/ -> repo root
VENV_PY = ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
if VENV_PY.exists() and Path(sys.executable).resolve() != VENV_PY.resolve():
    sys.exit(subprocess.run([str(VENV_PY)] + sys.argv).returncode)

sys.path.insert(0, str(ROOT / "backend"))
os.chdir(str(ROOT / "backend"))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

try:
    from sqlalchemy.orm import Session
    from app.db.base import engine
    from app.db import models
    from app.pipeline.export import export_csv

    with Session(engine) as db:
        doc = db.query(models.Document).first()
        if not doc:
            print("Kein Dokument in DB. Bitte zuerst 'Beispieldaten' laden.")
            input("Enter zum Schliessen...")
            sys.exit(1)
        safe = (doc.doc_no or doc.id).replace("/","_").replace(" ","_")
        data = export_csv(doc.id, db)

    out = ROOT / f"Chargenprotokoll_{safe}.csv"
    with open(out, "wb") as f:
        f.write(data)

    print(f"Exportiert: {out}")
    print(f"Felder: {data.count(b';') // 14} Zeilen (ca.)")
    print()
    print("Datei wird geoeffnet...")
    subprocess.Popen(["explorer", str(out)], shell=True)

except Exception as e:
    print(f"Fehler: {e}")

input("\nEnter zum Schliessen...")
