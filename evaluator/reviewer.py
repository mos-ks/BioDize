"""
BioDize Pruefer -- Standalone Batch-Review-Tool
================================================
Startet Backend automatisch. Kein manuelles "App starten" noetig.
Fuer mehrere Batches: Dokument-Auswahl oben links.

Start: py reviewer.py
       Doppelklick auf "BioDize Launcher.bat" -> Schritt 3
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

# ── Fehlerbeschreibungen ──────────────────────────────────────────────────────
INFO = {
    "4EYES_DISTINCT":     ("Gleiche Person bearbeitet+geprueft", "Zwei verschiedene Personen erforderlich (GMP)."),
    "4EYES_ORDER":        ("Geprueft vor Bearbeitet",            "Pruefung muss nach Bearbeitung stattfinden."),
    "CALC_NET_MASS":      ("Netto ≠ Brutto - Tara",             "Rechenfehler oder Tippfehler beim Eintragen."),
    "CALC_VOLUME":        ("Volumen falsch",                     "V ≠ Nettomasse × Dichte."),
    "CALC_FORMULA":       ("Formel-Ergebnis falsch",             "Handschriftliches Ergebnis weicht von Rechnung ab."),
    "CALC_ROUNDING":      ("Rundungsabweichung",                 "Minimale Abweichung -- wahrscheinlich Rundung."),
    "RANGE_SOLL":         ("Wert ausserhalb Soll",               "Abweichung! Wert liegt ausserhalb des Sollbereichs."),
    "RANGE_SETPOINT":     ("Sollwert nicht eingehalten",         "Wert entspricht nicht dem Sollwert."),
    "FMT_DATE_PADDING":   ("Datum-Format falsch",                "Format muss TT.MM.JJJJ sein (z.B. 01.06.2026)."),
    "FMT_NKS":            ("Nachkommastellen falsch",            "Anzahl Dezimalstellen stimmt nicht mit Vorgabe."),
    "DATE_BEFORE_PRINT":  ("Datum vor Druckdatum",               "Datum vor Formulardruck. OCR-Jahresfehler? (2016 statt 2026)"),
    "DATE_FAR_FUTURE":    ("Datum zu weit in Zukunft",           "OCR-Jahresfehler? (2028 oder 2076 statt 2026)"),
    "KUERZEL_UNKNOWN":    ("Unbekanntes Kuerzel",                "Kuerzel nicht in Personalliste (Seite 4)."),
    "XREF_CARRIED_MATCH": ("Uebertrag stimmt nicht",             "Uebertrag weicht vom Quellwert ab."),
    "XREF_NEAR_MISS":     ("Uebertrag minimal abweichend",       "Evtl. Rundungsunterschied -- pruefen."),
    "XREF_MISMATCH":      ("Uebertrag stimmt nicht",             "Uebertrag weicht vom Quellwert ab."),
    "EXTRACT_LOW_CONF":   ("OCR unsicher",                       "Texterkennung war unsicher. Scan direkt pruefen."),
}
ACTION = {
    "4EYES_DISTINCT":     "Zweite Person muss gegenzeichnen, oder Bestaetigen wenn bereits erledigt.",
    "4EYES_ORDER":        "Datum pruefen. Bei Jahresfehler (z.B. 2016->2026): Korrigieren.",
    "CALC_NET_MASS":      "Tara + Brutto aus Scan ablesen, Netto = Brutto-Tara rechnen -> Korrigieren.",
    "CALC_VOLUME":        "Scan ansehen. Richtigen Wert Korrigieren oder Bestaetigen.",
    "CALC_FORMULA":       "Formel nachrechnen -> richtiges Ergebnis Korrigieren.",
    "CALC_ROUNDING":      "Scan ansehen. Bei plausibler Rundung: Bestaetigen.",
    "RANGE_SOLL":         "Wert wirklich ausserhalb? Falls ja -> Bestaetigen + Abweichung dok. Falls OCR-Fehler -> Korrigieren.",
    "RANGE_SETPOINT":     "Richtigen Wert aus Scan ablesen -> Korrigieren.",
    "FMT_DATE_PADDING":   "Datum als TT.MM.JJJJ -> Korrigieren (z.B. '01.06.2026').",
    "FMT_NKS":            "Wert mit korrekter Nachkommazahl -> Korrigieren.",
    "DATE_BEFORE_PRINT":  "Jahr pruefen. OCR liest oft 2016 statt 2026 -> Korrigieren.",
    "DATE_FAR_FUTURE":    "Jahr pruefen. OCR liest oft 2028/2076 statt 2026 -> Korrigieren.",
    "KUERZEL_UNKNOWN":    "Kuerzel aus Scan ablesen -> Korrigieren.",
    "XREF_CARRIED_MATCH": "Quellwert und Uebertrag vergleichen -> Korrigieren.",
    "XREF_NEAR_MISS":     "Rundung pruefen. Falls plausibel: Bestaetigen.",
    "XREF_MISMATCH":      "Quellwert und Uebertrag vergleichen -> Korrigieren.",
    "EXTRACT_LOW_CONF":   "Scan ansehen und Wert pruefen -> Bestaetigen oder Korrigieren.",
}
STATUS_DE = {"auto_accepted":"Auto-OK","needs_review":"Zu pruefen",
             "confirmed":"Bestaetigt","corrected":"Korrigiert"}


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
        "confirm": "Bestaetigen",
        "correct": "Wert korrigieren",
        "next":    "Naechstes Feld",
        "prev":    "Vorheriges Feld",
        "filter_flags": "Nur Fehler/Warnungen",
        "filter_all":   "Alle Felder",
    }
    def __init__(self, parent, keys, on_save):
        super().__init__(parent); self.title("Tastenkuerzel")
        self.configure(bg=C["hdr"]); self.resizable(False,False); self.grab_set()
        self._k = dict(keys); self._on_save = on_save; self._wait = None
        self._vars = {}; self._btns = {}
        self._build()

    def _build(self):
        tk.Label(self, text="Taste klicken, dann Taste druecken",
                 bg=C["hdr"], fg=C["dim"], font=("Segoe UI",9)).pack(pady=12)
        g = tk.Frame(self, bg=C["hdr"]); g.pack(padx=20, pady=4)
        for row,(action,label) in enumerate(self.LABELS.items()):
            tk.Label(g, text=label, font=("Segoe UI",10), bg=C["hdr"],
                     fg=C["fg"], width=22, anchor="w").grid(row=row,column=0,pady=4)
            v = tk.StringVar(value=self._k.get(action,"").strip("<>").replace("Return","Enter").replace("space","Leertaste"))
            self._vars[action] = v
            b = tk.Button(g, textvariable=v, font=("Segoe UI",10,"bold"), width=14,
                          bg=C["side"], fg=C["blue"], relief="flat", bd=0,
                          padx=8, pady=6, cursor="hand2")
            b.grid(row=row, column=1, padx=(12,0), pady=4)
            b.bind("<Button-1>", lambda e,a=action: self._start(a))
            self._btns[action] = b
        bar = tk.Frame(self,bg=C["hdr"]); bar.pack(pady=16)
        tk.Button(bar,text="Speichern",bg="#166534",fg="white",relief="flat",bd=0,
                  padx=14,pady=8,cursor="hand2",command=self._save,
                  font=("Segoe UI",10,"bold")).pack(side="left",padx=6)
        tk.Button(bar,text="Standard",bg=C["side"],fg=C["dim"],relief="flat",bd=0,
                  padx=14,pady=8,cursor="hand2",command=self._reset,
                  font=("Segoe UI",10)).pack(side="left",padx=6)
        tk.Button(bar,text="Abbrechen",bg=C["side"],fg=C["dim"],relief="flat",bd=0,
                  padx=14,pady=8,cursor="hand2",command=self.destroy,
                  font=("Segoe UI",10)).pack(side="left",padx=6)

    def _start(self, action):
        if self._wait: return
        self._wait = action
        self._vars[action].set("< Taste druecken >")
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
        self._vars[a].set(bind.strip("<>").replace("Return","Enter").replace("space","Leertaste"))

    def _reset(self):
        self._k = dict(DEFAULT_KEYS)
        for a,v in self._vars.items():
            v.set(DEFAULT_KEYS.get(a,"").strip("<>").replace("Return","Enter").replace("space","Leertaste"))

    def _save(self): self._on_save(self._k); self.destroy()


# ── Haupt-App ─────────────────────────────────────────────────────────────────
class App:
    def __init__(self, root: tk.Tk):
        self.root   = root
        self.root.title("BioDize Pruefer")
        self.root.configure(bg=C["bg"])
        self.root.state("zoomed")
        self.root.minsize(900, 600)

        # Daten
        self.docs:    list[dict] = []
        self.doc_id:  str | None = None
        self.items:   list[dict] = []
        self.visible: list[dict] = []
        self.idx = 0

        # Bild-Cache (alle Seiten im RAM)
        self.pil_cache:   dict[int, Image.Image]          = {}
        self.photo_cache: dict[tuple, ImageTk.PhotoImage] = {}
        self.cur_page: int | None = None
        self.cur_bbox: list | None = None
        self.cur_sev:  str | None = None

        # Zoom-State -- 1.0 = Fit-to-Canvas (schneller Cache-Pfad)
        self.zoom   = 1.0
        self.zoom_x = 0.5
        self.zoom_y = 0.5
        self._pan_last: tuple | None = None

        # Bbox-Editor-State
        self.edit_mode      = False
        self._draw_start:   tuple | None = None
        self._sel_fid:      str   | None = None
        self._page_fields:  list[dict]   = []
        self._drag_bbox:    list  | None = None
        self._drag_mode     = ""
        self._drag_start_c: tuple | None = None
        self._undo_stack:   list[tuple[str, list | None]] = []  # (field_id, old_bbox)

        # UI-State
        self.filter_v = tk.StringVar(value="all")
        self._fullscreen = False
        self._done_shown = False
        self._be_proc: subprocess.Popen | None = None
        self._keys    = self._load_keys()
        self._img_ref = None   # GC-Schutz

        self._build_ui()
        self._bind_keys()
        # Backend sofort starten und verbinden
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
        def fmt(k): return self._keys.get(k,"").strip("<>").replace("Return","Enter").replace("space","Leertaste")
        if hasattr(self,"btn_confirm"):
            self.btn_confirm.config(text=f"Bestaetigen   [{fmt('confirm')}]")
            self.btn_correct.config(text=f"Korrigieren   [{fmt('correct')}]")
            self.btn_next.config(   text=f"Weiter   [{fmt('next')}]")

    # ── Backend auto-starten ──────────────────────────────────────────────────

    def _auto_start_backend(self):
        """Startet das Backend sofort, verbindet sich dann automatisch."""
        def _worker():
            # Pruefen ob Backend schon laeuft
            if api("/health"):
                self.root.after(0, self._on_connected)
                return
            # Backend starten
            self.root.after(0, lambda: self._set_status("Backend startet...", C["yel"]))
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
                "Backend nicht gestartet. Manuell: 'App starten' im Launcher.", C["red"]))
        threading.Thread(target=_worker, daemon=True).start()

    def _on_connected(self):
        self._set_status("Verbunden -- lade Daten...", C["grn"])
        self._load_docs()

    # ── UI aufbauen ───────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Kopfzeile ────────────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=C["hdr"], height=46)
        hdr.pack(fill="x"); hdr.pack_propagate(False)

        tk.Label(hdr, text="BioDize Pruefer",
                 font=("Segoe UI",13,"bold"), bg=C["hdr"], fg=C["fg"]
                 ).pack(side="left", padx=14, pady=8)

        # Dokument-Waehler (fuer mehrere Batches)
        self.doc_var = tk.StringVar(value="Verbinde...")
        self.doc_menu = ttk.Combobox(hdr, textvariable=self.doc_var,
                                     state="readonly", width=40,
                                     font=("Segoe UI",9))
        self.doc_menu.pack(side="left", padx=12)
        self.doc_menu.bind("<<ComboboxSelected>>", lambda e: self._switch_doc())

        tk.Button(hdr, text="+ Laden", font=("Segoe UI",8,"bold"),
                  bg="#7c3aed", fg="white", activebackground="#6d28d9",
                  relief="flat", bd=0, padx=10, pady=5, cursor="hand2",
                  command=self._load_new_batch).pack(side="left", padx=4)

        self.lbl_status = tk.Label(hdr, text="Startet...",
                                   font=("Segoe UI",8), bg=C["hdr"], fg=C["dim"])
        self.lbl_status.pack(side="left", padx=10)

        # Rechte Seite Header
        self.lbl_prog = tk.Label(hdr, text="",
                                 font=("Segoe UI",11,"bold"), bg=C["hdr"], fg=C["blue"])
        self.lbl_prog.pack(side="right", padx=14)

        self.btn_edit = tk.Button(hdr, text="Boxen bearbeiten",
                                  font=("Segoe UI",8,"bold"),
                                  bg="#7c3aed", fg="white",
                                  activebackground="#6d28d9",
                                  relief="flat", bd=0, padx=10, pady=5,
                                  cursor="hand2",
                                  command=self._toggle_edit_mode)
        self.btn_edit.pack(side="right", padx=4)

        for text, cmd in [("Tastenkuerzel", lambda: KeyDialog(self.root,self._keys,self._save_keys)),
                          ("Tabelle (Strg+D)", self._open_table),
                          ("Debugger (Strg+L)", self._open_debugger)]:
            tk.Button(hdr, text=text, font=("Segoe UI",8),
                      bg=C["side"], fg=C["dim"], activebackground=C["sel"],
                      relief="flat", bd=0, padx=8, pady=5, cursor="hand2",
                      command=cmd).pack(side="right", padx=2)

        # ── Filter ───────────────────────────────────────────────────────────
        fbar = tk.Frame(self.root, bg=C["side"], height=30)
        fbar.pack(fill="x"); fbar.pack_propagate(False)

        tk.Label(fbar, text="Zeige:", bg=C["side"], fg=C["dim"],
                 font=("Segoe UI",8)).pack(side="left", padx=10, pady=6)

        for val, lbl, fg in [("all",     "Alle Felder  [A]",        C["dim"]),
                              ("flagged", "Fehler + Warnungen  [F]", C["red"]),
                              ("error",   "Nur Fehler",              C["red"]),
                              ("warning", "Nur Warnungen",           C["yel"])]:
            tk.Radiobutton(fbar, text=lbl, variable=self.filter_v, value=val,
                           command=self._apply_filter, bg=C["side"], fg=fg,
                           selectcolor=C["sel"], activebackground=C["side"],
                           font=("Segoe UI",8), cursor="hand2", relief="flat"
                           ).pack(side="left", padx=8)

        self.lbl_count = tk.Label(fbar, text="", bg=C["side"], fg=C["dim"],
                                  font=("Segoe UI",8))
        self.lbl_count.pack(side="right", padx=12)

        # Editor-Toolbar (standardmaessig versteckt)
        self.edit_bar = tk.Frame(self.root, bg="#1a0a2e", height=36)
        # Wird per _toggle_edit_mode eingeblendet
        self.lbl_edit_hint = tk.Label(self.edit_bar,
            text="BEARBEITUNGSMODUS  |  Feld anklicken: auswaehlen  |  "
                 "Leere Flaeche ziehen: neue Box  |  Box ziehen: verschieben  |  "
                 "Ecken ziehen: Groesse aendern  |  Entf: Box loeschen",
            bg="#1a0a2e", fg="#c4b5fd", font=("Segoe UI",8))
        self.lbl_edit_hint.pack(side="left", padx=12, pady=8)

        self.btn_save_bbox = tk.Button(self.edit_bar, text="Alle Boxen speichern",
            font=("Segoe UI",8,"bold"), bg="#166534", fg="white",
            activebackground="#14532d", relief="flat", bd=0,
            padx=12, pady=5, cursor="hand2",
            command=self._save_all_bboxes)
        self.btn_save_bbox.pack(side="right", padx=8)

        self.btn_del_bbox = tk.Button(self.edit_bar, text="Box loeschen [Entf]",
            font=("Segoe UI",8), bg="#7f1d1d", fg="white",
            activebackground="#991b1b", relief="flat", bd=0,
            padx=12, pady=5, cursor="hand2",
            command=self._delete_sel_bbox)
        self.btn_del_bbox.pack(side="right", padx=4)

        self.lbl_sel_field = tk.Label(self.edit_bar, text="Kein Feld ausgewaehlt",
            bg="#1a0a2e", fg="#a78bfa", font=("Segoe UI",8,"bold"))
        self.lbl_sel_field.pack(side="right", padx=12)

        # ── Hauptbereich ─────────────────────────────────────────────────────
        body = tk.Frame(self.root, bg=C["bg"])
        body.pack(fill="both", expand=True)

        # Linke Feldliste
        left = tk.Frame(body, bg=C["side"], width=280)
        left.pack(side="left", fill="y"); left.pack_propagate(False)

        self.lbl_list = tk.Label(left, text="Felder",
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

        # Rechte Seite
        right = tk.Frame(body, bg=C["bg"])
        right.pack(side="left", fill="both", expand=True)

        # Scan-Bild (fast der gesamte Platz)
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
        self.root.bind("<Control-z>", lambda e: self._undo())
        self.root.bind("<Escape>",    lambda e: (self._exit_fs() or self._cancel_edit_sel()))

        # Fehler-Banner (eine Zeile)
        self.banner = tk.Frame(right, height=34)
        self.banner.pack(fill="x", padx=6, pady=(0,2))
        self.banner.pack_propagate(False)

        self.lbl_banner = tk.Label(self.banner, text="",
                                   font=("Segoe UI",10,"bold"), anchor="w")
        self.lbl_banner.pack(side="left", fill="both", expand=True, padx=12)

        self.lbl_exp = tk.Label(self.banner, text="",
                                font=("Segoe UI",8), anchor="e", wraplength=600)
        self.lbl_exp.pack(side="right", padx=12)

        # Aktionszeile
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
                          takefocus=False)   # kein Focus-Klau
            b.pack(side="left", padx=(8,4), pady=6)
            b.bind("<Enter>", lambda e: b.config(bg=hover))
            b.bind("<Leave>", lambda e: b.config(bg=color))
            return b

        self.btn_confirm = mkbtn("Bestaetigen   [Enter]","#166534","#14532d", self.confirm)
        self.btn_correct = mkbtn("Korrigieren   [E]",   "#1e40af","#1e3a8a", self.correct)
        self.btn_next    = mkbtn("Weiter   [Leer]",     "#374151","#4b5563", self.next_field)

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

        # Fortschrittsbalken
        style = ttk.Style(); style.configure("P.Horizontal.TProgressbar",
            troughcolor=C["side"], background="#166534", thickness=3)
        self.prog = ttk.Progressbar(self.root, mode="determinate",
                                    style="P.Horizontal.TProgressbar")
        self.prog.pack(fill="x", side="bottom")

        self._set_buttons(False)

    # ── Status ────────────────────────────────────────────────────────────────

    def _set_status(self, msg, color=None):
        self.lbl_status.config(text=msg, fg=color or C["dim"])

    def _set_buttons(self, active: bool):
        st = "normal" if active else "disabled"
        self.btn_confirm.config(state=st)
        self.btn_correct.config(state=st)

    # ── Dokumente ─────────────────────────────────────────────────────────────

    def _load_docs(self):
        def _w():
            docs = api("/api/v1/documents")
            if not docs:
                self.root.after(0, lambda: self._set_status(
                    "Keine Dokumente. 'Beispieldaten laden' im Launcher.", C["yel"]))
                return
            self.docs = docs
            labels = [f"{d.get('doc_no','?')}  ({d.get('n_fields',0)} Felder, "
                      f"{d.get('n_errors',0)} Fehler)" for d in docs]
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
        self._set_status("Lade Felder...", C["yel"])
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
            f"{n_err} Fehler   {n_wrn} Warnungen   {n_ok} OK   "
            f"(Bilder laden im Hintergrund...)", C["fg"])
        self._apply_filter()
        threading.Thread(target=self._preload_all, daemon=True).start()

    # ── Bildvorladen ──────────────────────────────────────────────────────────

    def _preload_all(self):
        doc_id   = self.doc_id
        all_pgs  = sorted({i["page"] for i in self.items})
        # Aktuelle Seite zuerst, dann aufsteigend alle anderen
        cur      = [self.cur_page] if self.cur_page in all_pgs else []
        ordered  = cur + [p for p in all_pgs if p not in cur]
        loaded = 0
        for pg in ordered:
            if pg in self.pil_cache or doc_id != self.doc_id:
                continue
            data = fetch_img(doc_id, pg)
            if data:
                img = Image.open(BytesIO(data)).convert("RGB")
                # Keine Verkleinerung -- volle Aufloesung im RAM
                self.pil_cache[pg] = img
                loaded += 1
                if pg == self.cur_page:
                    self.root.after(0, self._redraw)
        total = len(flag_pgs) + len(other_pgs)
        self.root.after(0, lambda: self._set_status(
            f"{loaded}/{total} Seiten geladen -- Navigation sofort", C["grn"]))

    # ── Filter + Liste ────────────────────────────────────────────────────────

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
        self.lbl_list.config(text=f"{n} Felder  |  {nf} mit Flags")
        self.lbl_count.config(text=f"{nf} zu pruefen" if nf else "Alles geprueft!")

        if self.visible:
            self._done_shown = False
            self.lb.selection_set(0)
            self.lb.see(0)          # immer nach oben scrollen
            self._show(0)

    def _on_list_select(self):
        sel = self.lb.curselection()
        if sel: self._show(sel[0])

    # ── Anzeige ───────────────────────────────────────────────────────────────

    def _show(self, idx: int):
        if not (0 <= idx < len(self.visible)): return
        self.idx = idx
        item  = self.visible[idx]
        flags = item["flags"]
        total = len(self.visible)

        # Fortschritt
        self.lbl_prog.config(text=f"{idx+1} / {total}")
        self.prog["maximum"] = total; self.prog["value"] = idx + 1

        # Banner
        if flags:
            fl   = flags[0]; sev = fl["severity"]; code = fl["code"]
            bg   = C["err"] if sev == "error" else C["wrn"]
            col  = C["red"] if sev == "error" else C["yel"]
            lbl  = "FEHLER" if sev == "error" else "WARNUNG"
            title, explain = INFO.get(code, (code, fl.get("message","")))
            exp = fl.get("expected",""); act = fl.get("actual","")
            banner_txt = f"  {lbl}: {title}"
            if exp or act: banner_txt += f"    |    Erwartet: {exp}    Gefunden: {act}"
            self.banner.config(bg=bg)
            self.lbl_banner.config(bg=bg, fg=col, text=banner_txt)
            self.lbl_exp.config(bg=bg, fg=C["dim"], text=explain)
            self.lbl_action.config(bg=C["side"], fg=C["grn"],
                text=f"  Was tun?  {ACTION.get(code,'Scan pruefen.')}")
        else:
            st = STATUS_DE.get(item["status"], item["status"])
            self.banner.config(bg=C["ok"])
            self.lbl_banner.config(bg=C["ok"], fg=C["grn"],
                text=f"  OK  —  {st}  —  p{item['page']}  {item['label'][:40]}")
            self.lbl_exp.config(bg=C["ok"], fg=C["dim"], text=item["value"])
            self.lbl_action.config(bg=C["side"], fg=C["dim"], text="")

        self._set_buttons(bool(flags))

        # Bild setzen -- Zoom zuruecksetzen bei neuem Feld
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
        # Selektion beim Feldwechsel immer zuruecksetzen
        if self.edit_mode:
            self._sel_fid = None
            self.lbl_sel_field.config(text="Kein Feld ausgewaehlt -- anklicken zum Auswaehlen")
        self._redraw()

    # ── Bbox-Editor ──────────────────────────────────────────────────────────────

    def _toggle_edit_mode(self):
        self.edit_mode = not self.edit_mode
        if self.edit_mode:
            self.btn_edit.config(bg="#6d28d9", text="Bearbeitung beenden")
            self.edit_bar.pack(fill="x", after=self.root.winfo_children()[1])
            # Felder dieser Seite laden
            self._load_page_fields()
            self.canvas.config(cursor="crosshair")
        else:
            self.btn_edit.config(bg="#7c3aed", text="Boxen bearbeiten")
            self.edit_bar.pack_forget()
            self._sel_fid = None
            self.canvas.config(cursor="crosshair")
            self._redraw()

    def _load_page_fields(self):
        """Laedt alle Felder der aktuellen Seite fuer den Editor."""
        pg = self.cur_page
        if not pg:
            return
        self._page_fields = [i for i in self.items if i["page"] == pg]
        self._redraw()

    def _canvas_to_img(self, cx, cy):
        """Canvas-Koordinate -> normierte Bildkoordinate (0-1)."""
        cw = self.canvas.winfo_width(); ch = self.canvas.winfo_height()
        pg = self.cur_page
        if pg not in self.pil_cache:
            return None, None
        pil = self.pil_cache[pg]
        iw, ih = pil.size
        base = min(cw/iw, ch/ih)
        if self.zoom <= 1.0:
            pw = int(iw*base); ph = int(ih*base)
            ix = (cw-pw)//2;   iy = (ch-ph)//2
            nx = (cx-ix) / pw; ny = (cy-iy) / ph
        else:
            ts  = base*self.zoom
            vw  = cw/ts; vh = ch/ts
            x0  = max(0.0, self.zoom_x*iw - vw/2)
            y0  = max(0.0, self.zoom_y*ih - vh/2)
            x1  = min(float(iw), x0+vw); y1 = min(float(ih), y0+vh)
            nx  = x0/iw + (cx/cw)*(x1-x0)/iw
            ny  = y0/ih + (cy/ch)*(y1-y0)/ih
        return max(0.0,min(1.0,nx)), max(0.0,min(1.0,ny))

    def _img_to_canvas(self, nx, ny):
        """Normierte Bildkoordinate -> Canvas-Koordinate."""
        cw = self.canvas.winfo_width(); ch = self.canvas.winfo_height()
        pg = self.cur_page
        if pg not in self.pil_cache:
            return 0, 0
        pil = self.pil_cache[pg]
        iw, ih = pil.size
        base = min(cw/iw, ch/ih)
        if self.zoom <= 1.0:
            pw = int(iw*base); ph = int(ih*base)
            ix = (cw-pw)//2;   iy = (ch-ph)//2
            return ix + nx*pw,  iy + ny*ph
        else:
            ts  = base*self.zoom
            vw  = cw/ts; vh = ch/ts
            x0  = max(0.0, self.zoom_x*iw - vw/2)
            y0  = max(0.0, self.zoom_y*ih - vh/2)
            x1  = min(float(iw), x0+vw); y1 = min(float(ih), y0+vh)
            cx  = (nx*iw - x0) / (x1-x0) * cw
            cy  = (ny*ih - y0) / (y1-y0) * ch
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

    def _cancel_edit_sel(self):
        self._sel_fid = None
        if self.edit_mode:
            self.lbl_sel_field.config(text="Kein Feld ausgewaehlt")
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
            self.lbl_sel_field.config(
                text=f"Rueckgaengig: {item.get('label','?')[:25]}")
        self._redraw()

    def _delete_sel_bbox(self):
        if not self.edit_mode or not self._sel_fid:
            return
        item = next((i for i in self._page_fields if i["id"]==self._sel_fid), None)
        if not item:
            return
        self._push_undo(item["id"], item.get("bbox"))
        item["bbox"] = None; self._sel_fid = None
        self.lbl_sel_field.config(text="Box geloescht  (Strg+Z zum Rueckgaengig)")
        self._redraw()

    def _save_all_bboxes(self):
        """Speichert alle geaenderten Bboxen der aktuellen Seite an die API."""
        to_save = [(i["id"], i.get("bbox")) for i in self._page_fields]
        self.lbl_sel_field.config(text=f"Speichere {len(to_save)} Felder...")
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
            msg = f"Gespeichert: {ok}  Fehler: {err}"
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
        if fid:
            # Feld ausgewaehlt -- Drag-Modus bestimmen
            item = next(i for i in self._page_fields if i["id"]==fid)
            bbox = item.get("bbox")
            zone = self._handle_zone(nx, ny, bbox) if bbox else "move"
            self._sel_fid       = fid
            self._drag_mode     = zone
            self._drag_bbox     = list(bbox) if bbox else None
            self._drag_start_c  = (nx, ny)
            # Undo-Snapshot VOR dem Drag
            self._push_undo(fid, bbox)
            label = item.get("label","?")[:30]
            self.lbl_sel_field.config(
                text=f"Ausgewaehlt: {label}  |  Ziehen: {zone}")
        else:
            # Leere Flaeche: neue Box zeichnen
            self._sel_fid      = None
            self._draw_start   = (nx, ny)
            self._drag_mode    = "draw"
            self.canvas.config(cursor="crosshair")
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
                            text=f"Neue Box fuer: {cur_item.get('label','?')[:30]}"
                                 f"  (Strg+Z rueckgaengig  |  Speichern nicht vergessen)")
            self._draw_start = None
        self._drag_mode = ""
        self._redraw()

    def _on_wheel(self, event):
        """Mausrad: rein-/rauszoomen, zentriert auf Mausposition."""
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

        # Mausposition als Anteil des Canvas (0-1)
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
            msg = ("Bild wird geladen...\n\n"
                   "Alle Seiten werden automatisch im Hintergrund geladen.\n"
                   "Navigation ist sofort verfuegbar sobald die Seite bereit ist.")
            self.canvas.create_text(cw//2, ch//2, text=msg,
                fill=C["dim"], font=("Segoe UI",11), justify="center")
            return

        pil = self.pil_cache[pg]
        iw, ih = pil.size
        base = min(cw/iw, ch/ih)

        if self.zoom <= 1.0:
            # ── Schneller Cache-Pfad (unveraendert, keine PIL-Arbeit) ────────
            key = (pg, cw, ch)
            photo = self.photo_cache.get(key)
            if photo is None:
                nw = max(1, int(iw*base)); nh = max(1, int(ih*base))
                photo = ImageTk.PhotoImage(pil.resize((nw,nh), Image.BILINEAR))
                self.photo_cache[key] = photo
            self._img_ref = photo
            pw, ph = photo.width(), photo.height()
            ix = (cw-pw)//2; iy = (ch-ph)//2
            self.canvas.create_image(ix, iy, image=photo, anchor="nw")

            # Bbox
            bbox = self.cur_bbox; sev = self.cur_sev
            if bbox and len(bbox) == 4:
                bx0=ix+int(bbox[0]*pw); by0=iy+int(bbox[1]*ph)
                bx1=ix+int(bbox[2]*pw); by1=iy+int(bbox[3]*ph)
                color = "#ef4444" if sev=="error" else "#f59e0b"
                self.canvas.create_rectangle(bx0,by0,bx1,by1,outline=color,width=3)

        else:
            # ── Zoom-Pfad: Crop aus PIL, dann auf Canvas-Groesse skalieren ──
            ts  = base * self.zoom
            vw  = cw / ts; vh = ch / ts          # Sichtbares Fenster in Bildpx
            x0  = max(0.0, self.zoom_x*iw - vw/2)
            y0  = max(0.0, self.zoom_y*ih - vh/2)
            x1  = min(float(iw), x0 + vw)
            y1  = min(float(ih), y0 + vh)
            if x1 >= iw: x0 = max(0.0, iw - vw)
            if y1 >= ih: y0 = max(0.0, ih - vh)

            crop  = pil.crop((int(x0), int(y0), int(x1), int(y1)))
            disp  = crop.resize((cw, ch), Image.BILINEAR)   # BILINEAR = schnell
            photo = ImageTk.PhotoImage(disp)
            self._img_ref = photo
            self.canvas.create_image(0, 0, image=photo, anchor="nw")

            # Bbox im Zoom-Bereich
            bbox = self.cur_bbox; sev = self.cur_sev
            if bbox and len(bbox) == 4:
                rw = x1-x0; rh = y1-y0  # sichtbarer Bereich in Bildpx
                bx0c = (bbox[0]*iw - x0) / rw * cw
                by0c = (bbox[1]*ih - y0) / rh * ch
                bx1c = (bbox[2]*iw - x0) / rw * cw
                by1c = (bbox[3]*ih - y0) / rh * ch
                if bx1c>0 and bx0c<cw and by1c>0 and by0c<ch:
                    color = "#ef4444" if sev=="error" else "#f59e0b"
                    self.canvas.create_rectangle(
                        max(0,bx0c), max(0,by0c),
                        min(cw,bx1c), min(ch,by1c),
                        outline=color, width=3)

            # Zoom-Indikator
            self.canvas.create_text(cw-8, 8,
                text=f"{self.zoom:.1f}x  (Doppelklick = Zuruecksetzen)",
                fill="white", font=("Segoe UI",8,"bold"),
                anchor="ne")

        # ── Editor-Overlay: alle Seitenboxen anzeigen ────────────────────────
        if self.edit_mode and self._page_fields:
            for item in self._page_fields:
                b = item.get("bbox")
                if not b or len(b) != 4:
                    continue
                cx0,cy0 = self._img_to_canvas(b[0],b[1])
                cx1,cy1 = self._img_to_canvas(b[2],b[3])
                is_sel  = item["id"] == self._sel_fid
                is_cur  = item["id"] == (self._cur() or {}).get("id")
                color   = "#a78bfa" if is_sel else "#22d3ee" if is_cur else "#94a3b8"
                width   = 3 if is_sel or is_cur else 1
                self.canvas.create_rectangle(cx0,cy0,cx1,cy1,
                                             outline=color, width=width)
                # Feldname
                label = item.get("label","?")[:18]
                self.canvas.create_text(cx0+3, cy0+2, text=label,
                    fill=color, font=("Segoe UI",7), anchor="nw")
                # Resize-Handles an den Ecken (nur wenn ausgewaehlt)
                if is_sel:
                    for hx, hy in [(cx0,cy0),(cx1,cy0),(cx0,cy1),(cx1,cy1)]:
                        self.canvas.create_rectangle(
                            hx-5,hy-5,hx+5,hy+5,
                            fill="#a78bfa", outline="white", width=1)

    # ── Aktionen ──────────────────────────────────────────────────────────────

    def _cur(self):
        return self.visible[self.idx] if 0 <= self.idx < len(self.visible) else None

    def confirm(self):
        item = self._cur()
        if not item or not item["flags"]: return
        fid = item["id"]
        # Sofort lokal aktualisieren und weiternavigieren
        save = (list(item["flags"]), item["has_err"], item["has_wrn"], item["status"])
        item["flags"] = []; item["has_err"] = False
        item["has_wrn"] = False; item["status"] = "confirmed"
        self._update_lb(self.idx); self.next_field()
        def _bg():
            r = api(f"/api/v1/fields/{fid}", method="PATCH",
                    body={"action":"confirm","actor":"reviewer"})
            if not r:  # Revert bei Fehler
                item["flags"],item["has_err"],item["has_wrn"],item["status"] = save
                self.root.after(0, lambda: self._update_lb(self.idx))
        threading.Thread(target=_bg, daemon=True).start()

    def correct(self):
        item = self._cur()
        if not item: return
        old  = item["value"]
        code = item["flags"][0]["code"] if item["flags"] else ""
        title, _ = INFO.get(code, (code,""))
        new = sd.askstring("Korrigieren",
            f"Seite {item['page']}  —  {item['label']}\n\n"
            f"{title}\n\nAktueller Wert: {old}\n\nRichtiger Wert:",
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
                mb.showinfo("Durchgang beendet",
                    f"Alle {len(self.visible)} Felder gesehen.\n"
                    f"Noch {rem} mit Flags offen.\n\nFaengt von vorne an.")
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
        self.root.focus_set()   # Focus zurueck damit Tastenkuerzel sofort greifen

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
        # Zaehler aktualisieren
        rem = sum(1 for i in self.visible if i["flags"])
        self.lbl_count.config(text=f"{rem} zu pruefen" if rem else "Alles geprueft! ✓")

    # ── Neuen Batch laden ────────────────────────────────────────────────────

    def _load_new_batch(self):
        import tkinter.filedialog as fd
        path = fd.askopenfilename(
            title="extracted_fields.json auswaehlen",
            filetypes=[("JSON","*.json"),("Alle","*.*")],
            initialdir=str(ROOT/"results"))
        if not path: return
        def _bg():
            self.root.after(0, lambda: self._set_status("Importiere...", C["yel"]))
            result = subprocess.run(
                [str(VENV_PY), str(ROOT/"load_results.py"), "--file", path],
                capture_output=True, timeout=120)
            if result.returncode == 0:
                self.root.after(0, lambda: (
                    self._set_status("Importiert!", C["grn"]),
                    self._load_docs()))
            else:
                self.root.after(0, lambda: self._set_status("Import fehlgeschlagen!", C["red"]))
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
        win.title("BioDize -- Alle Felder"); win.geometry("1100x600")
        win.configure(bg=C["bg"])
        style = ttk.Style(win); style.theme_use("clam")
        style.configure("T.Treeview", background=C["side"], foreground=C["fg"],
                        rowheight=22, fieldbackground=C["side"], font=("Segoe UI",9))
        style.configure("T.Treeview.Heading", background=C["hdr"], foreground=C["fg"],
                        font=("Segoe UI",9,"bold"))
        style.map("T.Treeview", background=[("selected",C["sel"])])
        bar = tk.Frame(win,bg=C["hdr"],height=36); bar.pack(fill="x"); bar.pack_propagate(False)
        tk.Button(bar, text="Als CSV speichern", bg="#1e40af", fg="white",
                  relief="flat", bd=0, padx=10, pady=6, cursor="hand2",
                  font=("Segoe UI",8,"bold"),
                  command=lambda: subprocess.Popen(
                      [str(VENV_PY), str(ROOT/"export_csv.py")],
                      creationflags=subprocess.CREATE_NEW_CONSOLE)
                  ).pack(side="right", padx=8, pady=4)
        cols = ("Seite","Kapitel","Feld","Wert","Status","Code","Schwere")
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
            sev="Fehler" if item["has_err"] else "Warnung" if item["has_wrn"] else ""
            tag="err" if item["has_err"] else "wrn" if item["has_wrn"] else "ok"
            tv.insert("","end",values=(item["page"],item["chapter"],
                item["label"][:40],item["value"][:30],
                STATUS_DE.get(item["status"],item["status"]),code,sev),tags=(tag,))

    def _open_debugger(self):
        subprocess.Popen([str(VENV_PY), str(ROOT/"debugger.py")],
                         creationflags=subprocess.CREATE_NEW_CONSOLE)


# ── Start ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
