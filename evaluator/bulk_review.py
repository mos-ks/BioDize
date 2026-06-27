"""
BioDize  -  Bulk Review
======================
Geht durch alle Felder in der Review-Queue und zeigt sie der Reihe nach an.
Du entscheidest für jedes: Bestätigen / Korrigieren / Überspringen.

Oder mit --auto-confirm: Alle als "bestätigt" markieren (Demo-Modus).

Starten:  py bulk_review.py                   # interaktiv
          py bulk_review.py --auto-confirm    # alles bestätigen
          py bulk_review.py --code 4EYES      # nur 4EYES-Felder
"""
from __future__ import annotations
import json, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()  # evaluator/ -> repo root
VENV_PY = ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
if VENV_PY.exists() and Path(sys.executable).resolve() != VENV_PY.resolve():
    sys.exit(subprocess.run([str(VENV_PY)] + sys.argv).returncode)

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt
    from rich.rule import Rule
    from rich.table import Table
    from rich import box
except ImportError:
    subprocess.run([str(VENV_PY), "-m", "pip", "install", "rich", "--quiet"])
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt
    from rich.rule import Rule
    from rich.table import Table
    from rich import box

import urllib.request, urllib.error

console = Console(force_terminal=True)
BASE = "http://localhost:8000"


def api(method: str, path: str, body: dict | None = None) -> dict | list | None:
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method,
                                  headers={"Content-Type": "application/json",
                                           "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        console.print(f"[red]HTTP {e.code}: {e.read().decode()[:200]}[/red]")
        return None
    except Exception as e:
        console.print(f"[red]API nicht erreichbar: {e}[/red]")
        console.print("[dim]Bitte zuerst 'App starten' im Launcher klicken.[/dim]")
        sys.exit(1)


def main() -> None:
    args = sys.argv[1:]
    auto       = "--auto-confirm" in args or "--auto" in args
    code_filter= next((args[i+1].upper() for i,a in enumerate(args)
                       if a == "--code" and i+1 < len(args)), None)

    # Dokumente holen
    docs = api("GET", "/api/v1/documents")
    if not docs:
        console.print("[red]Keine Dokumente gefunden. 'Echte Daten laden' zuerst ausführen.[/red]")
        sys.exit(1)

    doc = docs[0]
    doc_id = doc["id"]

    console.print()
    console.print(Panel(
        f"  Dokument: [bold]{doc.get('doc_no','?')}[/bold]\n"
        f"  Fehler: [red]{doc.get('n_errors',0)}[/red]   "
        f"Warnungen: [yellow]{doc.get('n_warnings',0)}[/yellow]   "
        f"Zur Prüfung: [bold]{doc.get('n_needs_review',0)}[/bold]",
        title="[bold]BioDize  -  Bulk Review[/bold]",
        border_style="bright_blue",
    ))

    # Review-Queue laden
    queue = api("GET", f"/api/v1/documents/{doc_id}/queue")
    if not queue:
        console.print("[green]Queue leer  -  alle Felder bereits bearbeitet.[/green]")
        return

    # Filter
    if code_filter:
        queue = [f for f in queue
                 if any(fl["code"].startswith(code_filter) for fl in f.get("flags", []))]

    console.print(f"  [dim]{len(queue)} Felder in der Queue{f' (Filter: {code_filter})' if code_filter else ''}[/dim]")

    if auto:
        import threading
        total  = len(queue)
        ok = err = done = 0
        lock   = threading.Lock()

        def confirm_one(field):
            nonlocal ok, err, done
            result = api("PATCH", f"/api/v1/fields/{field['id']}",
                         {"action": "confirm", "actor": "bulk_review"})
            with lock:
                if result: ok += 1
                else:      err += 1
                done += 1
                bar = "#" * int(30 * done / total)
                pad = "." * (30 - len(bar))
                print(f"\r  [{bar}{pad}] {done}/{total}  OK:{ok}  Fehler:{err}", end="", flush=True)

        console.print(f"\n  Bestaetige {total} Felder parallel...\n")
        # Max 8 parallele Verbindungen (SQLite-Limit)
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(confirm_one, queue))
        print()
        console.print(f"\n  [green]Bestaetigt: {ok}[/green]  [red]Fehler: {err}[/red]")
        input("\n  Enter druecken zum Schliessen...")
        return

    # Interaktiver Modus
    confirmed = corrected = skipped = 0
    for idx, field in enumerate(queue, 1):
        flags = field.get("flags", [])
        flag_codes = ", ".join(f["code"] for f in flags)
        sev_col = "red" if any(f["severity"] == "error" for f in flags) else "yellow"

        console.print()
        console.print(Rule(f"[{sev_col}]{flag_codes}[/{sev_col}]  p{field['page_no']}  "
                          f"{field.get('label_raw','')[:30]}  [dim]({idx}/{len(queue)})[/dim]"))

        # Details
        tbl = Table(box=box.SIMPLE_HEAD, show_edge=False, show_header=False, padding=(0,1))
        tbl.add_column(width=14, style="dim")
        tbl.add_column()
        tbl.add_row("Wert (OCR)",  repr(field.get("value_raw", "?")))
        tbl.add_row("Normalisiert",str(field.get("value", "?")))
        tbl.add_row("Einheit",     field.get("unit") or " - ")
        for fl in flags:
            tbl.add_row(fl["code"], f"Erwartet: [green]{fl.get('expected','?')}[/green]  "
                                    f"Ist: [red]{fl.get('actual','?')}[/red]")
        console.print(tbl)

        ans = Prompt.ask(
            "  [bold]k[/bold]=bestätigen  [bold]c[/bold]=korrigieren  "
            "[bold]s[/bold]=überspringen  [bold]q[/bold]=beenden",
            default="k",
        ).strip().lower()

        if ans == "q":
            break
        elif ans == "s":
            skipped += 1
        elif ans == "c":
            new_val = Prompt.ask(f"  Neuer Wert (aktuell: {field.get('value_raw','?')!r})")
            result = api("PATCH", f"/api/v1/fields/{field['id']}",
                         {"action": "correct", "value": new_val, "actor": "reviewer"})
            if result:
                console.print(f"  [green]Korrigiert -> {new_val!r}[/green]")
                corrected += 1
        else:  # k = bestätigen
            result = api("PATCH", f"/api/v1/fields/{field['id']}",
                         {"action": "confirm", "actor": "reviewer"})
            if result:
                console.print("  [green]Bestaetigt[/green]")
                confirmed += 1

    console.print()
    console.print(Panel(
        f"  [green]Bestaetigt: {confirmed}[/green]   "
        f"[cyan]Korrigiert: {corrected}[/cyan]   "
        f"[dim]Uebersprungen: {skipped}[/dim]",
        title="Ergebnis", border_style="green",
    ))


if __name__ == "__main__":
    main()
