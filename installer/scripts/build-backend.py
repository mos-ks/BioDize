"""Freeze the BioDize FastAPI backend with PyInstaller.

Run from any directory — paths are resolved relative to the repo root.

Usage:
  python installer/scripts/build-backend.py

Output:
  dist-backend/biodize-backend/          (PyInstaller onedir bundle)
    biodize-backend[.exe]                (main executable)
    *.so / *.dll / ...                   (shared libraries)

The script:
  1. Detects platform / architecture.
  2. Installs backend requirements (swaps PyMuPDF -> pypdfium2 on ARM64 Windows
     and uvicorn[standard] -> uvicorn on ARM64 Windows, since httptools has no
     ARM64 Windows wheel).
  3. Installs PyInstaller.
  4. Runs PyInstaller with hidden imports for FastAPI / uvicorn / SQLAlchemy.
  5. Moves output to <repo-root>/dist-backend/.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
THIS   = Path(__file__).resolve()
REPO   = THIS.parent.parent.parent          # .../biodize/
BACKEND = REPO / "backend"
ENTRY   = THIS.parent / "backend-entry.py"
OUT_DIR = REPO / "dist-backend"
WORK    = REPO / ".pyinstaller-work"
SPEC    = REPO / ".pyinstaller-spec"

# ── Platform detection ────────────────────────────────────────────────────────
IS_WIN   = sys.platform == "win32"
IS_ARM64 = platform.machine().lower() in ("arm64", "aarch64")
IS_WIN_ARM64 = IS_WIN and IS_ARM64

print(f"[build-backend] platform={sys.platform}  arch={platform.machine()}")
print(f"[build-backend] ARM64 Windows mode: {IS_WIN_ARM64}")

# ── Collect requirements ──────────────────────────────────────────────────────
SKIP_PREFIXES = ("mistralai", "openai", "pytest", "httpx")

raw_reqs: list[str] = []
with open(BACKEND / "requirements.txt") as fh:
    for line in fh:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pkg = line.split("#")[0].strip()
        if any(pkg.lower().startswith(s) for s in SKIP_PREFIXES):
            continue
        raw_reqs.append(pkg)

final_reqs: list[str] = []
added_pdfium = False

for req in raw_reqs:
    low = req.lower()

    if "pymupdf" in low:
        if IS_WIN_ARM64:
            print(f"  [ARM64-win] swap  {req!r} -> pypdfium2 Pillow")
            if not added_pdfium:
                final_reqs += ["pypdfium2", "Pillow"]
                added_pdfium = True
        else:
            final_reqs.append(req)
        continue

    if "uvicorn[standard]" in low:
        if IS_WIN_ARM64:
            print(f"  [ARM64-win] swap  {req!r} -> uvicorn  (httptools has no ARM64 wheel)")
            final_reqs.append("uvicorn")
        else:
            final_reqs.append(req)
        continue

    final_reqs.append(req)

# ── Install ───────────────────────────────────────────────────────────────────
print(f"\n[build-backend] Installing {len(final_reqs)} packages + pyinstaller...")
subprocess.run(
    [sys.executable, "-m", "pip", "install", "--upgrade"] + final_reqs + ["pyinstaller"],
    check=True,
)

# ── PyInstaller ───────────────────────────────────────────────────────────────
print("\n[build-backend] Running PyInstaller...")

# Clean previous output so a fresh bundle is always produced.
for d in (OUT_DIR, WORK, SPEC):
    if d.exists():
        shutil.rmtree(d)

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--name",         "biodize-backend",
    "--noconfirm",
    "--onedir",
    "--distpath",     str(OUT_DIR),
    "--workpath",     str(WORK),
    "--specpath",     str(SPEC),
    # Collect entire packages so sub-modules / plugins aren't missed.
    "--collect-all",  "fastapi",
    "--collect-all",  "starlette",
    "--collect-all",  "uvicorn",
    "--collect-all",  "pydantic",
    "--collect-all",  "pydantic_settings",
    "--collect-all",  "sqlalchemy",
    "--collect-all",  "app",
    # uvicorn internal modules that importlib can't see statically.
    "--hidden-import", "uvicorn.logging",
    "--hidden-import", "uvicorn.loops",
    "--hidden-import", "uvicorn.loops.auto",
    "--hidden-import", "uvicorn.protocols",
    "--hidden-import", "uvicorn.protocols.http",
    "--hidden-import", "uvicorn.protocols.http.auto",
    "--hidden-import", "uvicorn.protocols.websockets",
    "--hidden-import", "uvicorn.protocols.websockets.auto",
    "--hidden-import", "uvicorn.lifespan",
    "--hidden-import", "uvicorn.lifespan.on",
    "--hidden-import", "uvicorn.middleware",
    "--hidden-import", "uvicorn.middleware.proxy_headers",
    # Standard library modules sometimes missed in frozen builds.
    "--hidden-import", "email.mime.text",
    "--hidden-import", "email.mime.multipart",
    "--hidden-import", "multiprocessing.spawn",
    "--hidden-import", "sqlite3",
    str(ENTRY),
]

subprocess.run(cmd, check=True, cwd=str(BACKEND))

# ── Verify output ─────────────────────────────────────────────────────────────
bundle = OUT_DIR / "biodize-backend"
ext    = ".exe" if IS_WIN else ""
exe    = bundle / f"biodize-backend{ext}"

if not exe.exists():
    sys.exit(f"[build-backend] ERROR: expected executable not found: {exe}")

print(f"\n[build-backend] SUCCESS")
print(f"  bundle  : {bundle}")
print(f"  exe     : {exe}  ({exe.stat().st_size // 1024 // 1024} MB)")
