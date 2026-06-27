"""BioDize Launcher"""
import tkinter as tk
import subprocess, sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()  # evaluator/ -> repo root
VENV_PY = ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
PY      = str(VENV_PY) if VENV_PY.exists() else sys.executable

BG        = "#0f1117"
CARD_BG   = "#1a1d27"
TEXT      = "#e2e8f0"
MUTED     = "#64748b"
ACCENT2   = "#22c55e"

FONT_TITLE = ("Segoe UI", 20, "bold")
FONT_STEP  = ("Segoe UI", 8)
FONT_BTN   = ("Segoe UI", 12, "bold")
FONT_DESC  = ("Segoe UI", 8)
FONT_STA   = ("Segoe UI", 8)

procs: list[subprocess.Popen] = []


def launch(script: str, label: str, btn: tk.Button,
           color_hover: str, color_base: str) -> None:
    set_status(f"{label} wird gestartet...", MUTED)
    btn.config(state="disabled", text="Laedt...")
    try:
        parts = script.split()
        cmd   = [PY, str(ROOT / parts[0])] + parts[1:]
        p     = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
        procs.append(p)
        set_status(f"{label} laeuft (PID {p.pid})", ACCENT2)
    except Exception as e:
        set_status(f"Fehler: {e}", "#ef4444")
    root.after(2000, lambda: btn.config(
        state="normal", text=label, bg=color_base, activebackground=color_hover))


def set_status(msg: str, color: str = MUTED) -> None:
    status_var.set(msg)
    status_lbl.config(fg=color)


def on_close() -> None:
    for p in procs:
        try: p.terminate()
        except Exception: pass
    root.destroy()


def make_step(parent, step_nr: str, text: str, desc: str,
              color: str, hover: str, command) -> tk.Frame:
    card = tk.Frame(parent, bg=CARD_BG, bd=0)

    # Schritt-Nummer
    tk.Label(card, text=f"Schritt {step_nr}", font=FONT_STEP,
             bg=CARD_BG, fg=MUTED).pack(anchor="w", padx=20, pady=(12, 0))

    btn = tk.Button(card, text=text, font=FONT_BTN,
                    bg=color, fg="#ffffff",
                    activebackground=hover, activeforeground="#ffffff",
                    relief="flat", bd=0, padx=28, pady=13,
                    cursor="hand2")
    btn.config(command=lambda: command(btn, color, hover))
    btn.pack(fill="x", padx=20, pady=(4, 4))
    btn.bind("<Enter>", lambda e: btn.config(bg=hover))
    btn.bind("<Leave>", lambda e: btn.config(bg=color)
             if btn["state"] == "normal" else None)

    tk.Label(card, text=desc, font=FONT_DESC, bg=CARD_BG, fg=MUTED,
             wraplength=260, justify="center").pack(pady=(0, 14))
    return card


def sep():
    tk.Frame(root, bg=CARD_BG, height=1).pack(fill="x", padx=24)


# ── Datei-Dialog fuer Formular ────────────────────────────────────────────────

