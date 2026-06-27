"""BioDize Launcher — vollstaendig terminal-frei"""
import json
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.filedialog as fd
import tkinter.messagebox as mb
import urllib.request
import webbrowser
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.resolve()
ROOT        = SCRIPTS_DIR.parent
VENV_PY     = ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
VENV_PWW    = ROOT / "backend" / ".venv" / "Scripts" / "pythonw.exe"
SYS_PWW     = Path(r"C:\Temp\py313-arm64-full\pythonw.exe")

PY  = str(VENV_PY)  if VENV_PY.exists()  else sys.executable
PWW = str(VENV_PWW) if VENV_PWW.exists() \
      else str(SYS_PWW) if SYS_PWW.exists() \
      else PY.replace("python.exe", "pythonw.exe")

API_CFG = SCRIPTS_DIR / "api_keys.json"

# ── Farben ─────────────────────────────────────────────────────────────────
BG   = "#0f1117"; CARD = "#1a1d27"; TEXT = "#e2e8f0"; DIM = "#64748b"
GRN  = "#22c55e"; RED  = "#f87171"; YEL  = "#fbbf24"; BLUE = "#3b82f6"

# ── Silent subprocess helpers ──────────────────────────────────────────────
NO_WIN = subprocess.CREATE_NO_WINDOW

def silent_popen(cmd, cwd=None, env=None):
    """Startet Prozess OHNE jegliches Terminal-Fenster."""
    return subprocess.Popen(
        cmd, cwd=str(cwd) if cwd else None, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=NO_WIN,
    )

def console_popen(cmd, cwd=None):
    """Startet Prozess MIT Terminal-Fenster (fuer interaktive Tools)."""
    return subprocess.Popen(
        cmd, cwd=str(cwd) if cwd else None,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )

def api_get(path, base="http://localhost:8000"):
    try:
        with urllib.request.urlopen(base + path, timeout=3) as r:
            return json.loads(r.read())
    except Exception:
        return None

# ── Globaler Prozess-Tracker ───────────────────────────────────────────────
_procs: list[subprocess.Popen] = []
_backend: subprocess.Popen | None = None
_frontend: subprocess.Popen | None = None


# ── API Key Config ─────────────────────────────────────────────────────────

def load_api_cfg():
    if API_CFG.exists():
        try: return json.loads(API_CFG.read_text())
        except: pass
    return {"configs": []}

def save_api_cfg(cfg):
    API_CFG.write_text(json.dumps(cfg, indent=2))


# ── Haupt-App ─────────────────────────────────────────────────────────────

