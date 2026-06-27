"""
BioDize Desktop Launcher
========================
Setzt Backend (FastAPI) und Frontend (Vite) auf und startet beide Server.
Kein Docker nötig - läuft komplett lokal.

Starten:  py start.py   ODER  Doppelklick auf BioDize.bat
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
import threading
import webbrowser
from pathlib import Path

# ---------------------------------------------------------------------------
# Pfade
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.parent.resolve()  # evaluator/ -> repo root
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
VENV_DIR = BACKEND_DIR / ".venv"

BACKEND_PORT = 8000
FRONTEND_PORT = 5173
FRONTEND_URL = f"http://localhost:{FRONTEND_PORT}"
BACKEND_URL = f"http://localhost:{BACKEND_PORT}"

IS_WINDOWS = sys.platform == "win32"

# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def banner(msg: str) -> None:
    width = 60
    print("\n" + "=" * width)
    print(f"  {msg}")
    print("=" * width)


def info(msg: str) -> None:
    print(f"  [BioDize] {msg}")


def warn(msg: str) -> None:
    print(f"  [WARN]    {msg}", file=sys.stderr)


def abort(msg: str) -> None:
    print(f"\n  [FEHLER]  {msg}", file=sys.stderr)
    input("\n  Enter drücken zum Schließen...")
    sys.exit(1)


def find_py() -> str:
    """Gibt den Python-Interpreter zurück, der für diesen Prozess verwendet wird."""
    return sys.executable


def venv_python() -> str:
    if IS_WINDOWS:
        return str(VENV_DIR / "Scripts" / "python.exe")
    return str(VENV_DIR / "bin" / "python")


def venv_pip() -> str:
    if IS_WINDOWS:
        return str(VENV_DIR / "Scripts" / "pip.exe")
    return str(VENV_DIR / "bin" / "pip")


def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None,
        shell: bool | None = None) -> int:
    """Führt Befehl aus und gibt Exit-Code zurück. Gibt Ausgabe direkt weiter."""
    use_shell = IS_WINDOWS if shell is None else shell
    result = subprocess.run(cmd, cwd=str(cwd) if cwd else None, env=env, shell=use_shell)
    return result.returncode


def check_node() -> None:
    if not shutil.which("node"):
        abort("Node.js nicht gefunden. Bitte von https://nodejs.org installieren.")
    if not shutil.which("npm"):
        abort("npm nicht gefunden. Mit Node.js sollte npm enthalten sein.")
    info("Node.js und npm gefunden.")


# ---------------------------------------------------------------------------
# Auto-Update via Git
# ---------------------------------------------------------------------------

def _git(*args: str, cwd: Path = ROOT) -> tuple[int, str]:
    """git-Befehl ausführen, gibt (returncode, stdout+stderr) zurück."""
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    return result.returncode, (result.stdout + result.stderr).strip()


def auto_update() -> None:
    """
    Prüft ob es neue Commits auf GitHub gibt und führt git pull aus.
    Schlägt netzwerk- oder git-Fehler still fehl - startet trotzdem.
    """
    if not shutil.which("git"):
        warn("git nicht gefunden - automatische Updates übersprungen.")
        return

    # Sicherstellen, dass das Verzeichnis ein Git-Repo ist
    rc, _ = _git("rev-parse", "--git-dir")
    if rc != 0:
        warn("Kein Git-Repository - automatische Updates übersprungen.")
        return

    info("Prüfe auf Updates von GitHub ...")

    # Lokalen HEAD merken
    _, local_sha = _git("rev-parse", "HEAD")

    # Remote abrufen (Timeout durch git selbst, max 30 s)
    rc, out = _git("fetch", "--quiet", "origin")
    if rc != 0:
        warn(f"git fetch fehlgeschlagen (kein Internet?) - starte mit lokaler Version.\n  {out}")
        return

    # Remote-HEAD des aktuellen Branches ermitteln
    _, branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    _, remote_sha = _git("rev-parse", f"origin/{branch}")

    if local_sha == remote_sha:
        info("Bereits aktuell.")
        return

    # Neue Commits vorhanden -> anzeigen was kommt
    _, log = _git("log", "--oneline", f"HEAD..origin/{branch}")
    print()
    print("  Neue Commits auf GitHub:")
    for line in log.splitlines():
        print(f"    + {line}")
    print()

    # Lokale ungespeicherte Änderungen prüfen.
    # Nur *verfolgte* geänderte Dateien blockieren den Pull (kein "??").
    # .env, .db, __pycache__, results/ sind immer harmlos.
    _IGNORE_SUFFIXES = (".env", ".db", ".pyc")
    _IGNORE_PARTS    = {"__pycache__", "results", ".venv", "node_modules", "var"}
    _, dirty = _git("status", "--porcelain")
    local_edits = set()
    for ln in dirty.splitlines():
        if len(ln) < 4:
            continue
        xy, path = ln[:2], ln[3:].strip()
        # "??" = untracked -> kein Problem für pull
        if xy.strip() == "??":
            continue
        if any(path.endswith(s) for s in _IGNORE_SUFFIXES):
            continue
        if any(part in path.split("/") for part in _IGNORE_PARTS):
            continue
        local_edits.add(path)
    if local_edits:
        warn(
            "Lokale Änderungen vorhanden - git pull wird übersprungen um Datenverlust zu vermeiden:\n"
            + "".join(f"    {f}\n" for f in sorted(local_edits))
            + "  Führe 'git stash' aus um sie temporär zu sichern."
        )
        return

    # Pull durchführen
    info(f"Führe git pull origin {branch} aus ...")
    rc, out = _git("pull", "--ff-only", "origin", branch)
    if rc != 0:
        warn(f"git pull fehlgeschlagen - starte mit lokaler Version.\n  {out}")
        return

    info(f"Update erfolgreich. ({local_sha[:7]} -> {remote_sha[:7]})")

    # Sentinels löschen damit pip/npm bei geänderten Abhängigkeiten neu installieren
    for sentinel in [
        VENV_DIR / ".installed_stamp",
        FRONTEND_DIR / "node_modules" / ".install_stamp",
    ]:
        if sentinel.exists():
            sentinel.unlink()
            info(f"  Abhängigkeits-Sentinel zurückgesetzt: {sentinel.name}")


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def setup_backend_env() -> None:
    env_file = BACKEND_DIR / ".env"
    env_example = BACKEND_DIR / ".env.example"
    if not env_file.exists():
        if env_example.exists():
            shutil.copy(env_example, env_file)
            info(".env aus .env.example erstellt (Stub-Modus, keine API-Keys nötig).")
        else:
            env_file.write_text(
                "EXTRACTOR=stub\n"
                "OCR_ENGINE=stub\n"
                "DATABASE_URL=sqlite:///./biodize.db\n"
                "STORAGE_DIR=./var\n"
                "RENDER_DPI=200\n"
                "AUTO_ACCEPT_THRESHOLD=0.9\n"
                "VERIFICATION_POLICY=confidence_gated\n",
                encoding="utf-8",
            )
            info(".env mit Standard-Stub-Werten erstellt.")
    else:
        info(".env bereits vorhanden.")


def setup_frontend_env() -> None:
    env_file = FRONTEND_DIR / ".env"
    needed = f"VITE_API_BASE={BACKEND_URL}\n"
    if not env_file.exists():
        env_file.write_text(needed, encoding="utf-8")
        info(f"frontend/.env erstellt -> VITE_API_BASE={BACKEND_URL}")
    else:
        content = env_file.read_text(encoding="utf-8")
        if "VITE_API_BASE" not in content:
            env_file.write_text(needed + content, encoding="utf-8")
            info(f"VITE_API_BASE={BACKEND_URL} in frontend/.env eingetragen.")
        else:
            # Überschreibe den Wert auf localhost
            import re
            new_content = re.sub(
                r"VITE_API_BASE=.*",
                f"VITE_API_BASE={BACKEND_URL}",
                content,
            )
            if new_content != content:
                env_file.write_text(new_content, encoding="utf-8")
                info(f"VITE_API_BASE auf {BACKEND_URL} aktualisiert.")
            else:
                info("frontend/.env bereits auf localhost gesetzt.")


def setup_venv() -> None:
    if not VENV_DIR.exists():
        info("Erstelle Python-Virtualenv ...")
        rc = run([find_py(), "-m", "venv", str(VENV_DIR)], shell=False)
        if rc != 0:
            abort("Virtualenv konnte nicht erstellt werden.")
        info("Virtualenv erstellt.")
    else:
        info("Virtualenv bereits vorhanden.")


def install_backend_deps() -> None:
    req = BACKEND_DIR / "requirements.txt"
    if not req.exists():
        warn("requirements.txt nicht gefunden - überspringe pip install.")
        return
    # Wenn bereits installiert (Sentinel vorhanden), nur neu installieren
    # wenn sich requirements.txt geändert hat.
    sentinel = VENV_DIR / ".installed_stamp"
    req_mtime = req.stat().st_mtime
    if sentinel.exists() and sentinel.stat().st_mtime >= req_mtime:
        info("Python-Abhängigkeiten bereits aktuell.")
        return

    # ARM64-Windows: keine Build-Tools -> nur pure-Python / Binary-Wheels.
    # PyMuPDF: kein ARM64-Wheel (stub-Modus braucht es nicht).
    # uvicorn[standard]: enthält httptools (C-Ext) -> auf uvicorn ohne Extras reduzieren.
    lines = req.read_text(encoding="utf-8").splitlines()
    filtered = []
    for l in lines:
        stripped = l.strip()
        if stripped.startswith("PyMuPDF"):
            continue
        # uvicorn[standard] -> uvicorn (httptools benötigt Visual C++)
        l = l.replace("uvicorn[standard]", "uvicorn")
        filtered.append(l)
    tmp_req = BACKEND_DIR / "_requirements_no_pymupdf.txt"
    tmp_req.write_text("\n".join(filtered) + "\n", encoding="utf-8")

    info("Installiere Python-Abhängigkeiten ...")
    # --only-binary :all: vermeidet C-Ext-Builds (kein MSVC auf ARM64 nötig)
    rc = run(
        [venv_pip(), "install", "-r", str(tmp_req), "--only-binary", ":all:"],
        cwd=BACKEND_DIR,
        shell=False,
    )
    tmp_req.unlink(missing_ok=True)
    if rc != 0:
        abort("pip install ist fehlgeschlagen.")

    # PDF-Renderer: pypdfium2 + Pillow (ARM64-kompatibel, ersetzt PyMuPDF)
    info("Installiere PDF-Renderer (pypdfium2 + Pillow) ...")
    pdf_rc = run(
        [venv_pip(), "install", "pypdfium2", "Pillow", "--only-binary", ":all:", "--quiet"],
        cwd=BACKEND_DIR,
        shell=False,
    )
    if pdf_rc != 0:
        warn("pypdfium2/Pillow konnte nicht installiert werden - PDF-Seitenansicht nicht verfügbar.")
    else:
        info("PDF-Renderer installiert.")

    # PyMuPDF zusätzlich versuchen (falls doch ein Wheel existiert, z.B. x64)
    run(
        [venv_pip(), "install", "PyMuPDF>=1.24", "--only-binary", ":all:", "--quiet"],
        cwd=BACKEND_DIR,
        shell=False,
    )

    # Sentinel setzen damit beim nächsten Start kein reinstall nötig ist
    sentinel.touch()
    info("Python-Abhängigkeiten installiert.")


def setup_vite_dev_config() -> None:
    """Erstellt vite.config.dev.ts ohne Cloudflare-Plugin (kein ARM64-Binary).
    Wird nie von git pull überschrieben da untracked."""
    cfg = FRONTEND_DIR / "vite.config.dev.ts"
    if cfg.exists():
        return
    cfg.write_text(
        'import { defineConfig } from "vite";\n'
        'import react from "@vitejs/plugin-react";\n'
        '\n'
        '// Lokale Dev-Config ohne @cloudflare/vite-plugin (kein ARM64-Windows-Binary).\n'
        '// Diese Datei wird vom Launcher erzeugt und nicht ins Git eingecheckt.\n'
        'export default defineConfig({\n'
        '  plugins: [react()],\n'
        '  server: { port: 5173, host: true },\n'
        '  preview: { port: 4173, host: true },\n'
        '  build: { outDir: "dist", sourcemap: false },\n'
        '});\n',
        encoding="utf-8",
    )
    info("vite.config.dev.ts erstellt (ohne Cloudflare-Plugin).")


def install_frontend_deps() -> None:
    nm = FRONTEND_DIR / "node_modules"
    pkg = FRONTEND_DIR / "package.json"
    stamp = FRONTEND_DIR / "node_modules" / ".install_stamp"
    pkg_mtime = pkg.stat().st_mtime if pkg.exists() else 0
    if nm.exists() and stamp.exists() and stamp.stat().st_mtime >= pkg_mtime:
        info("npm-Pakete bereits aktuell.")
        return
    info("Installiere npm-Pakete (einmalig, dauert kurz) ...")
    # --ignore-scripts: überspringt wrangler/workerd Binary-Download (kein ARM64-Wheel).
    # Für lokales `npm run dev` wird wrangler nicht benötigt.
    rc = run(["npm", "install", "--ignore-scripts"], cwd=FRONTEND_DIR)
    if rc != 0:
        abort("npm install ist fehlgeschlagen.")
    stamp.touch()
    info("npm-Pakete installiert.")


# ---------------------------------------------------------------------------
# Prozesse starten
# ---------------------------------------------------------------------------

def start_backend() -> subprocess.Popen:
    info(f"Starte Backend auf {BACKEND_URL} ...")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        [
            venv_python(),
            "-m", "uvicorn",
            "app.main:app",
            "--host", "127.0.0.1",
            "--port", str(BACKEND_PORT),
            "--reload",
        ],
        cwd=str(BACKEND_DIR),
        env=env,
    )
    return proc


def start_frontend() -> subprocess.Popen:
    info(f"Starte Frontend auf {FRONTEND_URL} ...")
    env = os.environ.copy()
    # vite.config.dev.ts vermeidet den @cloudflare/vite-plugin (kein ARM64-Binary)
    proc = subprocess.Popen(
        ["npm", "run", "dev", "--", "--config", "vite.config.dev.ts"],
        cwd=str(FRONTEND_DIR),
        env=env,
        shell=IS_WINDOWS,
    )
    return proc


def _detect_vite_port(timeout: float = 15.0) -> int:
    """Wartet bis Vite bereit ist und gibt den tatsächlichen Port zurück."""
    deadline = time.time() + timeout
    for port in range(FRONTEND_PORT, FRONTEND_PORT + 10):
        while time.time() < deadline:
            try:
                import urllib.request
                urllib.request.urlopen(f"http://localhost:{port}", timeout=1)
                return port
            except Exception:
                time.sleep(0.3)
    return FRONTEND_PORT


def open_browser_delayed(delay: float = 3.0) -> None:
    def _open():
        time.sleep(delay)
        port = _detect_vite_port()
        url = f"http://localhost:{port}"
        info(f"Browser wird geoeffnet -> {url}/go.html")
        webbrowser.open(f"{url}/go.html")
    t = threading.Thread(target=_open, daemon=True)
    t.start()


def wait_and_cleanup(procs: list[subprocess.Popen]) -> None:
    info("Beide Server laufen. Strg+C zum Beenden.")
    try:
        while True:
            time.sleep(1)
            for p in procs:
                if p.poll() is not None:
                    info(f"Prozess {p.pid} hat sich unerwartet beendet (Code {p.returncode}).")
    except KeyboardInterrupt:
        banner("Beende BioDize ...")
        for p in procs:
            try:
                if IS_WINDOWS:
                    subprocess.call(
                        ["taskkill", "/F", "/T", "/PID", str(p.pid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    os.killpg(os.getpgid(p.pid), signal.SIGTERM)
            except Exception:
                p.terminate()
        info("Fertig.")


# ---------------------------------------------------------------------------
# Hauptprogramm
# ---------------------------------------------------------------------------

def main() -> None:
    banner("BioDize  -  Lokaler Starter")
    print(f"\n  Verzeichnis: {ROOT}")
    print(f"  Backend:     {BACKEND_URL}")
    print(f"  Frontend:    {FRONTEND_URL}")
    print(f"  API-Docs:    {BACKEND_URL}/docs\n")

    banner("0 / 4  Update prüfen")
    auto_update()

    check_node()

    banner("1 / 4  Backend einrichten")
    setup_backend_env()
    setup_venv()
    install_backend_deps()

    banner("2 / 4  Frontend einrichten")
    setup_frontend_env()
    setup_vite_dev_config()
    install_frontend_deps()

    banner("3 / 4  Server starten")
    backend_proc = start_backend()
    time.sleep(1)          # kurz warten, damit uvicorn Port belegt
    frontend_proc = start_frontend()

    banner("4 / 4  Browser öffnen")
    open_browser_delayed(delay=5.0)

    wait_and_cleanup([backend_proc, frontend_proc])


if __name__ == "__main__":
    main()