def load_custom_form(btn, color_base, color_hover):
    import tkinter.filedialog as fd
    path = fd.askopenfilename(
        title="Formular-JSON auswaehlen",
        filetypes=[("JSON", "*.json"), ("Alle", "*.*")],
        initialdir=str(ROOT / "results"),
    )
    if not path:
        return
    set_status(f"Lade: {Path(path).name}...", MUTED)
    btn.config(state="disabled", text="Laedt...")
    try:
        p = subprocess.Popen(
            [PY, str(ROOT / "load_results.py"), "--file", path],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        procs.append(p)
        set_status(f"Formular wird importiert (PID {p.pid})", ACCENT2)
    except Exception as e:
        set_status(f"Fehler: {e}", "#ef4444")
    root.after(2000, lambda: btn.config(
        state="normal", text="Andere Daten laden",
        bg=color_base, activebackground=color_hover))


# ── Fenster ──────────────────────────────────────────────────────────────────

root = tk.Tk()
root.title("BioDize")
root.configure(bg=BG)
root.resizable(False, False)
root.protocol("WM_DELETE_WINDOW", on_close)
root.geometry("360x100")

# Titel
tk.Label(root, text="BioDize", font=FONT_TITLE, bg=BG, fg=TEXT).pack(pady=(22, 0))
tk.Label(root, text="Pharma-Chargenprotokoll Digitalisierung",
         font=("Segoe UI", 9), bg=BG, fg=MUTED).pack(pady=(2, 14))

sep()

# Schritt 1
s1 = make_step(root, "1", "App starten",
               "Backend + Frontend hochfahren\nund Browser oeffnen",
               "#1d4ed8", "#1e40af",
               lambda btn, c, h: launch("start.py", "App starten", btn, h, c))
s1.pack(fill="x", padx=24, pady=(14, 4))

# Schritt 2 -- zwei Optionen nebeneinander
s2_frame = tk.Frame(root, bg=BG)
s2_frame.pack(fill="x", padx=24, pady=4)

def make_mini_btn(parent, step, text, desc, color, hover, cmd):
    card = tk.Frame(parent, bg=CARD_BG, bd=0)
    tk.Label(card, text=f"Schritt {step}", font=FONT_STEP,
             bg=CARD_BG, fg=MUTED).pack(anchor="w", padx=12, pady=(10,0))
    btn = tk.Button(card, text=text, font=("Segoe UI", 10, "bold"),
                    bg=color, fg="white", activebackground=hover,
                    activeforeground="white", relief="flat", bd=0,
                    padx=8, pady=10, cursor="hand2")
    btn.config(command=lambda: cmd(btn, color, hover))
    btn.pack(fill="x", padx=12, pady=(3,3))
    btn.bind("<Enter>", lambda e: btn.config(bg=hover))
    btn.bind("<Leave>", lambda e: btn.config(bg=color)
             if btn["state"]=="normal" else None)
    tk.Label(card, text=desc, font=FONT_DESC, bg=CARD_BG, fg=MUTED,
             wraplength=120, justify="center").pack(pady=(0,10))
    return card

left2  = make_mini_btn(s2_frame, "2a", "Beispieldaten",
                       "Mitgelieferte 323 Felder\nin DB laden",
                       "#7c3aed", "#6d28d9",
                       lambda btn,c,h: launch("load_results.py","Echte Daten",btn,h,c))
right2 = make_mini_btn(s2_frame, "2b", "Andere Daten",
                       "Andere JSON-Datei\nauswaehlen",
                       "#1e40af", "#1e3a8a",
                       load_custom_form)
left2.pack(side="left", fill="x", expand=True, padx=(0,4))
right2.pack(side="left", fill="x", expand=True, padx=(4,0))

# Schritt 3 -- Pruefer (Hauptaktion)
sep()
s3 = make_step(root, "3", "Pruefer oeffnen",
               "Fehler ansehen, Scan-Bild anzeigen\nund Werte korrigieren",
               "#059669", "#047857",
               lambda btn, c, h: launch("reviewer.py", "Pruefer", btn, h, c))
s3.pack(fill="x", padx=24, pady=(10, 4))

# Schritt 4 -- Export
s4 = make_step(root, "4", "Als CSV exportieren",
               "Alle Felder mit Flags als CSV-Datei\nspeichern",
               "#0f766e", "#0d6b63",
               lambda btn, c, h: launch("export_csv.py", "CSV Export", btn, h, c))
s4.pack(fill="x", padx=24, pady=(0, 4))

sep()

# Extra-Tools (klein)
extra = tk.Frame(root, bg=BG)
extra.pack(fill="x", padx=24, pady=6)

def mini_tool_btn(parent, text, script, color="#334155", hover="#475569"):
    b = tk.Button(parent, text=text, font=("Segoe UI", 8),
                  bg=color, fg=TEXT, activebackground=hover,
                  activeforeground=TEXT, relief="flat", bd=0,
                  padx=8, pady=6, cursor="hand2",
                  command=lambda: subprocess.Popen(
                      [PY, str(ROOT / script)],
                      creationflags=subprocess.CREATE_NEW_CONSOLE))
    b.bind("<Enter>", lambda e: b.config(bg=hover))
    b.bind("<Leave>", lambda e: b.config(bg=color))
    b.pack(side="left", padx=(0,6))
    return b

mini_tool_btn(extra, "Debugger",   "debugger.py")
mini_tool_btn(extra, "Autopatch",  "autopatch.py")
mini_tool_btn(extra, "Alle best.", "bulk_review.py --auto-confirm",
              color="#164e63", hover="#155e75")

sep()

status_var = tk.StringVar(value="Bereit.")
status_lbl = tk.Label(root, textvariable=status_var, font=FONT_STA,
                       bg=BG, fg=MUTED, anchor="center")
status_lbl.pack(pady=10)

# Fenstergroesse anpassen
root.update_idletasks()
W = 360
H = root.winfo_reqheight()
sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
root.geometry(f"{W}x{H}+{(sw-W)//2}+{(sh-H)//2}")

root.mainloop()