class App:
    def __init__(self, root: tk.Tk):
        self.root   = root
        self.status_var = tk.StringVar(value="Bereit.")
        self._build()

    def _build(self):
        root = self.root
        root.title("BioDize"); root.configure(bg=BG)
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Header
        tk.Label(root, text="BioDize", font=("Segoe UI",20,"bold"),
                 bg=BG, fg=TEXT).pack(pady=(20,0))
        tk.Label(root, text="Pharma-Chargenprotokoll Digitalisierung",
                 font=("Segoe UI",9), bg=BG, fg=DIM).pack(pady=(2,12))

        self._sep()

        # Schritt 1: App starten
        self._step(root, "1", "App starten",
                   "Backend + Frontend hochfahren",
                   "#1d4ed8","#1e40af", self._start_app)

        # Schritt 2: Daten
        row = tk.Frame(root, bg=BG); row.pack(fill="x", padx=24, pady=4)
        self._mini(row,"2a","Beispieldaten","323 Felder laden",
                   "#7c3aed","#6d28d9", self._load_default, side="left")
        self._mini(row,"2b","Andere Daten","JSON auswaehlen",
                   "#1e40af","#1e3a8a", self._load_custom, side="right")

        self._sep()

        # Schritt 3: Pruefer
        self._step(root, "3", "Pruefer oeffnen",
                   "Fehler pruefen, Scan-Bild, Korrekturen",
                   "#059669","#047857", self._open_reviewer)

        # Schritt 4: Export
        self._step(root, "4", "Als CSV exportieren",
                   "Alle Felder + Flags als CSV-Datei",
                   "#0f766e","#0d6b63", self._export_csv)

        self._sep()

        # Schritt 5: API-Vergleich
        self._step(root, "5", "API-Genauigkeit vergleichen",
                   "Verschiedene API-Keys gegen Ground Truth testen",
                   "#92400e","#78350f", self._open_compare)

        self._sep()

        # Mini-Tools
        tools = tk.Frame(root, bg=BG); tools.pack(fill="x", padx=24, pady=6)
        for label, fn in [("Debugger", self._open_debugger),
                          ("Autopatch", self._open_autopatch),
                          ("Alle bestaetigen", self._bulk_confirm)]:
            tk.Button(tools, text=label, font=("Segoe UI",8),
                      bg=CARD, fg=TEXT, activebackground="#334155",
                      relief="flat", bd=0, padx=8, pady=6,
                      cursor="hand2", command=fn,
                      takefocus=False).pack(side="left", padx=(0,6))

        self._sep()

        # Statuszeile
        tk.Label(root, textvariable=self.status_var,
                 font=("Segoe UI",8), bg=BG, fg=DIM).pack(pady=8)

        # Fenster zentrieren
        root.update_idletasks()
        W = 360; H = root.winfo_reqheight()
        sw,sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")

    def _sep(self):
        tk.Frame(self.root, bg=CARD, height=1).pack(fill="x", padx=24)

    def _step(self, parent, nr, text, desc, color, hover, cmd):
        card = tk.Frame(parent, bg=CARD)
        tk.Label(card, text=f"Schritt {nr}", font=("Segoe UI",8),
                 bg=CARD, fg=DIM).pack(anchor="w", padx=20, pady=(10,0))
        btn = tk.Button(card, text=text, font=("Segoe UI",12,"bold"),
                        bg=color, fg="white", activebackground=hover,
                        activeforeground="white", relief="flat", bd=0,
                        padx=28, pady=12, cursor="hand2",
                        command=cmd, takefocus=False)
        btn.pack(fill="x", padx=20, pady=(4,4))
        btn.bind("<Enter>", lambda e: btn.config(bg=hover))
        btn.bind("<Leave>", lambda e: btn.config(bg=color))
        tk.Label(card, text=desc, font=("Segoe UI",8), bg=CARD, fg=DIM,
                 wraplength=260, justify="center").pack(pady=(0,12))
        card.pack(fill="x", padx=24, pady=(8,4))
        return btn

    def _mini(self, parent, nr, text, desc, color, hover, cmd, side="left"):
        card = tk.Frame(parent, bg=CARD)
        tk.Label(card, text=f"Schritt {nr}", font=("Segoe UI",8),
                 bg=CARD, fg=DIM).pack(anchor="w", padx=12, pady=(8,0))
        btn = tk.Button(card, text=text, font=("Segoe UI",10,"bold"),
                        bg=color, fg="white", activebackground=hover,
                        activeforeground="white", relief="flat", bd=0,
                        padx=8, pady=9, cursor="hand2",
                        command=cmd, takefocus=False)
        btn.pack(fill="x", padx=12, pady=(3,3))
        btn.bind("<Enter>", lambda e: btn.config(bg=hover))
        btn.bind("<Leave>", lambda e: btn.config(bg=color))
        tk.Label(card, text=desc, font=("Segoe UI",8), bg=CARD, fg=DIM,
                 wraplength=120, justify="center").pack(pady=(0,8))
        pad = (0,4) if side=="left" else (4,0)
        card.pack(side="left", fill="x", expand=True, padx=pad)

    def _status(self, msg, color=None):
        self.status_var.set(msg)

    # ── Schritt 1: App starten ─────────────────────────────────────────────

    def _start_app(self):
        self._status("Starte Backend...")
        def _bg():
            global _backend, _frontend
            # Backend
            if not api_get("/health"):
                _backend = silent_popen(
                    [PY, "-m", "uvicorn", "app.main:app",
                     "--host", "127.0.0.1", "--port", "8000"],
                    cwd=ROOT / "backend")
                _procs.append(_backend)
                # Warten bis bereit
                for _ in range(30):
                    time.sleep(0.5)
                    if api_get("/health"): break
            self.root.after(0, lambda: self._status("Backend laeuft. Starte Frontend..."))
            # Frontend
            npm = "npm.cmd" if sys.platform=="win32" else "npm"
            _frontend = silent_popen(
                [npm, "run", "dev", "--", "--config", "vite.config.dev.ts"],
                cwd=ROOT / "frontend")
            _procs.append(_frontend)
            time.sleep(3)
            # Browser
            port = 5173
            for p in range(5173, 5183):
                try:
                    urllib.request.urlopen(f"http://localhost:{p}", timeout=1)
                    port = p; break
                except: pass
            self.root.after(0, lambda: (
                self._status(f"App laeuft  localhost:{port}"),
                webbrowser.open(f"http://localhost:{port}/go.html")))
        threading.Thread(target=_bg, daemon=True).start()

    # ── Schritt 2: Daten ──────────────────────────────────────────────────

    def _load_default(self):
        self._run_silent("load_results.py", "Daten laden...")

    def _load_custom(self):
        path = fd.askopenfilename(
            title="JSON auswaehlen", filetypes=[("JSON","*.json"),("Alle","*.*")],
            initialdir=str(ROOT/"results"))
        if path:
            self._run_silent(f"load_results.py --file {path}", "Importiere...")

    def _run_silent(self, script_and_args: str, msg: str):
        """Fuehrt ein Script aus OHNE Terminal, zeigt Ergebnis im Status."""
        self._status(msg)
        parts = script_and_args.split()
        cmd   = [PY, str(SCRIPTS_DIR / parts[0])] + parts[1:]
        def _bg():
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True,
                    creationflags=NO_WIN, timeout=120)
                ok = result.returncode == 0
                out = (result.stdout or result.stderr or "").strip().splitlines()
                last = out[-1] if out else ("OK" if ok else "Fehler")
                color = GRN if ok else RED
                self.root.after(0, lambda: self._status(last, color))
            except Exception as e:
                self.root.after(0, lambda: self._status(str(e)[:60], RED))
        threading.Thread(target=_bg, daemon=True).start()

    # ── Schritt 3: Pruefer ────────────────────────────────────────────────

    def _open_reviewer(self):
        silent_popen([PWW, "-B", str(SCRIPTS_DIR/"reviewer.py")])
        self._status("Pruefer geoeffnet.")

    # ── Schritt 4: Export ─────────────────────────────────────────────────

    def _export_csv(self):
        self._run_silent("export_csv.py", "Exportiere CSV...")

    # ── Schritt 5: API-Vergleich ──────────────────────────────────────────

    def _open_compare(self):
        CompareWindow(self.root)

    # ── Mini-Tools ────────────────────────────────────────────────────────

    def _open_debugger(self):
        console_popen([PY, "-B", str(SCRIPTS_DIR/"debugger.py")])

    def _open_autopatch(self):
        console_popen([PY, "-B", str(SCRIPTS_DIR/"autopatch.py")])

    def _bulk_confirm(self):
        self._run_silent("bulk_review.py --auto-confirm", "Bestaetigt alle Felder...")

    def _on_close(self):
        for p in _procs:
            try: p.terminate()
            except: pass
        self.root.destroy()


