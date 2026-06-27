"""CSV export -- runs silently, opens file in Explorer."""
import sys, os, subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
VENV_PY = ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
if VENV_PY.exists() and Path(sys.executable).resolve() != VENV_PY.resolve():
    sys.exit(subprocess.run([str(VENV_PY)] + sys.argv).returncode)

sys.path.insert(0, str(ROOT / "backend"))
os.chdir(str(ROOT / "backend"))

from sqlalchemy.orm import Session
from app.db.base import engine
from app.db import models
from app.pipeline.export import export_csv

with Session(engine) as db:
    doc = db.query(models.Document).first()
    if not doc:
        print("No document in DB.")
        sys.exit(1)
    safe = (doc.doc_no or doc.id).replace("/","_").replace(" ","_")
    data = export_csv(doc.id, db)

out = ROOT / f"Chargenprotokoll_{safe}.csv"
with open(out, "wb") as f:
    f.write(data)

print(f"Exported: {out}")
subprocess.Popen(["explorer", str(out)], shell=True,
                 creationflags=0x08000000)
