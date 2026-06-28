"""
BioDize Eval -- Standalone Batch Review Tool
=============================================
Auto-starts backend. No manual setup needed.
For multiple batches: use document dropdown top-left.

Start: py reviewer.py
       Double-click BioDize Launcher.bat -> Step 3
"""
from __future__ import annotations
import json, os, subprocess, sys, threading, time
from io import BytesIO
from pathlib import Path
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.messagebox as mb
import tkinter.simpledialog as sd
import urllib.request, urllib.error

ROOT = Path(__file__).parent.parent.resolve()  # evaluator/ -> repo root
VENV_PY = ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
if VENV_PY.exists() and Path(sys.executable).resolve() != VENV_PY.resolve():
    sys.exit(subprocess.run([str(VENV_PY)] + sys.argv).returncode)

try:
    from PIL import Image, ImageTk
except ImportError:
    subprocess.run([str(VENV_PY), "-m", "pip", "install", "Pillow", "--quiet"])
    from PIL import Image, ImageTk

BASE = "http://localhost:8000"
KEYS_FILE = ROOT / "reviewer_keys.json"

DEFAULT_KEYS = {
    "confirm":  "<Return>",
    "correct":  "<e>",
    "next":     "<space>",
    "prev":     "<BackSpace>",
    "filter_flags": "<f>",
    "filter_all":   "<a>",
}

# ── Farben ────────────────────────────────────────────────────────────────────
C = dict(
    bg="#111827", side="#1f2937", hdr="#0d1117",
    sel="#1e3a5f", err="#450a0a", wrn="#422006", ok="#052e16",
    fg="#f1f5f9", dim="#6b7280",
    red="#f87171", yel="#fbbf24", grn="#4ade80", blue="#60a5fa",
)

# ── Error descriptions ────────────────────────────────────────────────────────
INFO = {
    "4EYES_DISTINCT":     ("Same person edited + reviewed",      "Two distinct persons required (GMP)."),
    "4EYES_ORDER":        ("Reviewed before edited",             "Review must happen after editing."),
    "CALC_NET_MASS":      ("Net != Gross - Tare",                "Calculation error or typo on entry."),
    "CALC_VOLUME":        ("Volume incorrect",                   "V != net mass x density."),
    "CALC_FORMULA":       ("Formula result incorrect",           "Handwritten result deviates from calculation."),
    "CALC_ROUNDING":      ("Rounding deviation",                 "Minimal deviation -- likely rounding."),
    "RANGE_SOLL":         ("Value out of range",                 "Deviation! Value lies outside the target range."),
    "RANGE_SETPOINT":     ("Setpoint not met",                   "Value does not match the setpoint."),
    "FMT_DATE_PADDING":   ("Date format incorrect",              "Format must be DD.MM.YYYY (e.g. 01.06.2026)."),
    "FMT_NKS":            ("Decimal places incorrect",           "Number of decimals does not match specification."),
    "DATE_BEFORE_PRINT":  ("Date before print date",             "Date before form print. OCR year error? (2016 vs 2026)."),
    "DATE_FAR_FUTURE":    ("Date too far in future",             "OCR year error? (2028 or 2076 vs 2026)."),
    "KUERZEL_UNKNOWN":    ("Unknown signer initials",            "Initials not in personnel list (page 4)."),
    "KUERZEL_UNRESOLVED": ("Unresolved signer initials",         "Initials could not be matched to a registered signer."),
    "SIG_INCOMPLETE":     ("Signature incomplete",               "Signature is missing date or initials."),
    "XREF_CARRIED_MATCH": ("Source value differs from carry-over", "Carry-over deviates from the source field value."),
    "XREF_NEAR_MISS":     ("Carry-over slightly off",            "Possible rounding difference -- check."),
    "XREF_MISMATCH":      ("Cross-reference mismatch",           "Carry-over deviates from source value."),
    "EXTRACT_LOW_CONF":   ("OCR uncertain",                      "Text recognition was uncertain. Check scan directly."),
}
ACTION = {
    "4EYES_DISTINCT":     "A second person must countersign, or Confirm if already done.",
    "4EYES_ORDER":        "Check date. On year error (e.g. 2016 -> 2026): Correct.",
    "CALC_NET_MASS":      "Read tare + gross from scan, compute net = gross - tare -> Correct.",
    "CALC_VOLUME":        "Check scan. V = net mass x density -> Correct the wrong value.",
    "CALC_FORMULA":       "Recompute formula -> Correct the right result.",
    "CALC_ROUNDING":      "Check scan. If rounding is plausible: Confirm.",
    "RANGE_SOLL":         "Value really out of range? If yes -> Confirm + document deviation. If OCR error -> Correct.",
    "RANGE_SETPOINT":     "Read correct value from scan -> Correct.",
    "FMT_DATE_PADDING":   "Date as DD.MM.YYYY -> Correct (e.g. '01.06.2026').",
    "FMT_NKS":            "Value with correct decimal count -> Correct.",
    "DATE_BEFORE_PRINT":  "Check year. OCR often reads 2016 instead of 2026 -> Correct.",
    "DATE_FAR_FUTURE":    "Check year. OCR often reads 2028/2076 instead of 2026 -> Correct.",
    "KUERZEL_UNKNOWN":    "Read initials from scan -> Correct.",
    "KUERZEL_UNRESOLVED": "Match initials to a registered signer -> Correct.",
    "SIG_INCOMPLETE":     "Add missing date or initials -> Correct.",
    "XREF_CARRIED_MATCH": "Compare source value and carry-over -> Correct.",
    "XREF_NEAR_MISS":     "Check rounding. If plausible: Confirm.",
    "XREF_MISMATCH":      "Compare source value and carry-over -> Correct.",
    "EXTRACT_LOW_CONF":   "Check scan and value -> Confirm or Correct.",
}
STATUS_DE = {"auto_accepted":"Auto-OK","needs_review":"To review",
             "confirmed":"Confirmed","corrected":"Corrected"}
# Registered canonical signers (page 4 personnel list)
CANONICAL_SIGNERS = ["ohs", "han"]