# ── API-Vergleichs-Fenster ─────────────────────────────────────────────────

class CompareWindow(tk.Toplevel):
    """Vergleicht verschiedene API-Key-Konfigurationen gegen Ground Truth."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("BioDize — API-Genauigkeitsvergleich")
        self.configure(bg=BG); self.geometry("700x560")
        self.resizable(True, True)
        self.cfg = load_api_cfg()
        self._build()

    def _build(self):
        # Header
        tk.Label(self, text="API-Konfigurationen vergleichen",
                 font=("Segoe UI",13,"bold"), bg=BG, fg=TEXT).pack(pady=(16,4))
        tk.Label(self,
                 text="Fuege API-Key-Konfigurationen hinzu und teste ihre Genauigkeit\n"
                      "gegen den Ground Truth (8 Seiten, 8 erwartete Regelverstoesse).",
                 font=("Segoe UI",9), bg=BG, fg=DIM,
                 justify="center").pack()

        # Config-Liste
        frame = tk.Frame(self, bg=CARD); frame.pack(fill="x", padx=20, pady=12)
        tk.Label(frame, text="Gespeicherte Konfigurationen",
                 font=("Segoe UI",9,"bold"), bg=CARD, fg=TEXT,
                 anchor="w").pack(fill="x", padx=12, pady=(10,4))

        self.cfg_list = tk.Listbox(frame, bg=BG, fg=TEXT,
                                   selectbackground=CARD, font=("Segoe UI",9),
                                   height=5, bd=0, highlightthickness=0)
        self.cfg_list.pack(fill="x", padx=12, pady=(0,8))
        self._refresh_list()

        # Buttons fuer Konfiguration
        btn_row = tk.Frame(frame, bg=CARD); btn_row.pack(fill="x", padx=12, pady=(0,10))
        for text, cmd in [("+ Neu", self._add_cfg),
                          ("Bearbeiten", self._edit_cfg),
                          ("Loeschen", self._del_cfg)]:
            tk.Button(btn_row, text=text, font=("Segoe UI",8),
                      bg="#334155", fg=TEXT, activebackground="#475569",
                      relief="flat", bd=0, padx=10, pady=5,
                      cursor="hand2", command=cmd,
                      takefocus=False).pack(side="left", padx=(0,6))

        # Ground Truth
        gt_frame = tk.Frame(self, bg=CARD); gt_frame.pack(fill="x", padx=20, pady=(0,8))
        tk.Label(gt_frame, text="Ground Truth Verzeichnis",
                 font=("Segoe UI",9,"bold"), bg=CARD, fg=TEXT,
                 anchor="w").pack(fill="x", padx=12, pady=(10,4))
        gt_row = tk.Frame(gt_frame, bg=CARD); gt_row.pack(fill="x", padx=12, pady=(0,10))
        self.gt_var = tk.StringVar(value=str(ROOT/"ground_truth"))
        tk.Entry(gt_row, textvariable=self.gt_var,
                 bg=BG, fg=TEXT, insertbackground=TEXT,
                 font=("Segoe UI",9), relief="flat", bd=4).pack(side="left", fill="x", expand=True)
        tk.Button(gt_row, text="...", font=("Segoe UI",9),
                  bg="#334155", fg=TEXT, relief="flat", bd=0,
                  padx=8, pady=4, cursor="hand2",
                  command=self._browse_gt,
                  takefocus=False).pack(side="left", padx=(6,0))

        # Vergleich starten
        self.btn_run = tk.Button(self, text="Vergleich starten",
                                 font=("Segoe UI",11,"bold"),
                                 bg="#7c3aed", fg="white",
                                 activebackground="#6d28d9",
                                 relief="flat", bd=0, padx=20, pady=12,
                                 cursor="hand2", command=self._run_compare,
                                 takefocus=False)
        self.btn_run.pack(pady=(0,8))

        # Ergebnis-Tabelle
        res_frame = tk.Frame(self, bg=CARD); res_frame.pack(fill="both", expand=True, padx=20, pady=(0,16))
        tk.Label(res_frame, text="Ergebnisse",
                 font=("Segoe UI",9,"bold"), bg=CARD, fg=TEXT,
                 anchor="w").pack(fill="x", padx=12, pady=(10,4))

        self.results_text = tk.Text(res_frame, bg=BG, fg=TEXT,
                                    font=("Consolas",9), relief="flat",
                                    bd=0, height=10, state="disabled",
                                    wrap="none")
        sb = tk.Scrollbar(res_frame, command=self.results_text.yview, bg=CARD)
        self.results_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.results_text.pack(fill="both", expand=True, padx=(12,0), pady=(0,12))

        self._show_result("Konfigurationen hinzufuegen und 'Vergleich starten' klicken.\n\n"
                          "Ohne API-Keys wird der gespeicherte Ground-Truth-Lauf verwendet\n"
                          "(keine echte Extraktion notwendig).")

    def _refresh_list(self):
        self.cfg_list.delete(0, "end")
        for i, c in enumerate(self.cfg.get("configs", [])):
            name    = c.get("name", f"Config {i+1}")
            extractor = c.get("extractor","stub")
            ocr     = c.get("ocr_engine","stub")
            self.cfg_list.insert("end", f"  {name}   [{extractor} + {ocr}]")

    def _add_cfg(self):
        ConfigDialog(self, None, self._on_cfg_saved)

    def _edit_cfg(self):
        sel = self.cfg_list.curselection()
        if not sel: return
        ConfigDialog(self, self.cfg["configs"][sel[0]], self._on_cfg_saved, sel[0])

    def _del_cfg(self):
        sel = self.cfg_list.curselection()
        if not sel: return
        self.cfg["configs"].pop(sel[0])
        save_api_cfg(self.cfg); self._refresh_list()

    def _on_cfg_saved(self, config, idx=None):
        if idx is None:
            self.cfg.setdefault("configs", []).append(config)
        else:
            self.cfg["configs"][idx] = config
        save_api_cfg(self.cfg); self._refresh_list()

    def _browse_gt(self):
        d = fd.askdirectory(title="Ground-Truth-Verzeichnis auswaehlen",
                            initialdir=self.gt_var.get())
        if d: self.gt_var.set(d)

    def _show_result(self, text):
        self.results_text.configure(state="normal")
        self.results_text.delete("1.0", "end")
        self.results_text.insert("end", text)
        self.results_text.configure(state="disabled")

    def _run_compare(self):
        gt_dir = Path(self.gt_var.get())
        if not gt_dir.exists():
            mb.showerror("Fehler", f"Ground-Truth-Verzeichnis nicht gefunden:\n{gt_dir}")
            return

        configs = self.cfg.get("configs", [])
        # Immer auch den Baseline-Run (gespeicherte Ergebnisse) hinzufuegen
        runs = [{"name": "Baseline (gespeicherte Ergebnisse)",
                 "extractor":"stub","ocr_engine":"stub",
                 "openai_api_key":"","mistral_api_key":""}] + configs

        self.btn_run.config(state="disabled", text="Laeuft...")
        self._show_result("Vergleich laeuft... (kann etwas dauern)")

        def _bg():
            lines = []
            hdr = f"{'Konfiguration':<32} {'Prec':>6} {'Rec':>6} {'F1':>6} {'ValAcc':>7} {'SigAcc':>7}"
            lines.append(hdr)
            lines.append("-" * len(hdr))

            for run in runs:
                try:
                    result = self._score_run(run, gt_dir)
                    a = result.get("aggregate", {})
                    lines.append(
                        f"{run['name'][:31]:<32}"
                        f" {a.get('rule_precision',0):>5.0%}"
                        f" {a.get('rule_recall',0):>6.0%}"
                        f" {a.get('rule_f1',0):>6.0%}"
                        f" {(a.get('value_acc') or 0):>7.0%}"
                        f" {(a.get('signature_acc') or 0):>7.0%}"
                    )
                    # Detailzeilen
                    for p in result.get("pages",[]):
                        if p.get("fn") or p.get("fp"):
                            fn = p.get("fn",[]); fp = p.get("fp",[])
                            det = []
                            if fn: det.append(f"FN:{fn}")
                            if fp: det.append(f"FP:{fp}")
                            lines.append(f"  p{p['page']:02d}: {' '.join(det)}")
                except Exception as e:
                    lines.append(f"{run['name'][:31]:<32}  FEHLER: {e}")

            self.root.after(0, lambda: (
                self._show_result("\n".join(lines)),
                self.btn_run.config(state="normal", text="Vergleich starten")))

        threading.Thread(target=_bg, daemon=True).start()

    def _score_run(self, run: dict, gt_dir: Path) -> dict:
        """Fuehrt Pipeline aus und bewertet gegen Ground Truth."""
        import os, json as _json
        sys.path.insert(0, str(ROOT/"backend"))
        os.chdir(str(ROOT/"backend"))

        from app.pipeline.model import Block, BBox, Document, Field, Read
        from app.pipeline.normalize import normalize
        from app.pipeline.resolve import resolve
        from app.pipeline.validate.engine import validate
        from app.pipeline.validate.uncertainty import score
        from app.evaluation.scorer import score_ground_truth

        results_json = ROOT / "results" / "extracted_fields.json"
        if not results_json.exists():
            raise FileNotFoundError("results/extracted_fields.json nicht gefunden.")

        data    = _json.loads(results_json.read_text(encoding="utf-8"))
        entries = data["fields"]
        doc     = Document(doc_no="eval", title="eval", page_count=46)
        bmap: dict = {}
        for e in entries:
            chap = (e.get("chapter") or "").strip(); pno = e["page_no"]
            key  = (chap, pno)
            if key not in bmap:
                bmap[key] = Block(chapter=chap, page_no=pno, template="real")
            b = bmap[key]
            bbox_raw = e.get("bbox")
            bbox = BBox(*bbox_raw) if bbox_raw and len(bbox_raw)==4 else None
            vr   = str(e.get("value_raw") or e.get("value") or "")
            f    = Field(page_no=pno, chapter=chap, role=e.get("role"),
                         label_raw=e.get("label") or "", value_raw=vr, bbox=bbox)
            f.reads = [Read(model="eval", value_raw=vr,
                            confidence=e.get("confidence", 1.0))]
            b.fields.append(f); f.block_key = b.key
        doc.blocks = list(bmap.values())

        normalize(doc); resolve(doc); validate(doc); score(doc)
        report = score_ground_truth(doc, gt_dir)
        return report.as_dict()


# ── Config-Dialog ─────────────────────────────────────────────────────────

class ConfigDialog(tk.Toplevel):
    def __init__(self, parent, config, on_save, idx=None):
        super().__init__(parent)
        self.title("API-Konfiguration")
        self.configure(bg=BG); self.resizable(False,False); self.grab_set()
        self._on_save = on_save; self._idx = idx
        self._cfg = dict(config) if config else {}
        self._build()

    def _build(self):
        tk.Label(self, text="API-Konfiguration",
                 font=("Segoe UI",12,"bold"), bg=BG, fg=TEXT).pack(pady=(16,4))

        grid = tk.Frame(self, bg=BG); grid.pack(padx=24, pady=8)

        fields = [
            ("Name",              "name",            "Mein Modell"),
            ("Extractor",         "extractor",       "openai  (oder stub)"),
            ("OCR Engine",        "ocr_engine",      "mistral  (oder stub)"),
            ("OpenAI API Key",    "openai_api_key",  "sk-..."),
            ("OpenAI Model",      "openai_model",    "gpt-4o"),
            ("Mistral API Key",   "mistral_api_key", "..."),
            ("OpenAI Base URL",   "openai_base_url", "(leer = standard)"),
        ]

        self._vars = {}
        for row,(label, key, placeholder) in enumerate(fields):
            tk.Label(grid, text=label+":", font=("Segoe UI",9), bg=BG,
                     fg=DIM, anchor="w", width=18).grid(row=row,column=0,sticky="w",pady=3)
            v = tk.StringVar(value=self._cfg.get(key,""))
            is_key = "key" in key.lower()
            e = tk.Entry(grid, textvariable=v, font=("Segoe UI",9),
                         bg=CARD, fg=TEXT, insertbackground=TEXT,
                         relief="flat", bd=4, width=36,
                         show="*" if is_key else "")
            e.grid(row=row, column=1, pady=3, padx=(8,0))
            if not v.get() and placeholder:
                e.insert(0, placeholder)
                e.config(fg=DIM)
                def _focus_in(event, entry=e, ph=placeholder, var=v):
                    if entry.get() == ph: entry.delete(0,"end"); entry.config(fg=TEXT)
                def _focus_out(event, entry=e, ph=placeholder, var=v):
                    if not entry.get(): entry.insert(0,ph); entry.config(fg=DIM)
                e.bind("<FocusIn>",  _focus_in)
                e.bind("<FocusOut>", _focus_out)
            self._vars[key] = (v, placeholder)

        bar = tk.Frame(self,bg=BG); bar.pack(pady=16)
        tk.Button(bar,text="Speichern",bg="#166534",fg="white",
                  relief="flat",bd=0,padx=14,pady=8,cursor="hand2",
                  font=("Segoe UI",10,"bold"),command=self._save,
                  takefocus=False).pack(side="left",padx=8)
        tk.Button(bar,text="Abbrechen",bg=CARD,fg=DIM,
                  relief="flat",bd=0,padx=14,pady=8,cursor="hand2",
                  font=("Segoe UI",10),command=self.destroy,
                  takefocus=False).pack(side="left",padx=8)

    def _save(self):
        cfg = {}
        for key,(var,ph) in self._vars.items():
            v = var.get()
            cfg[key] = "" if v == ph else v
        self._on_save(cfg, self._idx)
        self.destroy()


# ── Start ─────────────────────────────────────────────────────────────────

root = tk.Tk()
App(root)
root.mainloop()