# ── HTTP ──────────────────────────────────────────────────────────────────────
def api(path, method="GET", body=None):
    url  = BASE + path
    data = json.dumps(body).encode() if body else None
    req  = urllib.request.Request(url, data=data, method=method,
           headers={"Content-Type":"application/json","Accept":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            return json.loads(r.read())
    except Exception:
        return None

def fetch_img(doc_id, page_no):
    try:
        with urllib.request.urlopen(
            f"{BASE}/api/v1/documents/{doc_id}/pages/{page_no}/image",
            timeout=10) as r:
            return r.read()
    except Exception:
        return None


# ── Tastenkuerzel-Dialog ──────────────────────────────────────────────────────
class KeyDialog(tk.Toplevel):
    LABELS = {
        "confirm": "Confirm",
        "correct": "Correct value",
        "next":    "Next field",
        "prev":    "Previous field",
        "filter_flags": "Errors/Warnings only",
        "filter_all":   "All fields",
    }
    def __init__(self, parent, keys, on_save):
        super().__init__(parent); self.title("Keyboard Shortcuts")
        self.configure(bg=C["hdr"]); self.resizable(False,False); self.grab_set()
        self._k = dict(keys); self._on_save = on_save; self._wait = None
        self._vars = {}; self._btns = {}
        self._build()

    def _build(self):
        tk.Label(self, text="Click a key, then press a key",
                 bg=C["hdr"], fg=C["dim"], font=("Segoe UI",9)).pack(pady=12)
        g = tk.Frame(self, bg=C["hdr"]); g.pack(padx=20, pady=4)
        for row,(action,label) in enumerate(self.LABELS.items()):
            tk.Label(g, text=label, font=("Segoe UI",10), bg=C["hdr"],
                     fg=C["fg"], width=22, anchor="w").grid(row=row,column=0,pady=4)
            v = tk.StringVar(value=self._k.get(action,"").strip("<>").replace("Return","Enter").replace("space","Space"))
            self._vars[action] = v
            b = tk.Button(g, textvariable=v, font=("Segoe UI",10,"bold"), width=14,
                          bg=C["side"], fg=C["blue"], relief="flat", bd=0,
                          padx=8, pady=6, cursor="hand2")
            b.grid(row=row, column=1, padx=(12,0), pady=4)
            b.bind("<Button-1>", lambda e,a=action: self._start(a))
            self._btns[action] = b
        bar = tk.Frame(self,bg=C["hdr"]); bar.pack(pady=16)
        tk.Button(bar,text="Save",bg="#166534",fg="white",relief="flat",bd=0,
                  padx=14,pady=8,cursor="hand2",command=self._save,
                  font=("Segoe UI",10,"bold")).pack(side="left",padx=6)
        tk.Button(bar,text="Default",bg=C["side"],fg=C["dim"],relief="flat",bd=0,
                  padx=14,pady=8,cursor="hand2",command=self._reset,
                  font=("Segoe UI",10)).pack(side="left",padx=6)
        tk.Button(bar,text="Cancel",bg=C["side"],fg=C["dim"],relief="flat",bd=0,
                  padx=14,pady=8,cursor="hand2",command=self.destroy,
                  font=("Segoe UI",10)).pack(side="left",padx=6)

    def _start(self, action):
        if self._wait: return
        self._wait = action
        self._vars[action].set("< press key >")
        self.bind("<Key>", self._on_key); self.focus_set()

    def _on_key(self, e):
        if not self._wait: return
        a = self._wait; self._wait = None; self.unbind("<Key>")
        if e.keysym == "Escape":
            self._vars[a].set(self._k.get(a,"").strip("<>").replace("Return","Enter")); return
        sp = {"Return":"Return","space":"space","Left":"Left","Right":"Right",
              "BackSpace":"BackSpace","Tab":"Tab"}
        sym = e.keysym
        bind = f"<{sp.get(sym,sym.lower() if len(sym)==1 else sym)}>"
        self._k[a] = bind
        self._vars[a].set(bind.strip("<>").replace("Return","Enter").replace("space","Space"))

    def _reset(self):
        self._k = dict(DEFAULT_KEYS)
        for a,v in self._vars.items():
            v.set(DEFAULT_KEYS.get(a,"").strip("<>").replace("Return","Enter").replace("space","Space"))

    def _save(self): self._on_save(self._k); self.destroy()


# ── Main App ──────────────────────────────────────────────────────────────────
class App:
    def __init__(self, root: tk.Tk):
        self.root   = root
        self.root.title("BioDize Eval")
        self.root.configure(bg=C["bg"])
        self.root.state("zoomed")
        self.root.minsize(900, 600)

        # Data
        self.docs:    list[dict] = []
        self.doc_id:  str | None = None
        self.items:   list[dict] = []
        self.visible: list[dict] = []
        self.idx = 0

        # Image cache (all pages in RAM)
        self.pil_cache:   dict[int, Image.Image]          = {}
        self.photo_cache: dict[tuple, ImageTk.PhotoImage] = {}
        self.cur_page: int | None = None
        self.cur_bbox: list | None = None
        self.cur_sev:  str | None = None

        # Zoom state -- 1.0 = fit-to-canvas (faster cache path)
        self.zoom   = 1.0
        self.zoom_x = 0.5
        self.zoom_y = 0.5
        self._pan_last: tuple | None = None

        # Bbox editor state
        self.edit_mode      = False
        self._draw_start:   tuple | None = None
        self._sel_fid:      str   | None = None
        self._page_fields:  list[dict]   = []
        self._drag_bbox:    list  | None = None
        self._drag_mode     = ""
        self._drag_start_c: tuple | None = None
        self._undo_stack:   list[tuple[str, list | None]] = []  # (field_id, old_bbox)

        # UI state
        self.filter_v = tk.StringVar(value="all")
        self._fullscreen = False
        self._done_shown = False
        self._be_proc: subprocess.Popen | None = None
        self._keys    = self._load_keys()
        self._img_ref = None   # GC protection

        self._build_ui()
        self._bind_keys()
        # Start backend immediately and connect
        self._auto_start_backend()

    # ── Tastenkuerzel ─────────────────────────────────────────────────────────

    def _load_keys(self):
        if KEYS_FILE.exists():
            try: return {**DEFAULT_KEYS, **json.loads(KEYS_FILE.read_text())}
            except: pass
        return dict(DEFAULT_KEYS)

    def _save_keys(self, keys):
        self._keys = keys
        KEYS_FILE.write_text(json.dumps(keys, indent=2))
        self._bind_keys()

    def _bind_keys(self):
        for seq in ("<Return>","<e>","<space>","<BackSpace>","<f>","<a>"):
            try: self.root.unbind(seq)
            except: pass
        k = self._keys
        def bind(key, fn):
            try: self.root.bind(key, lambda e: fn())
            except: pass
        bind(k.get("confirm","<Return>"),      self.confirm)
        bind(k.get("correct","<e>"),           self.correct)
        bind(k.get("next","<space>"),          self.next_field)
        bind(k.get("prev","<BackSpace>"),      self.prev_field)
        bind(k.get("filter_flags","<f>"),
             lambda: (self.filter_v.set("flagged"), self._apply_filter()))
        bind(k.get("filter_all","<a>"),
             lambda: (self.filter_v.set("all"), self._apply_filter()))
        self.root.bind("<F11>",    lambda e: self._toggle_fs())
        self.root.bind("<Escape>", lambda e: self._exit_fs())
        self.root.bind("<Control-d>", lambda e: self._open_table())
        self.root.bind("<Control-l>", lambda e: self._open_debugger())
        self._update_btn_labels()

    def _update_btn_labels(self):
        def fmt(k): return self._keys.get(k,"").strip("<>").replace("Return","Enter").replace("space","Space")
        if hasattr(self,"btn_confirm"):
            self.btn_confirm.config(text=f"Confirm   [{fmt('confirm')}]")
            self.btn_correct.config(text=f"Correct   [{fmt('correct')}]")
            self.btn_next.config(   text=f"Next   [{fmt('next')}]")

    # ── Backend auto-start ────────────────────────────────────────────────────

    def _auto_start_backend(self):
        """Starts the backend immediately, then connects automatically."""
        def _worker():
            # Check whether the backend is already running
            if api("/health"):
                self.root.after(0, self._on_connected)
                return
            # Backend starten
            self.root.after(0, lambda: self._set_status("Backend starting...", C["yel"]))
            self._be_proc = subprocess.Popen(
                [str(VENV_PY), "-m", "uvicorn", "app.main:app",
                 "--host", "127.0.0.1", "--port", "8000"],
                cwd=str(ROOT / "backend"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            # Warten bis erreichbar (max 30s)
            for _ in range(60):
                time.sleep(0.5)
                if api("/health"):
                    self.root.after(0, self._on_connected)
                    return
            self.root.after(0, lambda: self._set_status(
                "Backend did not start. Manually: 'Start App' in the launcher.", C["red"]))
        threading.Thread(target=_worker, daemon=True).start()

    def _on_connected(self):
        self._set_status("Connected -- loading data...", C["grn"])
        self._load_docs()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Header ───────────────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=C["hdr"], height=46)
        hdr.pack(fill="x"); hdr.pack_propagate(False)

        tk.Label(hdr, text="BioDize Eval",
                 font=("Segoe UI",13,"bold"), bg=C["hdr"], fg=C["fg"]
                 ).pack(side="left", padx=14, pady=8)

        # Document selector (for multiple batches)
        self.doc_var = tk.StringVar(value="Connecting...")
        self.doc_menu = ttk.Combobox(hdr, textvariable=self.doc_var,
                                     state="readonly", width=40,
                                     font=("Segoe UI",9))
        self.doc_menu.pack(side="left", padx=12)
        self.doc_menu.bind("<<ComboboxSelected>>", lambda e: self._switch_doc())

        tk.Button(hdr, text="+ Load", font=("Segoe UI",8,"bold"),
                  bg="#7c3aed", fg="white", activebackground="#6d28d9",
                  relief="flat", bd=0, padx=10, pady=5, cursor="hand2",
                  command=self._load_new_batch).pack(side="left", padx=4)

        self.lbl_status = tk.Label(hdr, text="Starting...",
                                   font=("Segoe UI",8), bg=C["hdr"], fg=C["dim"])
        self.lbl_status.pack(side="left", padx=10)

        # Right side header
        self.lbl_prog = tk.Label(hdr, text="",
                                 font=("Segoe UI",11,"bold"), bg=C["hdr"], fg=C["blue"])
        self.lbl_prog.pack(side="right", padx=14)

        self.btn_edit = tk.Button(hdr, text="Edit Boxes",
                                  font=("Segoe UI",8,"bold"),
                                  bg="#7c3aed", fg="white",
                                  activebackground="#6d28d9",
                                  relief="flat", bd=0, padx=10, pady=5,
                                  cursor="hand2",
                                  command=self._toggle_edit_mode)
        self.btn_edit.pack(side="right", padx=4)

        # New feature buttons: Analytics + Deviation Report
        self.btn_analytics = tk.Button(hdr, text="Analytics", font=("Segoe UI",8,"bold"),
                  bg="#0e7490", fg="white", activebackground="#155e75",
                  relief="flat", bd=0, padx=10, pady=5, cursor="hand2",
                  command=self._open_analytics)
        self.btn_analytics.pack(side="right", padx=4)

        self.btn_deviation = tk.Button(hdr, text="Deviation Report", font=("Segoe UI",8,"bold"),
                  bg="#b45309", fg="white", activebackground="#92400e",
                  relief="flat", bd=0, padx=10, pady=5, cursor="hand2",
                  command=self._open_deviation_report)
        self.btn_deviation.pack(side="right", padx=4)

        for text, cmd in [("Shortcuts", lambda: KeyDialog(self.root,self._keys,self._save_keys)),
                          ("Ground Truth",   self._open_gt),
                          ("Table (Ctrl+D)", self._open_table),
                          ("Debugger (Ctrl+L)", self._open_debugger)]:
            tk.Button(hdr, text=text, font=("Segoe UI",8),
                      bg=C["side"], fg=C["dim"], activebackground=C["sel"],
                      relief="flat", bd=0, padx=8, pady=5, cursor="hand2",
                      command=cmd).pack(side="right", padx=2)

        # ── Filter ───────────────────────────────────────────────────────────
        fbar = tk.Frame(self.root, bg=C["side"], height=30)
        fbar.pack(fill="x"); fbar.pack_propagate(False)

        tk.Label(fbar, text="Show:", bg=C["side"], fg=C["dim"],
                 font=("Segoe UI",8)).pack(side="left", padx=10, pady=6)

        for val, lbl, fg in [("all",     "All fields  [A]",         C["dim"]),
                              ("flagged", "Errors + Warnings  [F]",  C["red"]),
                              ("error",   "Errors only",             C["red"]),
                              ("warning", "Warnings only",           C["yel"])]:
            tk.Radiobutton(fbar, text=lbl, variable=self.filter_v, value=val,
                           command=self._apply_filter, bg=C["side"], fg=fg,
                           selectcolor=C["sel"], activebackground=C["side"],
                           font=("Segoe UI",8), cursor="hand2", relief="flat"
                           ).pack(side="left", padx=8)

        self.lbl_count = tk.Label(fbar, text="", bg=C["side"], fg=C["dim"],
                                  font=("Segoe UI",8))
        self.lbl_count.pack(side="right", padx=12)

        # ── Box Editor panel (hidden until activated) ─────────────────────────
        self.edit_bar = tk.Frame(self.root, bg="#1a0a2e")

        # Row 1: field picker + delete + save
        row1 = tk.Frame(self.edit_bar, bg="#1a0a2e"); row1.pack(fill="x", padx=8, pady=(6,2))

        tk.Label(row1, text="Field:", bg="#1a0a2e", fg="#a78bfa",
                 font=("Segoe UI",8)).pack(side="left")
        self.field_var = tk.StringVar()
        self.field_combo = ttk.Combobox(row1, textvariable=self.field_var,
                                        state="readonly", width=38,
                                        font=("Segoe UI",8))
        self.field_combo.pack(side="left", padx=(4,8))
        self.field_combo.bind("<<ComboboxSelected>>", self._on_field_combo)

        for txt, col, hov, cmd in [
            ("Delete Box [Del]", "#7f1d1d","#991b1b", self._delete_sel_bbox),
            ("Draw New Box",     "#1e40af","#1e3a8a", self._start_draw_mode),
            ("Save All",         "#166534","#14532d", self._save_all_bboxes),
        ]:
            b = tk.Button(row1, text=txt, font=("Segoe UI",8),
                          bg=col, fg="white", activebackground=hov,
                          relief="flat", bd=0, padx=8, pady=4,
                          cursor="hand2", command=cmd, takefocus=False)
            b.pack(side="left", padx=(0,4))

        # Row 2: coordinate editor + nudge hint
        row2 = tk.Frame(self.edit_bar, bg="#1a0a2e"); row2.pack(fill="x", padx=8, pady=(2,6))
        tk.Label(row2, text="Box (x0 y0 x1 y1):", bg="#1a0a2e", fg="#a78bfa",
                 font=("Segoe UI",8)).pack(side="left")
        self._coord_vars = []
        for _ in range(4):
            v = tk.StringVar()
            e = tk.Entry(row2, textvariable=v, width=7, font=("Segoe UI",8),
                         bg="#0f0a1e", fg="white", insertbackground="white",
                         relief="flat", bd=2)
            e.pack(side="left", padx=(4,0))
            v.trace_add("write", self._on_coord_change)
            self._coord_vars.append(v)
        self._coord_updating = False

        tk.Label(row2, text=" | Arrow keys: nudge  Shift+Arrow: fine  Ctrl+Z: undo",
                 bg="#1a0a2e", fg="#64748b", font=("Segoe UI",7)).pack(side="left", padx=8)
        self.lbl_sel_field = tk.Label(row2, text="", bg="#1a0a2e",
                                      fg="#c4b5fd", font=("Segoe UI",8,"bold"))
        self.lbl_sel_field.pack(side="right", padx=8)

        self._draw_mode_active = False

        # ── Main area ────────────────────────────────────────────────────────
        body = tk.Frame(self.root, bg=C["bg"])
        body.pack(fill="both", expand=True)

        # Left field list
        left = tk.Frame(body, bg=C["side"], width=280)
        left.pack(side="left", fill="y"); left.pack_propagate(False)

        self.lbl_list = tk.Label(left, text="Fields",
                                 font=("Segoe UI",8,"bold"),
                                 bg=C["side"], fg=C["dim"], anchor="w")
        self.lbl_list.pack(fill="x", padx=8, pady=(8,2))

        vsb = tk.Scrollbar(left, orient="vertical", bg=C["side"],
                           troughcolor=C["bg"], width=5)
        self.lb = tk.Listbox(left, yscrollcommand=vsb.set,
                             bg=C["side"], fg=C["fg"],
                             selectbackground=C["sel"], selectforeground=C["fg"],
                             bd=0, highlightthickness=0, activestyle="none",
                             font=("Segoe UI",9), relief="flat", cursor="hand2")
        vsb.config(command=self.lb.yview)
        vsb.pack(side="right", fill="y")
        self.lb.pack(fill="both", expand=True, padx=(4,0))
        self.lb.bind("<<ListboxSelect>>", lambda e: self._on_list_select())

        # Right side
        right = tk.Frame(body, bg=C["bg"])
        right.pack(side="left", fill="both", expand=True)

        # Scan image (almost the entire space)
        self.canvas = tk.Canvas(right, bg="#0f0f0f",
                                highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True, padx=6, pady=(6,2))
        self.canvas.bind("<Configure>",     lambda e: self._redraw())
        self.canvas.bind("<MouseWheel>",      self._on_wheel)
        self.canvas.bind("<Button-4>",        self._on_wheel)
        self.canvas.bind("<Button-5>",        self._on_wheel)
        self.canvas.bind("<ButtonPress-1>",   self._mouse_down)
        self.canvas.bind("<B1-Motion>",       self._mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._mouse_up)
        self.canvas.bind("<Double-Button-1>", self._dbl_click)
        self.root.bind("<Delete>",    lambda e: self._delete_sel_bbox())
        self.root.bind("<BackSpace>", lambda e: self._delete_sel_bbox() if self.edit_mode else None)
        self.root.bind("<Control-z>", lambda e: self._undo())
        self.root.bind("<Escape>",    lambda e: (self._exit_fs() or self._cancel_edit_sel()))

        # Error banner (one line, with severity icon)
        self.banner = tk.Frame(right, height=34)
        self.banner.pack(fill="x", padx=6, pady=(0,2))
        self.banner.pack_propagate(False)

        self.lbl_banner = tk.Label(self.banner, text="",
                                   font=("Segoe UI",10,"bold"), anchor="w")
        self.lbl_banner.pack(side="left", fill="both", expand=True, padx=12)

        self.lbl_exp = tk.Label(self.banner, text="",
                                font=("Segoe UI",8), anchor="e", wraplength=600)
        self.lbl_exp.pack(side="right", padx=12)

        # Smart corrections panel (collapsible, appears for flagged fields)
        self.smart_panel = SmartCorrectionsPanel(right, self)

        # Action line
        self.lbl_action = tk.Label(right, text="", font=("Segoe UI",8),
                                   bg=C["side"], fg=C["grn"], anchor="w")
        self.lbl_action.pack(fill="x", padx=6, pady=(0,2))

        # Buttons
        btn_row = tk.Frame(right, bg=C["hdr"], height=50)
        btn_row.pack(fill="x", padx=6, pady=(0,6)); btn_row.pack_propagate(False)

        def mkbtn(text, color, hover, cmd):
            b = tk.Button(btn_row, text=text, font=("Segoe UI",10,"bold"),
                          bg=color, fg="white", activebackground=hover,
                          activeforeground="white", relief="flat", bd=0,
                          padx=20, pady=10, cursor="hand2", command=cmd,
                          takefocus=False)   # no focus stealing
            b.pack(side="left", padx=(8,4), pady=6)
            b.bind("<Enter>", lambda e: b.config(bg=hover))
            b.bind("<Leave>", lambda e: b.config(bg=color))
            return b

        self.btn_confirm = mkbtn("Confirm   [Enter]","#166534","#14532d", self.confirm)
        self.btn_correct = mkbtn("Correct   [E]",   "#1e40af","#1e3a8a", self.correct)
        self.btn_next    = mkbtn("Next   [Space]",     "#374151","#4b5563", self.next_field)

        def nav_cmd(fn):
            def _f(): fn(); self.root.focus_set()
            return _f

        tk.Button(btn_row, text=">", font=("Segoe UI",13),
                  bg=C["hdr"], fg=C["dim"], relief="flat", bd=0,
                  padx=10, pady=8, cursor="hand2",
                  command=nav_cmd(self.next_field),
                  takefocus=False).pack(side="right", padx=4)
        tk.Button(btn_row, text="<", font=("Segoe UI",13),
                  bg=C["hdr"], fg=C["dim"], relief="flat", bd=0,
                  padx=10, pady=8, cursor="hand2",
                  command=nav_cmd(self.prev_field),
                  takefocus=False).pack(side="right", padx=4)

        # Progress bar
        style = ttk.Style(); style.configure("P.Horizontal.TProgressbar",
            troughcolor=C["side"], background="#166534", thickness=3)
        self.prog = ttk.Progressbar(self.root, mode="determinate",
                                    style="P.Horizontal.TProgressbar")
        self.prog.pack(fill="x", side="bottom")

        # Mini review-progress bar (X/Y fields reviewed)
        rev_bar = tk.Frame(self.root, bg=C["hdr"], height=22)
        rev_bar.pack(fill="x", side="bottom"); rev_bar.pack_propagate(False)
        self.lbl_review = tk.Label(rev_bar, text="0 / 0 fields reviewed",
                                   font=("Segoe UI",8), bg=C["hdr"], fg=C["dim"])
        self.lbl_review.pack(side="left", padx=12)
        self.rev_canvas = tk.Canvas(rev_bar, bg=C["side"], height=8, width=200,
                                    highlightthickness=0)
        self.rev_canvas.pack(side="left", padx=8, pady=6)

        self._set_buttons(False)

    # ── Status ────────────────────────────────────────────────────────────────

    def _set_status(self, msg, color=None):
        self.lbl_status.config(text=msg, fg=color or C["dim"])

    def _set_buttons(self, active: bool):
        st = "normal" if active else "disabled"
        self.btn_confirm.config(state=st)
        self.btn_correct.config(state=st)

    def _update_review_progress(self):
        """Update the mini review-progress bar (resolved / total fields)."""
        if not hasattr(self, "rev_canvas"):
            return
        total = len(self.items)
        done  = sum(1 for i in self.items
                    if not i["flags"] or
                    i["status"] in ("confirmed", "corrected", "auto_accepted"))
        self.lbl_review.config(text=f"{done} / {total} fields reviewed")
        w = 200; h = 8
        self.rev_canvas.delete("all")
        self.rev_canvas.create_rectangle(0, 0, w, h, fill=C["side"], outline="")
        if total:
            fw = int(w * done / total)
            col = "#4ade80" if done == total else "#60a5fa"
            self.rev_canvas.create_rectangle(0, 0, fw, h, fill=col, outline="")

    # ── Documents ─────────────────────────────────────────────────────────────

    def _load_docs(self):
        def _w():
            docs = api("/api/v1/documents")
            if not docs:
                self.root.after(0, lambda: self._set_status(
                    "No documents. 'Load sample data' in the launcher.", C["yel"]))
                return
            self.docs = docs
            labels = [f"{d.get('doc_no','?')}  ({d.get('n_fields',0)} fields, "
                      f"{d.get('n_errors',0)} errors)" for d in docs]
            self.root.after(0, lambda: (
                self.doc_menu.config(values=labels),
                self.doc_menu.current(0),
                self._switch_doc()
            ))
        threading.Thread(target=_w, daemon=True).start()

    def _switch_doc(self):
        idx = self.doc_menu.current()
        if 0 <= idx < len(self.docs):
            self.doc_id = self.docs[idx]["id"]
            self.pil_cache.clear(); self.photo_cache.clear()
            self._load_fields()

    def _load_fields(self):
        self._set_status("Loading fields...", C["yel"])
        doc_id = self.doc_id
        def _w():
            fields = api(f"/api/v1/documents/{doc_id}/fields") or []
            items = []
            for f in fields:
                flags = f.get("flags", [])
                items.append(dict(
                    id=f.get("id"), page=f.get("page_no",0),
                    chapter=f.get("chapter") or "",
                    label=f.get("label_raw") or f.get("role") or "?",
                    value=f.get("value_raw") or "",
                    unit=f.get("unit") or "", status=f.get("status",""),
                    bbox=f.get("bbox"), flags=flags,
                    has_err=any(fl["severity"]=="error"   for fl in flags),
                    has_wrn=any(fl["severity"]=="warning" for fl in flags),
                ))
            n_err = sum(1 for i in items if i["has_err"])
            n_wrn = sum(1 for i in items if i["has_wrn"] and not i["has_err"])
            n_ok  = sum(1 for i in items if not i["flags"])
            self.root.after(0, lambda: self._on_fields_loaded(items, n_err, n_wrn, n_ok))
        threading.Thread(target=_w, daemon=True).start()

    def _on_fields_loaded(self, items, n_err, n_wrn, n_ok):
        self.items = items
        self._set_status(
            f"{n_err} errors   {n_wrn} warnings   {n_ok} OK   "
            f"(images loading in background...)", C["fg"])
        self._apply_filter()
        self._update_review_progress()
        threading.Thread(target=self._preload_all, daemon=True).start()

    # ── Image preloading ──────────────────────────────────────────────────────

    def _preload_all(self):
        doc_id   = self.doc_id
        all_pgs  = sorted({i["page"] for i in self.items})
        # Current page first, then all others ascending
        cur      = [self.cur_page] if self.cur_page in all_pgs else []
        ordered  = cur + [p for p in all_pgs if p not in cur]
        total  = len(ordered)
        loaded = 0
        for pg in ordered:
            if doc_id != self.doc_id:
                return
            if pg in self.pil_cache:
                loaded += 1
                continue
            data = fetch_img(doc_id, pg)
            if data:
                img = Image.open(BytesIO(data)).convert("RGB")
                # No downscaling -- full resolution in RAM
                self.pil_cache[pg] = img
                loaded += 1
                if pg == self.cur_page:
                    self.root.after(0, self._redraw)
        self.root.after(0, lambda: self._set_status(
            f"{loaded}/{total} pages loaded -- navigation is instant", C["grn"]))

    # ── Filter + list ─────────────────────────────────────────────────────────

    def _apply_filter(self):
        mode = self.filter_v.get()
        if   mode == "flagged": self.visible = [i for i in self.items if i["flags"]]
        elif mode == "error":   self.visible = [i for i in self.items if i["has_err"]]
        elif mode == "warning": self.visible = [i for i in self.items if i["has_wrn"] and not i["has_err"]]
        else:                   self.visible = list(self.items)

        self.lb.delete(0, "end")
        for item in self.visible:
            if   item["has_err"]: icon,fg = "X", C["red"]
            elif item["has_wrn"]: icon,fg = "!", C["yel"]
            elif item["status"] in ("confirmed","corrected","auto_accepted"):
                                  icon,fg = "v", C["grn"]
            else:                 icon,fg = "-", C["dim"]
            code  = item["flags"][0]["code"] if item["flags"] else ""
            short = (code.replace("4EYES_","4A:").replace("CALC_","C:")
                        .replace("RANGE_","R:").replace("DATE_","D:"))
            txt = f" {icon}  p{item['page']:<3} {item['label'][:22]}"
            if code: txt += f"  {short}"
            self.lb.insert("end", txt)
            self.lb.itemconfig("end", fg=fg)

        n  = len(self.visible)
        nf = sum(1 for i in self.visible if i["flags"])
        self.lbl_list.config(text=f"{n} fields  |  {nf} with flags")
        self.lbl_count.config(text=f"{nf} to review" if nf else "All reviewed!")
        self._update_review_progress()

        if self.visible:
            self._done_shown = False
            self.lb.selection_set(0)
            self.lb.see(0)          # always scroll to top
            self._show(0)

    def _on_list_select(self):
        sel = self.lb.curselection()
        if sel: self._show(sel[0])

    # ── Display ───────────────────────────────────────────────────────────────

    def _show(self, idx: int):
        if not (0 <= idx < len(self.visible)): return
        self.idx = idx
        item  = self.visible[idx]
        flags = item["flags"]
        total = len(self.visible)

        # Progress
        self.lbl_prog.config(text=f"{idx+1} / {total}")
        self.prog["maximum"] = total; self.prog["value"] = idx + 1

        # Banner
        if flags:
            fl   = flags[0]; sev = fl["severity"]; code = fl["code"]
            bg   = C["err"] if sev == "error" else C["wrn"]
            col  = C["red"] if sev == "error" else C["yel"]
            icon = "✗" if sev == "error" else "⚠"   # cross / warning sign
            lbl  = "ERROR" if sev == "error" else "WARNING"
            title, explain = INFO.get(code, (code, fl.get("message","")))
            exp = fl.get("expected",""); act = fl.get("actual","")
            banner_txt = f"  {icon}  {lbl}: {title}"
            if exp or act: banner_txt += f"    |    Expected: {exp}    Found: {act}"
            self.banner.config(bg=bg)
            self.lbl_banner.config(bg=bg, fg=col, text=banner_txt)
            self.lbl_exp.config(bg=bg, fg=C["dim"], text=explain)
            self.lbl_action.config(bg=C["side"], fg=C["grn"],
                text=f"  What to do?  {ACTION.get(code,'Check scan.')}")
        else:
            st = STATUS_DE.get(item["status"], item["status"])
            self.banner.config(bg=C["ok"])
            self.lbl_banner.config(bg=C["ok"], fg=C["grn"],
                text=f"  OK  —  {st}  —  p{item['page']}  {item['label'][:40]}")
            self.lbl_exp.config(bg=C["ok"], fg=C["dim"], text=item["value"])
            self.lbl_action.config(bg=C["side"], fg=C["dim"], text="")

        self._set_buttons(bool(flags))

        # Smart corrections panel: show suggestions for flagged fields
        if hasattr(self, "smart_panel"):
            self.smart_panel.update_for(item)

        # Set image -- reset zoom on new field
        new_page = item["page"]
        self.cur_bbox = item["bbox"]
        self.cur_sev  = flags[0]["severity"] if flags else None
        if new_page != self.cur_page:
            self.zoom = 1.0; self.zoom_x = 0.5; self.zoom_y = 0.5
            self.cur_page = new_page
            if self.edit_mode:
                self._load_page_fields()
        else:
            self.cur_page = new_page
        # Always reset selection on field change
        if self.edit_mode:
            self._sel_fid = None
            self.lbl_sel_field.config(text="No field selected -- click to select")
        self._redraw()

    # ── Bbox editor ──────────────────────────────────────────────────────────────

    def _toggle_edit_mode(self):
        self.edit_mode = not self.edit_mode
        if self.edit_mode:
            self.btn_edit.config(bg="#6d28d9", text="Stop Editing")
            self.edit_bar.pack(fill="x")
            self._load_page_fields()
            self._populate_field_combo()
            # Arrow key nudge in edit mode
            self.root.bind("<Up>",    lambda e: self._nudge(0, -0.005))
            self.root.bind("<Down>",  lambda e: self._nudge(0,  0.005))
            self.root.bind("<Left>",  lambda e: self._nudge(-0.005, 0))
            self.root.bind("<Right>", lambda e: self._nudge( 0.005, 0))
            self.root.bind("<Shift-Up>",    lambda e: self._nudge(0, -0.001))
            self.root.bind("<Shift-Down>",  lambda e: self._nudge(0,  0.001))
            self.root.bind("<Shift-Left>",  lambda e: self._nudge(-0.001, 0))
            self.root.bind("<Shift-Right>", lambda e: self._nudge( 0.001, 0))
        else:
            self.btn_edit.config(bg="#7c3aed", text="Edit Boxes")
            self.edit_bar.pack_forget()
            self._sel_fid = None
            self._draw_mode_active = False
            for key in ("<Up>","<Down>","<Left>","<Right>",
                        "<Shift-Up>","<Shift-Down>","<Shift-Left>","<Shift-Right>"):
                self.root.unbind(key)
            self._bind_keys()   # restore navigation keys
            self._redraw()

    def _load_page_fields(self):
        """Loads all fields of the current page for the editor."""
        pg = self.cur_page
        if not pg:
            return
        self._page_fields = [i for i in self.items if i["page"] == pg]
        self._redraw()

    def _view_params(self):
        """Returns (pil, iw, ih, base, ox, oy, pw, ph, x0, y0, x1, y1)
        describing where and how the image is drawn on canvas.
        ox/oy = canvas top-left of image; pw/ph = displayed pixel size."""
        cw = self.canvas.winfo_width(); ch = self.canvas.winfo_height()
        pg = self.cur_page
        if pg not in self.pil_cache:
            return None
        pil = self.pil_cache[pg]
        iw, ih = pil.size
        base = min(cw/iw, ch/ih)
        if self.zoom <= 1.0:
            pw = int(iw*base); ph = int(ih*base)
            ox = (cw-pw)//2;   oy = (ch-ph)//2
            return pil, iw, ih, base, ox, oy, pw, ph, 0.0, 0.0, float(iw), float(ih)
        else:
            # Zoom: fill the full canvas (original behaviour)
            ts = base*self.zoom
            vw = cw/ts; vh = ch/ts
            x0 = max(0.0, self.zoom_x*iw - vw/2)
            y0 = max(0.0, self.zoom_y*ih - vh/2)
            x1 = min(float(iw), x0+vw); y1 = min(float(ih), y0+vh)
            if x1 >= iw: x0 = max(0.0, iw-vw)
            if y1 >= ih: y0 = max(0.0, ih-vh)
            return pil, iw, ih, base, 0, 0, cw, ch, x0, y0, x1, y1

    def _canvas_to_img(self, cx, cy):
        """Canvas coordinate -> normalized image coordinate (0-1)."""
        v = self._view_params()
        if not v: return None, None
        _, iw, ih, _, ox, oy, pw, ph, x0, y0, x1, y1 = v
        nx = x0/iw + (cx-ox)/pw * (x1-x0)/iw
        ny = y0/ih + (cy-oy)/ph * (y1-y0)/ih
        return max(0.0, min(1.0, nx)), max(0.0, min(1.0, ny))

    def _img_to_canvas(self, nx, ny):
        """Normalized image coordinate -> canvas coordinate."""
        v = self._view_params()
        if not v: return 0, 0
        _, iw, ih, _, ox, oy, pw, ph, x0, y0, x1, y1 = v
        cx = ox + (nx*iw - x0) / (x1-x0) * pw
        cy = oy + (ny*ih - y0) / (y1-y0) * ph
        return cx, cy

    def _hit_field(self, nx, ny, tol=0.01):
        """Findet das Feld an normierter Bildkoordinate, None wenn keins."""
        best_fid = None; best_area = float("inf")
        for item in self._page_fields:
            b = item.get("bbox")
            if not b or len(b) != 4:
                continue
            x0,y0,x1,y1 = b
            # Toleranz beachten
            if (x0-tol <= nx <= x1+tol) and (y0-tol <= ny <= y1+tol):
                area = (x1-x0)*(y1-y0)
                if area < best_area:
                    best_area = area; best_fid = item["id"]
        return best_fid

    def _handle_zone(self, nx, ny, bbox, tol=0.012):
        """Gibt zurueck welche Zone einer Box angeklickt wurde."""
        x0,y0,x1,y1 = bbox
        near = lambda a,b: abs(a-b) < tol
        if near(nx,x1) and near(ny,y1): return "resize_br"
        if near(nx,x0) and near(ny,y1): return "resize_bl"
        if near(nx,x1) and near(ny,y0): return "resize_tr"
        if near(nx,x0) and near(ny,y0): return "resize_tl"
        if near(nx,x1): return "resize_r"
        if near(nx,x0): return "resize_l"
        if near(ny,y1): return "resize_b"
        if near(ny,y0): return "resize_t"
        if x0 <= nx <= x1 and y0 <= ny <= y1: return "move"
        return "none"

    # ── Field combo + coordinate editor ──────────────────────────────────────

    def _populate_field_combo(self):
        """Fill the field dropdown with all fields on the current page."""
        opts = [f"{i.get('label','?')[:45]}  (p{i['page']})"
                for i in self._page_fields]
        self.field_combo.config(values=opts)
        if opts: self.field_combo.current(0); self._on_field_combo()

    def _on_field_combo(self, _=None):
        idx = self.field_combo.current()
        if 0 <= idx < len(self._page_fields):
            item = self._page_fields[idx]
            self._sel_fid = item["id"]
            self.lbl_sel_field.config(text=item.get("label","?")[:30])
            self._update_coord_display()
            self._redraw()

    def _update_coord_display(self):
        """Update the x0 y0 x1 y1 entry fields from selected bbox."""
        if self._coord_updating: return
        item = next((i for i in self._page_fields if i["id"]==self._sel_fid), None)
        if not item: return
        b = item.get("bbox") or [0,0,0,0]
        self._coord_updating = True
        for var, val in zip(self._coord_vars, b):
            var.set(f"{val:.4f}")
        self._coord_updating = False

    def _on_coord_change(self, *_):
        """Apply manually edited coordinates to selected field."""
        if self._coord_updating: return
        item = next((i for i in self._page_fields if i["id"]==self._sel_fid), None)
        if not item: return
        try:
            vals = [float(v.get()) for v in self._coord_vars]
            if all(0 <= v <= 1 for v in vals) and vals[0]<vals[2] and vals[1]<vals[3]:
                item["bbox"] = vals
                self._redraw()
        except (ValueError, tk.TclError):
            pass

    def _nudge(self, dx: float, dy: float):
        """Move selected bbox by dx/dy (normalized 0-1)."""
        item = next((i for i in self._page_fields if i["id"]==self._sel_fid), None)
        if not item or not item.get("bbox"): return
        self._push_undo(item["id"], item["bbox"])
        b = list(item["bbox"])
        w, h = b[2]-b[0], b[3]-b[1]
        b[0] = max(0.0, min(1.0-w, b[0]+dx)); b[1] = max(0.0, min(1.0-h, b[1]+dy))
        b[2] = b[0]+w; b[3] = b[1]+h
        item["bbox"] = b
        self._update_coord_display(); self._redraw()

    def _start_draw_mode(self):
        self._draw_mode_active = True
        self.lbl_sel_field.config(text="Draw mode: click and drag on the scan")
        self.canvas.config(cursor="crosshair")

    def _cancel_edit_sel(self):
        self._sel_fid = None
        if self.edit_mode:
            self.lbl_sel_field.config(text="")
            self._redraw()

    def _push_undo(self, fid: str, old_bbox):
        self._undo_stack.append((fid, list(old_bbox) if old_bbox else None))
        if len(self._undo_stack) > 50:
            self._undo_stack.pop(0)

    def _undo(self):
        if not self._undo_stack:
            return
        fid, old_bbox = self._undo_stack.pop()
        item = next((i for i in self._page_fields if i["id"] == fid), None)
        if item:
            item["bbox"] = old_bbox
            self._sel_fid = fid
            self.lbl_sel_field.config(text=f"Undone: {item.get('label','?')[:25]}")
            self._update_coord_display()
        self._redraw()

    def _delete_sel_bbox(self):
        if not self.edit_mode or not self._sel_fid:
            return
        item = next((i for i in self._page_fields if i["id"]==self._sel_fid), None)
        if not item:
            return
        self._push_undo(item["id"], item.get("bbox"))
        item["bbox"] = None
        self.lbl_sel_field.config(text="Box deleted  (Ctrl+Z to undo)")
        self._update_coord_display()
        self._redraw()

    def _save_all_bboxes(self):
        """Saves all changed bboxes of the current page to the API."""
        to_save = [(i["id"], i.get("bbox")) for i in self._page_fields]
        self.lbl_sel_field.config(text=f"Saving {len(to_save)} fields...")
        def _bg():
            ok = err = 0
            for fid, bbox in to_save:
                if bbox is not None:
                    r = api(f"/api/v1/fields/{fid}", method="PATCH",
                            body={"action":"set_bbox","bbox":bbox,"actor":"editor"})
                else:
                    r = api(f"/api/v1/fields/{fid}", method="PATCH",
                            body={"action":"delete_bbox","actor":"editor"})
                if r: ok += 1
                else: err += 1
            # Auch in self.items aktualisieren
            for item in self._page_fields:
                for ii in self.items:
                    if ii["id"] == item["id"]:
                        ii["bbox"] = item.get("bbox"); break
            msg = f"Saved: {ok}  Errors: {err}"
            self.root.after(0, lambda: self.lbl_sel_field.config(text=msg))
        threading.Thread(target=_bg, daemon=True).start()

    # ── Zoom-Methoden (beeinflussen NUR _redraw, keine anderen Funktionen) ──────

    def _mouse_down(self, event):
        if self.edit_mode:
            self._edit_down(event)
        else:
            self._pan_start(event)

    def _mouse_drag(self, event):
        if self.edit_mode:
            self._edit_drag(event)
        else:
            self._pan_move(event)

    def _mouse_up(self, event):
        if self.edit_mode:
            self._edit_up(event)
        else:
            self._pan_last = None

    def _dbl_click(self, event):
        if not self.edit_mode:
            self._zoom_reset()

    # ── Edit-Mouse-Handler ────────────────────────────────────────────────────

    def _edit_down(self, event):
        nx, ny = self._canvas_to_img(event.x, event.y)
        if nx is None:
            return
        fid = self._hit_field(nx, ny)
        if self._draw_mode_active or not fid:
            # Draw new box
            self._draw_start  = (nx, ny)
            self._drag_mode   = "draw"
            self._draw_mode_active = True
            return
        # Select existing field
        item = next(i for i in self._page_fields if i["id"]==fid)
        bbox = item.get("bbox")
        zone = self._handle_zone(nx, ny, bbox) if bbox else "move"
        self._sel_fid      = fid
        self._drag_mode    = zone
        self._drag_bbox    = list(bbox) if bbox else None
        self._drag_start_c = (nx, ny)
        self._push_undo(fid, bbox)
        self.lbl_sel_field.config(text=item.get("label","?")[:35])
        # Sync combo + coords
        for i, it in enumerate(self._page_fields):
            if it["id"] == fid:
                self.field_combo.current(i); break
        self._update_coord_display()
        self._redraw()

    def _edit_drag(self, event):
        nx, ny = self._canvas_to_img(event.x, event.y)
        if nx is None:
            return

        if self._drag_mode == "draw" and self._draw_start:
            x0,y0 = self._draw_start
            # Live-Vorschau auf Canvas
            c0x,c0y = self._img_to_canvas(x0,y0)
            c1x,c1y = self._img_to_canvas(nx,ny)
            self._redraw()
            self.canvas.create_rectangle(
                min(c0x,c1x), min(c0y,c1y), max(c0x,c1x), max(c0y,c1y),
                outline="#a78bfa", width=2, dash=(4,2))
            return

        if not self._sel_fid or not self._drag_bbox:
            return
        item = next((i for i in self._page_fields if i["id"]==self._sel_fid), None)
        if not item:
            return

        sx, sy = self._drag_start_c
        dx = nx - sx; dy = ny - sy
        b  = list(self._drag_bbox)

        m = self._drag_mode
        if m == "move":
            w = b[2]-b[0]; h = b[3]-b[1]
            b[0]=max(0.0, min(1.0-w, b[0]+dx)); b[1]=max(0.0,min(1.0-h,b[1]+dy))
            b[2]=b[0]+w;  b[3]=b[1]+h
        elif "r" in m: b[2] = max(b[0]+0.01, min(1.0, b[2]+dx))
        elif "l" in m: b[0] = max(0.0, min(b[2]-0.01, b[0]+dx)); b[2]=self._drag_bbox[2]
        if   "b" in m: b[3] = max(b[1]+0.01, min(1.0, b[3]+dy))
        elif "t" in m: b[1] = max(0.0, min(b[3]-0.01, b[1]+dy)); b[3]=self._drag_bbox[3]

        item["bbox"] = b
        self._drag_start_c = (nx, ny)
        self._drag_bbox    = list(b)
        self._redraw()

    def _edit_up(self, event):
        if self._drag_mode == "draw" and self._draw_start:
            nx, ny = self._canvas_to_img(event.x, event.y)
            if nx is None:
                self._draw_start = None; return
            x0,y0 = self._draw_start
            x0,x1 = sorted([x0,nx]); y0,y1 = sorted([y0,ny])
            if (x1-x0 > 0.005) and (y1-y0 > 0.005):
                # Box dem aktuell angezeigten Feld zuweisen
                cur = self._cur()
                if cur and cur["page"] == self.cur_page:
                    cur_item = next((i for i in self._page_fields
                                    if i["id"]==cur["id"]), None)
                    if cur_item:
                        self._push_undo(cur_item["id"], cur_item.get("bbox"))
                        cur_item["bbox"] = [x0,y0,x1,y1]
                        self._sel_fid = cur_item["id"]
                        self.lbl_sel_field.config(
                            text=f"New box: {cur_item.get('label','?')[:30]}  (Ctrl+Z undo  |  Save to persist)")
                        self._update_coord_display()
            self._draw_start = None
            self._draw_mode_active = False
        self._drag_mode = ""
        self._update_coord_display()
        self._redraw()

    def _on_wheel(self, event):
        """Mouse wheel: zoom in/out, centered on the mouse position."""
        if self.cur_page not in self.pil_cache:
            return
        cw = self.canvas.winfo_width(); ch = self.canvas.winfo_height()
        delta = getattr(event, "delta", 0)
        # Windows: delta +/-120; Linux: num 4=up, 5=down
        up = (delta > 0) or (getattr(event,"num",0) == 4)
        factor = 1.25 if up else 1/1.25
        new_zoom = max(1.0, min(12.0, self.zoom * factor))
        if new_zoom == self.zoom:
            return

        pil = self.pil_cache[self.cur_page]
        iw, ih = pil.size
        base = min(cw/iw, ch/ih)

        # Mouse position as fraction of the canvas (0-1)
        mx = max(0.0, min(1.0, event.x / cw))
        my = max(0.0, min(1.0, event.y / ch))

        # Altes sichtbares Fenster in Bildpixeln
        old_vw = cw / (base * self.zoom)
        old_vh = ch / (base * self.zoom)
        old_x0 = self.zoom_x * iw - old_vw / 2
        old_y0 = self.zoom_y * ih - old_vh / 2

        # Bildpunkt unter der Maus
        mouse_ix = old_x0 + mx * old_vw
        mouse_iy = old_y0 + my * old_vh

        # Neues Fenster
        new_vw = cw / (base * new_zoom)
        new_vh = ch / (base * new_zoom)
        new_cx = mouse_ix - (mx - 0.5) * new_vw
        new_cy = mouse_iy - (my - 0.5) * new_vh

        # Auf Bildgrenzen klemmen
        new_cx = max(new_vw/2, min(iw - new_vw/2, new_cx))
        new_cy = max(new_vh/2, min(ih - new_vh/2, new_cy))

        self.zoom   = new_zoom
        self.zoom_x = new_cx / iw
        self.zoom_y = new_cy / ih
        self._redraw()

    def _pan_start(self, event):
        if self.zoom > 1.0:
            self._pan_last = (event.x, event.y)

    def _pan_move(self, event):
        if self.zoom <= 1.0 or not self._pan_last:
            return
        if self.cur_page not in self.pil_cache:
            return
        cw = self.canvas.winfo_width(); ch = self.canvas.winfo_height()
        pil = self.pil_cache[self.cur_page]
        iw, ih = pil.size
        base = min(cw/iw, ch/ih)
        ts   = base * self.zoom

        dx = (event.x - self._pan_last[0]) / ts / iw
        dy = (event.y - self._pan_last[1]) / ts / ih
        self._pan_last = (event.x, event.y)

        vw = cw / ts; vh = ch / ts
        self.zoom_x = max(vw/(2*iw), min(1 - vw/(2*iw), self.zoom_x - dx))
        self.zoom_y = max(vh/(2*ih), min(1 - vh/(2*ih), self.zoom_y - dy))
        self._redraw()

    def _zoom_reset(self):
        self.zoom = 1.0; self.zoom_x = 0.5; self.zoom_y = 0.5
        self._redraw()

    # ── Render ────────────────────────────────────────────────────────────────

    def _redraw(self):
        cw = self.canvas.winfo_width(); ch = self.canvas.winfo_height()
        if cw < 10 or ch < 10: return
        self.canvas.delete("all")

        pg = self.cur_page
        if pg is None or pg not in self.pil_cache:
            msg = ("Loading image...\n\n"
                   "All pages are loaded automatically in the background.\n"
                   "Navigation is available as soon as the page is ready.")
            self.canvas.create_text(cw//2, ch//2, text=msg,
                fill=C["dim"], font=("Segoe UI",11), justify="center")
            return

        pil = self.pil_cache[pg]
        iw, ih = pil.size
        base = min(cw/iw, ch/ih)

        v = self._view_params()
        if not v:
            return
        _, _, _, _, ox, oy, pw, ph, x0v, y0v, x1v, y1v = v

        def _ic(nx, ny):  # image-norm -> canvas
            return ox + (nx*iw - x0v)/(x1v-x0v)*pw, oy + (ny*ih - y0v)/(y1v-y0v)*ph

        if self.zoom <= 1.0:
            # ── Fast cached path ─────────────────────────────────────────────
            key = (pg, cw, ch)
            photo = self.photo_cache.get(key)
            if photo is None:
                photo = ImageTk.PhotoImage(pil.resize((pw, ph), Image.BILINEAR))
                self.photo_cache[key] = photo
            self._img_ref = photo
            self.canvas.create_image(ox, oy, image=photo, anchor="nw")

            # Current field bbox
            bbox = self.cur_bbox; sev = self.cur_sev
            if bbox and len(bbox) == 4:
                bx0, by0 = _ic(bbox[0], bbox[1]); bx1, by1 = _ic(bbox[2], bbox[3])
                color = "#ef4444" if sev == "error" else "#f59e0b"
                self.canvas.create_rectangle(bx0, by0, bx1, by1, outline=color, width=3)

        else:
            # ── Zoom path: crop fills full canvas (original behaviour) ────────
            _, _, _, _, ox, oy, pw, ph, x0v, y0v, x1v, y1v = v
            crop  = pil.crop((int(x0v), int(y0v), int(x1v), int(y1v)))
            disp  = crop.resize((cw, ch), Image.BILINEAR)
            photo = ImageTk.PhotoImage(disp)
            self._img_ref = photo
            self.canvas.create_image(0, 0, image=photo, anchor="nw")

            bbox = self.cur_bbox; sev = self.cur_sev
            if bbox and len(bbox) == 4:
                bx0c, by0c = _ic(bbox[0], bbox[1])
                bx1c, by1c = _ic(bbox[2], bbox[3])
                if bx1c > 0 and bx0c < cw and by1c > 0 and by0c < ch:
                    color = "#ef4444" if sev == "error" else "#f59e0b"
                    self.canvas.create_rectangle(
                        max(0, bx0c), max(0, by0c),
                        min(cw, bx1c), min(ch, by1c),
                        outline=color, width=3)

            self.canvas.create_text(cw-8, 8,
                text=f"{self.zoom:.1f}x  (double-click = reset)",
                fill="white", font=("Segoe UI", 8, "bold"), anchor="ne")

        # ── Editor overlay: show all page boxes ──────────────────────────────
        if self.edit_mode and self._page_fields:
            for item in self._page_fields:
                b = item.get("bbox")
                if not b or len(b) != 4:
                    continue
                cx0, cy0 = _ic(b[0], b[1]); cx1, cy1 = _ic(b[2], b[3])
                is_sel = item["id"] == self._sel_fid
                is_cur = item["id"] == (self._cur() or {}).get("id")
                color  = "#a78bfa" if is_sel else "#22d3ee" if is_cur else "#64748b"
                width  = 3 if is_sel else 2 if is_cur else 1
                self.canvas.create_rectangle(cx0, cy0, cx1, cy1,
                                             outline=color, width=width)
                self.canvas.create_text(cx0+3, cy0+2,
                    text=item.get("label","?")[:20],
                    fill=color, font=("Segoe UI",7), anchor="nw")
                if is_sel:
                    hs = 7
                    for hx, hy in [(cx0,cy0),(cx1,cy0),(cx0,cy1),(cx1,cy1)]:
                        self.canvas.create_rectangle(
                            hx-hs, hy-hs, hx+hs, hy+hs,
                            fill="#a78bfa", outline="white", width=2)

    # ── Actions ─────────────────────────────────────────────────────────────────

    def _cur(self):
        return self.visible[self.idx] if 0 <= self.idx < len(self.visible) else None

    def confirm(self):
        item = self._cur()
        if not item or not item["flags"]: return
        fid = item["id"]
        # Update locally and navigate on immediately
        save = (list(item["flags"]), item["has_err"], item["has_wrn"], item["status"])
        item["flags"] = []; item["has_err"] = False
        item["has_wrn"] = False; item["status"] = "confirmed"
        self._update_lb(self.idx); self.next_field()
        def _bg():
            r = api(f"/api/v1/fields/{fid}", method="PATCH",
                    body={"action":"confirm","actor":"reviewer"})
            if not r:  # Revert on error
                item["flags"],item["has_err"],item["has_wrn"],item["status"] = save
                self.root.after(0, lambda: self._update_lb(self.idx))
        threading.Thread(target=_bg, daemon=True).start()

    def correct(self):
        item = self._cur()
        if not item: return
        old  = item["value"]
        code = item["flags"][0]["code"] if item["flags"] else ""
        title, _ = INFO.get(code, (code,""))
        new = sd.askstring("Correct",
            f"Page {item['page']}  —  {item['label']}\n\n"
            f"{title}\n\nCurrent value: {old}\n\nCorrect value:",
            parent=self.root, initialvalue=old)
        if not new or not new.strip() or new.strip() == old: return
        fid = item["id"]; new_val = new.strip()
        old_v = item["value"]; save = (list(item["flags"]),item["has_err"],item["has_wrn"],item["status"])
        item["value"] = new_val; item["flags"] = []
        item["has_err"] = False; item["has_wrn"] = False; item["status"] = "corrected"
        self._update_lb(self.idx); self.next_field()
        def _bg():
            r = api(f"/api/v1/fields/{fid}", method="PATCH",
                    body={"action":"correct","value":new_val,"actor":"reviewer"})
            if not r:
                item["value"] = old_v
                item["flags"],item["has_err"],item["has_wrn"],item["status"] = save
                self.root.after(0, lambda: self._update_lb(self.idx))
        threading.Thread(target=_bg, daemon=True).start()

    def next_field(self):
        if not self.visible: return
        n = self.idx + 1
        if n >= len(self.visible):
            if not self._done_shown:
                self._done_shown = True
                rem = sum(1 for i in self.visible if i["flags"])
                mb.showinfo("Pass complete",
                    f"All {len(self.visible)} fields seen.\n"
                    f"{rem} still flagged.\n\nStarting over from the top.")
            self._go(0)
        else:
            self._done_shown = False; self._go(n)

    def prev_field(self):
        self._go(max(0, self.idx-1))

    def _go(self, idx):
        idx = max(0, min(idx, len(self.visible)-1))
        self.lb.selection_clear(0,"end")
        self.lb.selection_set(idx); self.lb.see(idx)
        self._show(idx)
        self.root.focus_set()   # Focus back so shortcuts work immediately

    def _update_lb(self, vi):
        if not (0 <= vi < len(self.visible)): return
        v = self.visible[vi]
        if   v["has_err"]: icon,fg = "X",C["red"]
        elif v["has_wrn"]: icon,fg = "!",C["yel"]
        elif v["status"] in ("confirmed","corrected","auto_accepted"):
                           icon,fg = "v",C["grn"]
        else:              icon,fg = "-",C["dim"]
        code  = v["flags"][0]["code"] if v["flags"] else ""
        short = code.replace("4EYES_","4A:").replace("CALC_","C:").replace("RANGE_","R:")
        txt   = f" {icon}  p{v['page']:<3} {v['label'][:22]}"
        if code: txt += f"  {short}"
        self.lb.delete(vi); self.lb.insert(vi, txt)
        self.lb.itemconfig(vi, fg=fg)
        # Update counter
        rem = sum(1 for i in self.visible if i["flags"])
        self.lbl_count.config(text=f"{rem} to review" if rem else "All reviewed! ✓")
        self._update_review_progress()

    # ── Load new batch ─────────────────────────────────────────────────────────

    def _load_new_batch(self):
        import tkinter.filedialog as fd
        path = fd.askopenfilename(
            title="Select extracted_fields.json",
            filetypes=[("JSON","*.json"),("All","*.*")],
            initialdir=str(ROOT/"results"))
        if not path: return
        def _bg():
            self.root.after(0, lambda: self._set_status("Importing...", C["yel"]))
            result = subprocess.run(
                [str(VENV_PY), str(ROOT/"load_results.py"), "--file", path],
                capture_output=True, timeout=120)
            if result.returncode == 0:
                self.root.after(0, lambda: (
                    self._set_status("Imported!", C["grn"]),
                    self._load_docs()))
            else:
                self.root.after(0, lambda: self._set_status("Import failed!", C["red"]))
        threading.Thread(target=_bg, daemon=True).start()

    # ── Extras ────────────────────────────────────────────────────────────────

    def _toggle_fs(self):
        self._fullscreen = not self._fullscreen
        self.root.attributes("-fullscreen", self._fullscreen)

    def _exit_fs(self):
        if self._fullscreen:
            self._fullscreen = False
            self.root.attributes("-fullscreen", False)

    def _open_table(self):
        win = tk.Toplevel(self.root)
        win.title("BioDize -- All Fields"); win.geometry("1100x600")
        win.configure(bg=C["bg"])
        style = ttk.Style(win); style.theme_use("clam")
        style.configure("T.Treeview", background=C["side"], foreground=C["fg"],
                        rowheight=22, fieldbackground=C["side"], font=("Segoe UI",9))
        style.configure("T.Treeview.Heading", background=C["hdr"], foreground=C["fg"],
                        font=("Segoe UI",9,"bold"))
        style.map("T.Treeview", background=[("selected",C["sel"])])
        bar = tk.Frame(win,bg=C["hdr"],height=36); bar.pack(fill="x"); bar.pack_propagate(False)
        tk.Button(bar, text="Save as CSV", bg="#1e40af", fg="white",
                  relief="flat", bd=0, padx=10, pady=6, cursor="hand2",
                  font=("Segoe UI",8,"bold"),
                  command=lambda: subprocess.Popen(
                      [str(VENV_PY), str(ROOT/"export_csv.py")],
                      creationflags=subprocess.CREATE_NEW_CONSOLE)
                  ).pack(side="right", padx=8, pady=4)
        cols = ("Page","Chapter","Field","Value","Status","Code","Severity")
        tv = ttk.Treeview(win, columns=cols, show="headings",
                          style="T.Treeview", selectmode="browse")
        for col,w in zip(cols,[55,80,230,180,130,180,80]):
            tv.heading(col,text=col); tv.column(col,width=w,minwidth=40)
        tv.tag_configure("err",background=C["err"],foreground=C["red"])
        tv.tag_configure("wrn",background=C["wrn"],foreground=C["yel"])
        tv.tag_configure("ok", background=C["ok"], foreground=C["grn"])
        vsb=ttk.Scrollbar(win,orient="vertical",command=tv.yview)
        hsb=ttk.Scrollbar(win,orient="horizontal",command=tv.xview)
        tv.configure(yscrollcommand=vsb.set,xscrollcommand=hsb.set)
        vsb.pack(side="right",fill="y"); hsb.pack(side="bottom",fill="x")
        tv.pack(fill="both",expand=True)
        for item in self.items:
            flags=item["flags"]
            code="; ".join(fl["code"] for fl in flags)
            sev="Error" if item["has_err"] else "Warning" if item["has_wrn"] else ""
            tag="err" if item["has_err"] else "wrn" if item["has_wrn"] else "ok"
            tv.insert("","end",values=(item["page"],item["chapter"],
                item["label"][:40],item["value"][:30],
                STATUS_DE.get(item["status"],item["status"]),code,sev),tags=(tag,))

    def _open_debugger(self):
        subprocess.Popen([str(VENV_PY), str(ROOT/"debugger.py")],
                         creationflags=subprocess.CREATE_NEW_CONSOLE)

    def _open_gt(self):
        GtWindow(self.root)

    def _open_analytics(self):
        if not self.items:
            mb.showinfo("Analytics", "No data loaded yet.", parent=self.root)
            return
        doc_no = self.docs[self.doc_menu.current()].get("doc_no", "?") \
                 if 0 <= self.doc_menu.current() < len(self.docs) else "?"
        AnalyticsWindow(self.root, self.items, doc_no)

    def _open_deviation_report(self):
        if not self.items:
            mb.showinfo("Deviation Report", "No data loaded yet.", parent=self.root)
            return
        doc_no = self.docs[self.doc_menu.current()].get("doc_no", "?") \
                 if 0 <= self.doc_menu.current() < len(self.docs) else "?"
        DeviationReportGenerator(self.root, self.items, doc_no)


# ── Ground-Truth-Fenster ──────────────────────────────────────────────────────

class GtWindow(tk.Toplevel):
    """Shows ground-truth evaluation results and allows recomputation."""

    GT_DIR   = ROOT / "ground_truth"
    RESULT_F = ROOT / "ground_truth" / "eval_result.json"
    METRIC_LABELS = {
        "rule_precision": "Rule Precision",
        "rule_recall":    "Rule Recall",
        "rule_f1":        "Rule F1",
        "coverage":       "Field Coverage",
        "value_acc":      "Value Accuracy",
        "checkbox_acc":   "Checkbox Accuracy",
        "signature_acc":  "Signature Accuracy",
    }
    METRIC_TARGETS = {
        "rule_precision": 0.90, "rule_recall": 0.80, "rule_f1": 0.85,
        "coverage": 0.90, "value_acc": 0.80,
        "checkbox_acc": 0.75, "signature_acc": 0.90,
    }

    def __init__(self, parent):
        super().__init__(parent)
        self.title("BioDize -- Ground-Truth Evaluation")
        self.configure(bg=C["bg"]); self.geometry("860x640")
        self.resizable(True, True)
        self._build()
        self._load_result()

    def _build(self):
        # Header
        hdr = tk.Frame(self, bg=C["hdr"], height=44); hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="Ground-Truth Evaluation",
                 font=("Segoe UI",13,"bold"), bg=C["hdr"], fg=C["fg"]
                 ).pack(side="left", padx=14, pady=10)
        tk.Button(hdr, text="Recompute", font=("Segoe UI",8,"bold"),
                  bg="#7c3aed", fg="white", activebackground="#6d28d9",
                  relief="flat", bd=0, padx=10, pady=5, cursor="hand2",
                  command=self._recompute, takefocus=False
                  ).pack(side="right", padx=12)
        self.lbl_ts = tk.Label(hdr, text="", font=("Segoe UI",8),
                               bg=C["hdr"], fg=C["dim"])
        self.lbl_ts.pack(side="right", padx=8)

        # Aggregated metrics (top)
        agg_frame = tk.Frame(self, bg=C["side"]); agg_frame.pack(fill="x", padx=16, pady=(12,4))
        tk.Label(agg_frame, text="Overall Metrics",
                 font=("Segoe UI",9,"bold"), bg=C["side"], fg=C["dim"],
                 anchor="w").pack(fill="x", padx=12, pady=(8,4))

        self.agg_cards = tk.Frame(agg_frame, bg=C["side"])
        self.agg_cards.pack(fill="x", padx=12, pady=(0,10))

        # Per-page table (middle)
        pg_frame = tk.Frame(self, bg=C["side"]); pg_frame.pack(fill="both", expand=True, padx=16, pady=(0,4))
        tk.Label(pg_frame, text="Results per Gold Page",
                 font=("Segoe UI",9,"bold"), bg=C["side"], fg=C["dim"],
                 anchor="w").pack(fill="x", padx=12, pady=(8,4))

        style = ttk.Style(self); style.theme_use("clam")
        style.configure("GT.Treeview", background=C["bg"], foreground=C["fg"],
                        rowheight=24, fieldbackground=C["bg"], font=("Segoe UI",9))
        style.configure("GT.Treeview.Heading", background=C["hdr"],
                        foreground=C["fg"], font=("Segoe UI",9,"bold"))
        style.map("GT.Treeview", background=[("selected",C["sel"])])

        cols = ("Page","Section","Status","Precision","Recall","Coverage","Value","Checkbox","Sig","FN","FP")
        self.tv = ttk.Treeview(pg_frame, columns=cols, show="headings",
                               style="GT.Treeview", selectmode="browse")
        widths = [50,220,60,75,75,75,65,75,55,120,120]
        for col,w in zip(cols,widths):
            self.tv.heading(col, text=col); self.tv.column(col, width=w, minwidth=40)
        self.tv.tag_configure("pass",  background="#052e16", foreground=C["grn"])
        self.tv.tag_configure("fail",  background="#450a0a", foreground=C["red"])
        self.tv.tag_configure("warn",  background="#422006", foreground=C["yel"])
        self.tv.bind("<<TreeviewSelect>>", self._on_row_select)

        vsb = ttk.Scrollbar(pg_frame, orient="vertical",   command=self.tv.yview)
        hsb = ttk.Scrollbar(pg_frame, orient="horizontal", command=self.tv.xview)
        self.tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y"); hsb.pack(side="bottom", fill="x")
        self.tv.pack(fill="both", expand=True, padx=(12,0), pady=(0,6))

        # Detail panel (bottom)
        det_frame = tk.Frame(self, bg=C["side"], height=130); det_frame.pack(fill="x", padx=16, pady=(0,12)); det_frame.pack_propagate(False)
        tk.Label(det_frame, text="Detail (select a page)",
                 font=("Segoe UI",9,"bold"), bg=C["side"], fg=C["dim"],
                 anchor="w").pack(fill="x", padx=12, pady=(8,4))
        self.det_text = tk.Text(det_frame, bg=C["bg"], fg=C["fg"],
                                font=("Consolas",8), relief="flat", bd=0,
                                height=6, state="disabled", wrap="none")
        ds = ttk.Scrollbar(det_frame, command=self.det_text.yview)
        self.det_text.configure(yscrollcommand=ds.set)
        ds.pack(side="right", fill="y")
        self.det_text.pack(fill="both", expand=True, padx=(12,0), pady=(0,8))

    # ── Laden ─────────────────────────────────────────────────────────────────

    def _load_result(self):
        if not self.RESULT_F.exists():
            self._show_no_result()
            return
        try:
            data = json.loads(self.RESULT_F.read_text(encoding="utf-8"))
        except Exception as e:
            self._show_no_result(str(e)); return

        import os
        mtime = os.path.getmtime(self.RESULT_F)
        import datetime
        ts = datetime.datetime.fromtimestamp(mtime).strftime("%d.%m.%Y %H:%M")
        self.lbl_ts.config(text=f"Last computed: {ts}")

        self._render_agg(data.get("aggregate", {}))
        self._render_pages(data.get("pages", []))

    def _show_no_result(self, err=""):
        for w in self.agg_cards.winfo_children(): w.destroy()
        tk.Label(self.agg_cards,
                 text=f"No results available.\n{err}\nPlease click 'Recompute'.",
                 font=("Segoe UI",10), bg=C["side"], fg=C["yel"],
                 justify="center").pack(pady=20)

    def _render_agg(self, agg: dict):
        for w in self.agg_cards.winfo_children(): w.destroy()
        for key, label in self.METRIC_LABELS.items():
            val = agg.get(key)
            if val is None: continue
            target = self.METRIC_TARGETS.get(key, 0.0)
            pct    = f"{val:.1%}"
            color  = C["grn"] if val >= target else C["yel"] if val >= target*0.85 else C["red"]
            card   = tk.Frame(self.agg_cards, bg=C["bg"], padx=8, pady=6)
            card.pack(side="left", padx=(0,8), pady=2)
            tk.Label(card, text=label, font=("Segoe UI",7), bg=C["bg"],
                     fg=C["dim"]).pack()
            tk.Label(card, text=pct, font=("Segoe UI",14,"bold"),
                     bg=C["bg"], fg=color).pack()
            tk.Label(card, text=f"Target: {target:.0%}", font=("Segoe UI",6),
                     bg=C["bg"], fg=C["dim"]).pack()

    def _render_pages(self, pages: list):
        self.tv.delete(*self.tv.get_children())
        self._page_data = pages
        for p in pages:
            fn = p.get("fn",[]); fp = p.get("fp",[])
            has_fn = bool(fn); has_fp = bool(fp)
            status = "PASS" if not has_fn and not has_fp else "FAIL"
            tag    = "pass" if status=="PASS" else "fail"
            prec   = f"{p.get('rule_precision',0):.0%}"
            rec    = f"{p.get('rule_recall',0):.0%}"
            if p.get("coverage") is not None:
                cov = f"{p.get('coverage'):.0%}"
            else:
                total = p.get("covered", 0) + p.get("missing", 0)
                cov = f"{(p.get('covered', 0) / total):.0%}" if total else "—"
            val    = f"{p.get('value_correct',0)}/{p.get('value_correct',0)+p.get('value_wrong',0)}"
            cb_c   = p.get("cb_correct",0); cb_w = p.get("cb_wrong",0)
            cb     = f"{cb_c}/{cb_c+cb_w}" if cb_c+cb_w else "—"
            sig_c  = p.get("sig_correct",0); sig_w = p.get("sig_wrong",0)
            sig    = f"{sig_c}/{sig_c+sig_w}" if sig_c+sig_w else "—"
            fn_str = ", ".join(fn) if fn else ""
            fp_str = ", ".join(fp) if fp else ""
            sect   = p.get("section","")[:35]
            self.tv.insert("","end", iid=str(p["page"]),
                           values=(f"p{p['page']:02d}", sect, status,
                                   prec, rec, cov, val, cb, sig,
                                   fn_str, fp_str),
                           tags=(tag,))

    def _on_row_select(self, _=None):
        sel = self.tv.selection()
        if not sel: return
        pg_no = int(sel[0])
        page  = next((p for p in self._page_data if p["page"]==pg_no), None)
        if not page: return
        lines = [f"Page {pg_no}: {page.get('section','')}"]
        if page.get("fn"):   lines.append(f"FN (not detected): {', '.join(page['fn'])}")
        if page.get("fp"):   lines.append(f"FP (wrongly detected): {', '.join(page['fp'])}")
        if page.get("value_details"):
            lines.append("Wrong values:")
            for d in page["value_details"][:5]:
                if d.get("label") != "_extraction_fp":
                    lines.append(f"  {d.get('label','?')[:35]}: Gold={d.get('gold','?')!r}  OCR={d.get('pipeline','?')!r}")
        if page.get("missing"): lines.append(f"Missing fields: {page['missing']}")
        txt = "\n".join(lines)
        self.det_text.configure(state="normal")
        self.det_text.delete("1.0","end"); self.det_text.insert("end",txt)
        self.det_text.configure(state="disabled")

    # ── Neuberechnung ─────────────────────────────────────────────────────────

    def _recompute(self):
        self.lbl_ts.config(text="Computing...", fg=C["yel"])
        for w in self.agg_cards.winfo_children(): w.destroy()
        tk.Label(self.agg_cards, text="Computation running...",
                 font=("Segoe UI",10), bg=C["side"], fg=C["yel"]).pack(pady=20)
        self.tv.delete(*self.tv.get_children())

        def _bg():
            try:
                import os as _os; sys.path.insert(0, str(ROOT/"backend"))
                _os.chdir(str(ROOT/"backend"))
                from app.evaluation.results_loader import document_from_results
                from app.evaluation.scorer import score_ground_truth
                import json as _json

                results_f = ROOT/"results"/"extracted_fields.json"
                if not results_f.exists():
                    self.after(0, lambda: self.lbl_ts.config(
                        text="results/extracted_fields.json missing!", fg=C["red"]))
                    return

                doc = document_from_results(results_f, model_name="eval")
                report = score_ground_truth(doc, ROOT/"ground_truth")
                result = report.as_dict()
                # Save
                (ROOT/"ground_truth"/"eval_result.json").write_text(
                    _json.dumps(result,indent=2), encoding="utf-8")
                self.after(0, lambda: self._load_result())
            except Exception as e:
                self.after(0, lambda: self.lbl_ts.config(
                    text=f"Error: {e}", fg=C["red"]))

        threading.Thread(target=_bg, daemon=True).start()


# ══════════════════════════════════════════════════════════════════════════════
# NEW FEATURE CLASSES
# ══════════════════════════════════════════════════════════════════════════════

def _levenshtein(a: str, b: str) -> int:
    """Classic edit distance between two strings."""
    a = a or ""; b = b or ""
    if a == b: return 0
    if not a:  return len(b)
    if not b:  return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur.append(min(prev[j] + 1, cur[j-1] + 1, prev[j-1] + cost))
        prev = cur
    return prev[-1]


def _parse_num(s):
    """Extract a float from a messy string ('12,5 g' -> 12.5). None if no number."""
    if s is None: return None
    import re
    txt = str(s).replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", txt)
    return float(m.group()) if m else None


def _fmt_num(v):
    """Format a float without trailing zeros."""
    if v is None: return ""
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    return f"{v:.4f}".rstrip("0").rstrip(".")


def _correct_year(value: str, ref_year: int = 2026):
    """If the value contains a 4-digit year 1-2 digits different from ref_year,
    return the value with the year replaced by ref_year. Else None."""
    import re
    if not value: return None
    out = value; changed = False
    for m in re.finditer(r"\b(\d{4})\b", value):
        yr = int(m.group(1))
        if yr == ref_year:
            continue
        diff = sum(1 for x, y in zip(f"{yr:04d}", f"{ref_year:04d}") if x != y)
        if 1 <= diff <= 2:
            out = out.replace(m.group(1), str(ref_year), 1)
            changed = True
    return out if changed else None


class SmartCorrectionsPanel:
    """Collapsible panel below the error banner that computes and offers a
    suggested correction for the currently shown flagged field.

    Confidence levels:
      HIGH   -- exact formula match (calculations, year fix)
      MEDIUM -- fuzzy match (closest signer)
      LOW    -- heuristic (format / range hints)
    """

    def __init__(self, parent, app):
        self.app = app
        self._suggestion = None
        self._field = None
        self.frame = tk.Frame(parent, bg="#052e16", highlightthickness=1,
                              highlightbackground="#166534")
        # Not packed yet -- shown only when a suggestion exists
        self.icon = tk.Label(self.frame, text="\U0001F4A1", bg="#052e16",
                             fg="#4ade80", font=("Segoe UI", 11))
        self.icon.pack(side="left", padx=(10, 4), pady=4)
        self.lbl = tk.Label(self.frame, text="", bg="#052e16", fg="#dcfce7",
                            font=("Segoe UI", 9, "bold"), anchor="w",
                            justify="left")
        self.lbl.pack(side="left", fill="x", expand=True, padx=4, pady=4)
        self.lbl_conf = tk.Label(self.frame, text="", bg="#052e16",
                                 font=("Segoe UI", 8, "bold"))
        self.lbl_conf.pack(side="right", padx=(4, 8))
        self.btn_apply = tk.Button(self.frame, text="Apply", font=("Segoe UI", 9, "bold"),
                                   bg="#166534", fg="white", activebackground="#14532d",
                                   relief="flat", bd=0, padx=14, pady=4, cursor="hand2",
                                   command=self._apply, takefocus=False)
        self.btn_apply.pack(side="right", padx=4, pady=4)

    # ── Public API ────────────────────────────────────────────────────────────

    def update_for(self, item):
        self._field = item
        sug = self._compute(item) if item and item.get("flags") else None
        self._suggestion = sug
        if not sug:
            self.frame.pack_forget()
            return
        value, conf, text = sug
        cols = {"HIGH": "#4ade80", "MEDIUM": "#fbbf24", "LOW": "#f87171"}
        self.lbl.config(text=text)
        self.lbl_conf.config(text=f"{conf} confidence", fg=cols.get(conf, "#dcfce7"))
        # Apply button only makes sense if we have a concrete value
        if value is None:
            self.btn_apply.pack_forget()
        else:
            if not self.btn_apply.winfo_ismapped():
                self.btn_apply.pack(side="right", padx=4, pady=4)
        self.frame.pack(fill="x", padx=6, pady=(0, 2), after=self.app.banner)

    # ── Suggestion engine ─────────────────────────────────────────────────────

    def _compute(self, item):
        """Returns (value_or_None, confidence, display_text) or None."""
        flags = item.get("flags", [])
        if not flags:
            return None
        fl   = flags[0]
        code = fl.get("code", "")
        exp  = fl.get("expected", "")
        act  = fl.get("actual", "")
        val  = item.get("value", "")

        if code in ("DATE_BEFORE_PRINT", "DATE_FAR_FUTURE"):
            fixed = _correct_year(val, 2026)
            if fixed:
                return (fixed, "HIGH", f"Suggested year fix: {val}  ->  {fixed}")
            return (None, "LOW", "Possible OCR year error -- check the scan year (e.g. 2016 -> 2026).")

        if code in ("KUERZEL_UNKNOWN", "KUERZEL_UNRESOLVED"):
            cur = (val or act or "").strip().lower()
            if cur:
                best = min(CANONICAL_SIGNERS,
                           key=lambda s: _levenshtein(cur, s))
                dist = _levenshtein(cur, best)
                conf = "HIGH" if dist <= 1 else "MEDIUM" if dist <= 2 else "LOW"
                return (best, conf,
                        f"Closest registered signer: '{best}'  (from '{cur}', distance {dist})")
            return (None, "LOW", "Unknown initials -- read from scan and match to ohs / han.")

        if code == "CALC_NET_MASS":
            gross = tare = None
            if exp:
                # expected may already carry the right value
                ev = _parse_num(exp)
                if ev is not None:
                    return (_fmt_num(ev), "HIGH", f"Expected net mass: {_fmt_num(ev)} (gross - tare)")
            return (None, "MEDIUM", "Expected: gross - tare. Read gross and tare from the scan.")

        if code == "CALC_VOLUME":
            if exp:
                ev = _parse_num(exp)
                if ev is not None:
                    return (_fmt_num(ev), "HIGH", f"Expected volume: {_fmt_num(ev)} (net / density)")
            return (None, "MEDIUM", "Expected: net / density. Read net mass and density from the scan.")

        if code in ("CALC_FORMULA", "CALC_ROUNDING", "RANGE_SETPOINT",
                    "XREF_CARRIED_MATCH", "XREF_MISMATCH", "XREF_NEAR_MISS"):
            if exp:
                return (str(exp), "HIGH", f"Expected: {exp}")
            return (None, "LOW", "Compare against the source/setpoint value on the scan.")

        if code == "FMT_DATE_PADDING":
            fixed = self._pad_date(val)
            if fixed and fixed != val:
                return (fixed, "HIGH", f"Corrected format: {val}  ->  {fixed}")
            if exp:
                return (str(exp), "MEDIUM", f"Expected format: {exp} (DD.MM.YYYY)")
            return (None, "LOW", "Format must be DD.MM.YYYY (e.g. 01.06.2026).")

        if code == "FMT_NKS":
            if exp:
                return (str(exp), "MEDIUM", f"Expected (decimal places): {exp}")
            return (None, "LOW", "Adjust the number of decimal places to the specification.")

        if code == "RANGE_SOLL":
            return (None, "LOW", f"Out of range: {act or val} (limit: {exp})")

        if code == "SIG_INCOMPLETE":
            return (None, "LOW", "Missing: date or Kuerzel (initials).")

        # Generic fallback when an expected value is present
        if exp:
            return (str(exp), "MEDIUM", f"Expected: {exp}")
        return None

    @staticmethod
    def _pad_date(val):
        """Zero-pad a D.M.YYYY style date to DD.MM.YYYY."""
        import re
        if not val: return None
        m = re.match(r"\s*(\d{1,2})\.(\d{1,2})\.(\d{2,4})\s*$", val)
        if not m: return None
        d, mo, y = m.groups()
        if len(y) == 2: y = "20" + y
        return f"{int(d):02d}.{int(mo):02d}.{int(y):04d}"

    # ── Apply ─────────────────────────────────────────────────────────────────

    def _apply(self):
        if not self._suggestion or not self._field:
            return
        value, _conf, _text = self._suggestion
        if value is None:
            return
        item = self._field
        fid  = item["id"]
        save = (item.get("value"), list(item["flags"]),
                item["has_err"], item["has_wrn"], item["status"])
        # Optimistic local update
        item["value"] = value; item["flags"] = []
        item["has_err"] = False; item["has_wrn"] = False; item["status"] = "corrected"
        app = self.app
        app._update_lb(app.idx)
        self.frame.pack_forget()
        app.next_field()

        def _bg():
            r = api(f"/api/v1/fields/{fid}", method="PATCH",
                    body={"action": "correct", "value": value, "actor": "reviewer"})
            if not r:
                (item["value"], item["flags"], item["has_err"],
                 item["has_wrn"], item["status"]) = save
                app.root.after(0, lambda: app._update_lb(app.idx))
        threading.Thread(target=_bg, daemon=True).start()


class AnalyticsWindow(tk.Toplevel):
    """Cross-batch analytics dashboard drawn entirely with tk.Canvas."""

    def __init__(self, parent, items, doc_no):
        super().__init__(parent)
        self.items  = items
        self.doc_no = doc_no
        self.title(f"BioDize -- Analytics ({doc_no})")
        self.configure(bg=C["bg"]); self.geometry("1000x720")
        self.minsize(800, 560)
        self._compute_stats()
        self._build()

    # ── Stats ─────────────────────────────────────────────────────────────────

    def _compute_stats(self):
        from collections import Counter
        self.flag_counts = Counter()
        self.page_err    = Counter()   # error count per page
        self.page_wrn    = Counter()
        self.operator    = Counter()   # signer initials on flagged fields
        self.n_err = self.n_wrn = 0
        import re
        for it in self.items:
            for fl in it.get("flags", []):
                self.flag_counts[fl.get("code", "?")] += 1
                if fl.get("severity") == "error":
                    self.page_err[it["page"]] += 1; self.n_err += 1
                else:
                    self.page_wrn[it["page"]] += 1; self.n_wrn += 1
            if it.get("flags"):
                # crude signer detection: short alpha tokens in value
                for tok in re.findall(r"[A-Za-z]{2,4}", str(it.get("value", ""))):
                    low = tok.lower()
                    if low in CANONICAL_SIGNERS or len(low) <= 3:
                        self.operator[low] += 1
        self.all_pages = sorted({it["page"] for it in self.items})
        # Quality score: 100 - (errors*5 + warnings*2), clamped 0-100
        self.quality = max(0, min(100, 100 - (self.n_err * 5 + self.n_wrn * 2)))

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build(self):
        hdr = tk.Frame(self, bg=C["hdr"], height=46); hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text=f"Analytics Dashboard  —  {self.doc_no}",
                 font=("Segoe UI", 13, "bold"), bg=C["hdr"], fg=C["fg"]
                 ).pack(side="left", padx=14, pady=10)
        tk.Button(hdr, text="Export Report (CSV)", font=("Segoe UI", 8, "bold"),
                  bg="#0e7490", fg="white", activebackground="#155e75",
                  relief="flat", bd=0, padx=12, pady=6, cursor="hand2",
                  command=self._export_csv, takefocus=False).pack(side="right", padx=12)

        # Quality score card
        card = tk.Frame(self, bg=C["side"]); card.pack(fill="x", padx=16, pady=(12, 6))
        qcol = (C["grn"] if self.quality >= 80 else
                C["yel"] if self.quality >= 50 else C["red"])
        tk.Label(card, text="QUALITY SCORE", font=("Segoe UI", 8, "bold"),
                 bg=C["side"], fg=C["dim"]).pack(side="left", padx=(14, 8), pady=10)
        tk.Label(card, text=f"{self.quality}", font=("Segoe UI", 26, "bold"),
                 bg=C["side"], fg=qcol).pack(side="left", pady=6)
        tk.Label(card, text="/ 100", font=("Segoe UI", 10),
                 bg=C["side"], fg=C["dim"]).pack(side="left", padx=(2, 16), pady=14)
        tk.Label(card,
                 text=f"{self.n_err} errors    {self.n_wrn} warnings    "
                      f"{len(self.all_pages)} pages    {len(self.items)} fields",
                 font=("Segoe UI", 10), bg=C["side"], fg=C["fg"]).pack(side="left", padx=8)

        # Two columns of canvases
        body = tk.Frame(self, bg=C["bg"]); body.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        col_l = tk.Frame(body, bg=C["bg"]); col_l.pack(side="left", fill="both", expand=True, padx=(0, 8))
        col_r = tk.Frame(body, bg=C["bg"]); col_r.pack(side="left", fill="both", expand=True, padx=(8, 0))

        self._chart_frame(col_l, "Error Distribution (by flag code)",
                          self._draw_distribution, height=260)
        self._chart_frame(col_l, "Operator Analysis (signers on flagged pages)",
                          self._draw_operators, height=200)
        self._chart_frame(col_r, "Page Heatmap (error count per page)",
                          self._draw_heatmap, height=470)

    def _chart_frame(self, parent, title, draw_fn, height):
        f = tk.Frame(parent, bg=C["side"]); f.pack(fill="both", expand=True, pady=(0, 10))
        tk.Label(f, text=title, font=("Segoe UI", 9, "bold"),
                 bg=C["side"], fg=C["dim"], anchor="w").pack(fill="x", padx=10, pady=(8, 2))
        cv = tk.Canvas(f, bg=C["bg"], height=height, highlightthickness=0)
        cv.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        cv.bind("<Configure>", lambda e, c=cv, fn=draw_fn: fn(c))

    # ── Charts ────────────────────────────────────────────────────────────────

    def _draw_distribution(self, cv):
        cv.delete("all")
        w = cv.winfo_width(); h = cv.winfo_height()
        if w < 20 or h < 20: return
        data = self.flag_counts.most_common()
        if not data:
            cv.create_text(w//2, h//2, text="No flags", fill=C["dim"],
                           font=("Segoe UI", 11)); return
        mx = max(c for _, c in data)
        n  = len(data)
        pad_l = 170; pad_r = 50; pad_t = 10; pad_b = 10
        avail_h = h - pad_t - pad_b
        bar_h = min(26, avail_h / n)
        gap   = bar_h * 0.3
        y = pad_t
        bar_w_max = w - pad_l - pad_r
        for code, count in data:
            sev_col = "#f87171" if code in INFO else "#60a5fa"
            bw = max(2, int(bar_w_max * count / mx))
            cv.create_text(pad_l - 8, y + bar_h/2, text=code[:24], anchor="e",
                           fill=C["fg"], font=("Segoe UI", 8))
            cv.create_rectangle(pad_l, y, pad_l + bw, y + bar_h,
                                fill=sev_col, outline="")
            cv.create_text(pad_l + bw + 6, y + bar_h/2, text=str(count),
                           anchor="w", fill=C["fg"], font=("Segoe UI", 8, "bold"))
            y += bar_h + gap

    def _draw_heatmap(self, cv):
        cv.delete("all")
        w = cv.winfo_width(); h = cv.winfo_height()
        if w < 20 or h < 20: return
        pages = self.all_pages
        if not pages:
            cv.create_text(w//2, h//2, text="No pages", fill=C["dim"],
                           font=("Segoe UI", 11)); return
        cols = max(1, min(6, w // 110))
        pad = 10
        cell = (w - pad*2) // cols
        cell = max(60, min(cell, 120))
        mx_err = max([self.page_err[p] for p in pages] + [1])
        x = pad; y = pad
        col_i = 0
        for pg in pages:
            ec = self.page_err[pg]; wc = self.page_wrn[pg]
            if ec == 0 and wc == 0:
                fill = "#052e16"; bd = "#166534"
            elif ec == 0:
                fill = "#422006"; bd = "#a16207"
            else:
                # red intensity scaled by error count
                t = ec / mx_err
                r = int(0x45 + t * (0xdc - 0x45))
                fill = f"#{r:02x}0a0a"; bd = "#dc2626"
            cv.create_rectangle(x, y, x + cell - 8, y + cell - 8,
                                fill=fill, outline=bd, width=2)
            cv.create_text(x + (cell-8)/2, y + (cell-8)/2 - 8,
                           text=f"p{pg}", fill=C["fg"], font=("Segoe UI", 11, "bold"))
            cv.create_text(x + (cell-8)/2, y + (cell-8)/2 + 12,
                           text=f"{ec} err / {wc} wrn", fill=C["dim"],
                           font=("Segoe UI", 7))
            col_i += 1; x += cell
            if col_i >= cols:
                col_i = 0; x = pad; y += cell

    def _draw_operators(self, cv):
        cv.delete("all")
        w = cv.winfo_width(); h = cv.winfo_height()
        if w < 20 or h < 20: return
        data = self.operator.most_common(8)
        if not data:
            cv.create_text(w//2, h//2, text="No operators detected on flagged pages",
                           fill=C["dim"], font=("Segoe UI", 10)); return
        mx = max(c for _, c in data)
        n  = len(data)
        pad_l = 90; pad_r = 50; pad_t = 8; pad_b = 8
        bar_h = min(24, (h - pad_t - pad_b) / n)
        gap = bar_h * 0.3
        y = pad_t
        bar_w_max = w - pad_l - pad_r
        for name, count in data:
            bw = max(2, int(bar_w_max * count / mx))
            cv.create_text(pad_l - 8, y + bar_h/2, text=name, anchor="e",
                           fill=C["fg"], font=("Segoe UI", 9))
            cv.create_rectangle(pad_l, y, pad_l + bw, y + bar_h,
                                fill="#fbbf24", outline="")
            cv.create_text(pad_l + bw + 6, y + bar_h/2, text=str(count),
                           anchor="w", fill=C["fg"], font=("Segoe UI", 8, "bold"))
            y += bar_h + gap

    # ── Export ────────────────────────────────────────────────────────────────

    def _export_csv(self):
        import tkinter.filedialog as fd, datetime, csv
        desktop = Path.home() / "Desktop"
        default = f"BioDize_Analytics_{self.doc_no}_{datetime.date.today():%Y%m%d}.csv"
        path = fd.asksaveasfilename(
            parent=self, title="Export analytics report",
            initialdir=str(desktop if desktop.exists() else Path.home()),
            initialfile=default, defaultextension=".csv",
            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                wr = csv.writer(f)
                wr.writerow(["BioDize Analytics Report"])
                wr.writerow(["Document", self.doc_no])
                wr.writerow(["Generated", datetime.datetime.now().isoformat(timespec="seconds")])
                wr.writerow(["Quality Score", self.quality])
                wr.writerow(["Errors", self.n_err, "Warnings", self.n_wrn])
                wr.writerow([])
                wr.writerow(["Flag Distribution"])
                wr.writerow(["Code", "Count"])
                for code, c in self.flag_counts.most_common():
                    wr.writerow([code, c])
                wr.writerow([])
                wr.writerow(["Page Heatmap"])
                wr.writerow(["Page", "Errors", "Warnings"])
                for pg in self.all_pages:
                    wr.writerow([pg, self.page_err[pg], self.page_wrn[pg]])
                wr.writerow([])
                wr.writerow(["Operator Analysis"])
                wr.writerow(["Operator", "Count"])
                for name, c in self.operator.most_common():
                    wr.writerow([name, c])
            mb.showinfo("Export", f"Saved:\n{path}", parent=self)
        except Exception as e:
            mb.showerror("Export", f"Failed: {e}", parent=self)


class DeviationReportGenerator:
    """Generates a GxP-style HTML deviation report from all flagged fields,
    saves it to the desktop, and opens it in the default browser."""

    SEVERITY_RANK = {"error": 0, "warning": 1}

    def __init__(self, parent, items, doc_no):
        self.parent = parent
        self.items  = items
        self.doc_no = doc_no or "unknown"
        self._generate()

    def _category(self, code):
        if code.startswith("CALC"):   return "Calculation"
        if code.startswith("DATE"):   return "Date / Timeline"
        if code.startswith("FMT"):    return "Formatting"
        if code.startswith("RANGE"):  return "Specification Range"
        if code.startswith("4EYES"):  return "Four-Eyes / GMP"
        if code.startswith("KUERZEL") or code.startswith("SIG"): return "Signature"
        if code.startswith("XREF"):   return "Cross-Reference"
        return "Other"

    def _generate(self):
        import datetime, html, webbrowser
        flagged = [it for it in self.items if it.get("flags")]
        if not flagged:
            mb.showinfo("Deviation Report",
                        "No flagged fields -- nothing to report.", parent=self.parent)
            return

        now = datetime.datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        gen_str  = now.strftime("%d.%m.%Y %H:%M")

        # Build rows + grouped stats
        from collections import Counter
        by_sev = Counter(); by_cat = Counter(); by_page = Counter()
        rows = []
        for it in flagged:
            fl   = it["flags"][0]
            sev  = fl.get("severity", "warning")
            code = fl.get("code", "?")
            cat  = self._category(code)
            by_sev[sev] += 1; by_cat[cat] += 1; by_page[it["page"]] += 1
            title, _ = INFO.get(code, (code, ""))
            rows.append(dict(
                page=it["page"], section=it.get("chapter", "") or "—",
                field=it.get("label", "?"), sev=sev, code=code, issue=title,
                expected=fl.get("expected", "") or "—",
                found=fl.get("actual", "") or it.get("value", "") or "—",
                status=STATUS_DE.get(it.get("status", ""), it.get("status", "")),
            ))
        rows.sort(key=lambda r: (self.SEVERITY_RANK.get(r["sev"], 9), r["page"]))

        esc = html.escape
        sum_rows = "".join(
            f"<tr><td>{esc(cat)}</td><td>{cnt}</td></tr>"
            for cat, cnt in by_cat.most_common())
        detail_rows = "".join(
            f'<tr class="{r["sev"]}">'
            f'<td>{r["page"]}</td><td>{esc(str(r["section"]))}</td>'
            f'<td>{esc(str(r["field"]))}</td>'
            f'<td>{esc(r["issue"])} <span class="code">{esc(r["code"])}</span></td>'
            f'<td>{esc(str(r["expected"]))}</td><td>{esc(str(r["found"]))}</td>'
            f'<td>{esc(str(r["status"]))}</td></tr>'
            for r in rows)

        n_err = by_sev.get("error", 0); n_wrn = by_sev.get("warning", 0)
        classification = ("CRITICAL -- contains GMP-relevant errors requiring "
                          "formal deviation handling." if n_err else
                          "MINOR -- warnings only; review and document as appropriate.")

        doc_html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>BioDize Deviation Report {esc(self.doc_no)}</title>
<style>
  body {{ font-family: "Segoe UI", Arial, sans-serif; color:#1f2937;
          background:#f3f4f6; margin:0; padding:0; }}
  .page {{ max-width:1000px; margin:24px auto; background:#fff;
           box-shadow:0 1px 6px rgba(0,0,0,.12); }}
  header {{ background:#0d1117; color:#f1f5f9; padding:24px 32px; }}
  header h1 {{ margin:0 0 6px; font-size:22px; }}
  header .meta {{ font-size:13px; color:#9ca3af; }}
  .band {{ padding:6px 32px; background:#1e40af; color:#fff; font-size:13px;
           font-weight:600; letter-spacing:.5px; }}
  section {{ padding:20px 32px; }}
  h2 {{ font-size:15px; color:#111827; border-bottom:2px solid #e5e7eb;
        padding-bottom:6px; }}
  .cards {{ display:flex; gap:14px; flex-wrap:wrap; margin:8px 0 4px; }}
  .card {{ flex:1; min-width:120px; background:#f9fafb; border:1px solid #e5e7eb;
           border-radius:8px; padding:12px 16px; text-align:center; }}
  .card .num {{ font-size:26px; font-weight:700; }}
  .card .lbl {{ font-size:11px; color:#6b7280; text-transform:uppercase; }}
  .err .num {{ color:#dc2626; }} .wrn .num {{ color:#d97706; }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; margin-top:8px; }}
  th {{ background:#111827; color:#f9fafb; text-align:left; padding:8px 10px;
        font-size:12px; }}
  td {{ padding:7px 10px; border-bottom:1px solid #e5e7eb; vertical-align:top; }}
  tr.error  {{ background:#fef2f2; }}
  tr.warning{{ background:#fffbeb; }}
  tr.error td:first-child  {{ border-left:4px solid #dc2626; }}
  tr.warning td:first-child{{ border-left:4px solid #d97706; }}
  .code {{ font-family:Consolas,monospace; font-size:11px; color:#6b7280; }}
  footer {{ padding:18px 32px; background:#f9fafb; border-top:2px solid #e5e7eb;
            font-size:12px; color:#374151; }}
  .stamp {{ font-weight:700; color:{('#dc2626' if n_err else '#d97706')}; }}
</style></head>
<body><div class="page">
  <header>
    <h1>GxP Deviation Report</h1>
    <div class="meta">
      Document No.: <b>{esc(self.doc_no)}</b> &nbsp;|&nbsp;
      Generated: {esc(gen_str)} &nbsp;|&nbsp;
      Tool: BioDize Eval Reviewer
    </div>
  </header>
  <div class="band">EXECUTIVE SUMMARY</div>
  <section>
    <div class="cards">
      <div class="card err"><div class="num">{n_err}</div><div class="lbl">Errors</div></div>
      <div class="card wrn"><div class="num">{n_wrn}</div><div class="lbl">Warnings</div></div>
      <div class="card"><div class="num">{len(rows)}</div><div class="lbl">Total Findings</div></div>
      <div class="card"><div class="num">{len(by_page)}</div><div class="lbl">Pages Affected</div></div>
    </div>
    <h2>Findings by Category</h2>
    <table><tr><th>Category</th><th>Count</th></tr>{sum_rows}</table>
  </section>
  <div class="band">DETAILED FINDINGS</div>
  <section>
    <table>
      <tr><th>Page</th><th>Section</th><th>Field</th><th>Issue</th>
          <th>Expected</th><th>Found</th><th>Status</th></tr>
      {detail_rows}
    </table>
  </section>
  <footer>
    <p><span class="stamp">GxP Classification: {esc(classification)}</span></p>
    <p>This report was generated automatically from extracted batch-record
       fields and the BioDize rule engine. All findings must be assessed and
       dispositioned by qualified personnel in accordance with the applicable
       GMP quality system (e.g. EU GMP Annex 11 / 21 CFR Part 11). This document
       does not by itself constitute a released deviation record.</p>
    <p>Generated {esc(gen_str)} &nbsp;|&nbsp; Document {esc(self.doc_no)}</p>
  </footer>
</div></body></html>"""

        # Save to desktop
        desktop = Path.home() / "Desktop"
        out_dir = desktop if desktop.exists() else Path.home()
        safe_no = "".join(c if c.isalnum() or c in "-_." else "_"
                          for c in str(self.doc_no))
        out_path = out_dir / f"BioDize_Deviation_Report_{safe_no}_{date_str}.html"
        try:
            out_path.write_text(doc_html, encoding="utf-8")
            webbrowser.open(out_path.as_uri())
            mb.showinfo("Deviation Report",
                        f"Report generated ({len(rows)} findings):\n{out_path}",
                        parent=self.parent)
        except Exception as e:
            mb.showerror("Deviation Report", f"Failed: {e}", parent=self.parent)


# ── Start ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
