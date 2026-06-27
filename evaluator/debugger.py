"""
BioDize — Rule Debugger  (v2)
==============================
Starten:  py debugger.py          # echte 323 Felder, 21 Fehler
          py debugger.py --stub   # Stub-Modus (28 Felder, Regel-Tests)
          py debugger.py --watch  # auto-reload bei rules.py-Änderungen
"""
from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import time
import traceback
from copy import deepcopy
from dataclasses import dataclass, field as dc_field
from pathlib import Path

# ── Venv-Bootstrap ────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent.resolve()  # evaluator/ -> repo root
VENV_PY = ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
if VENV_PY.exists() and Path(sys.executable).resolve() != VENV_PY.resolve():
    sys.exit(subprocess.run([str(VENV_PY)] + sys.argv).returncode)

BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
os.chdir(str(BACKEND))

try:
    from rich.console import Console
except ImportError:
    pip = BACKEND / ".venv" / "Scripts" / "pip.exe"
    subprocess.run([str(pip), "install", "rich", "--quiet", "--only-binary", ":all:"])
    from rich.console import Console

from rich import box
from rich.columns import Columns
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from app.domain.roles import Role
from app.domain.severity import Category, FieldStatus, Severity
from app.pipeline.extract.stub import StubExtractor
from app.pipeline.model import Block, BBox, Document, Field, Flag, Read
from app.pipeline.normalize import normalize, parse_german_number, parse_soll, detect_value_type
from app.pipeline.validate import rules as R
from app.pipeline.validate.engine import validate
from app.pipeline.validate.uncertainty import score

console = Console()
RESULTS_JSON = ROOT / "results" / "extracted_fields.json"

# ── Typen ─────────────────────────────────────────────────────────────────────
@dataclass
class FlatFlag:
    page:     int
    chapter:  str
    label:    str
    role:     str
    value:    str
    severity: str          # "error" | "warning"
    category: str
    code:     str
    message:  str
    expected: str
    actual:   str


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────
SEV_RICH = {"error": "[bold red]ERR [/bold red]", "warning": "[bold yellow]WARN[/bold yellow]"}
CAT_COLOR = {
    "format":          "cyan",
    "range":           "magenta",
    "calculation":     "blue",
    "four_eyes":       "red",
    "temporal":        "yellow",
    "extraction":      "dim white",
    "cross_reference": "dark_orange",
}

RULE_META: dict[str, tuple[str, str]] = {
    "rule_date_format":      ("format",          "DD.MM.YYYY Null-Padding in Datum-Feldern"),
    "rule_nks":              ("format",          "Anzahl Nachkommastellen gegen Soll-Vorgabe"),
    "rule_range":            ("range",           "Wert im Soll-Bereich (min–max / Sollwert)"),
    "rule_formula":          ("calculation",     "calc_expr neu berechnen und mit Eintrag vergleichen"),
    "rule_net_mass":         ("calculation",     "Netto = Brutto − Tara  [Block]"),
    "rule_volume":           ("calculation",     "Volumen = Netto × Dichte  [Block]"),
    "rule_four_eyes":        ("four_eyes",       "Geprueft ≠ Bearbeitet; Datum-Reihenfolge  [Block]"),
    "rule_end_after_start":  ("temporal",        "Haltezeit-Ende > Haltezeit-Start  [Block]"),
    "rule_dates_document":   ("temporal",        "Kein Datum vor Druckdatum; nicht >180 Tage danach  [Dok]"),
    "rule_kuerzel_document": ("four_eyes",       "Kürzel in Beteiligte-Personen (Edit-Dist 2)  [Dok]"),
    "rule_xref_document":    ("cross_reference", "Übertrag-Wert = Quellfeld Kapitel X  [Dok]"),
}

FLAG_CODE_TO_RULE = {
    "FMT_DATE_PADDING": "rule_date_format",
    "FMT_NKS":          "rule_nks",
    "RANGE_SOLL":       "rule_range",
    "RANGE_SETPOINT":   "rule_range",
    "CALC_FORMULA":     "rule_formula",
    "CALC_ROUNDING":    "rule_formula",
    "CALC_NET_MASS":    "rule_net_mass",
    "CALC_VOLUME":      "rule_volume",
    "4EYES_ORDER":      "rule_four_eyes",
    "4EYES_DISTINCT":   "rule_four_eyes",
    "TIME_END_AFTER_START": "rule_end_after_start",
    "DATE_BEFORE_PRINT":"rule_dates_document",
    "DATE_FAR_FUTURE":  "rule_dates_document",
    "KUERZEL_UNKNOWN":  "rule_kuerzel_document",
    "XREF_MISMATCH":    "rule_xref_document",
    "EXTRACT_LOW_CONF": "(uncertainty scoring)",
}


# ── Daten laden ───────────────────────────────────────────────────────────────

def _flat_from_doc(doc: Document) -> list[FlatFlag]:
    out = []
    for b in doc.blocks:
        for f in b.fields:
            for fl in f.flags:
                out.append(FlatFlag(
                    page=f.page_no, chapter=f.chapter or "",
                    label=f.label_raw or "", role=f.role or "",
                    value=f.value_raw or "",
                    severity=fl.severity.value, category=fl.category.value,
                    code=fl.code, message=fl.message,
                    expected=fl.expected or "—", actual=fl.actual or "—",
                ))
    return sorted(out, key=lambda x: (x.severity != "error", x.code, x.page))


def load_real() -> tuple[list[FlatFlag], int, int, int, int]:
    """Lädt pre-computed Flags aus extracted_fields.json — exaktes Match mit der Web-App."""
    if not RESULTS_JSON.exists():
        raise FileNotFoundError(str(RESULTS_JSON))
    data   = json.loads(RESULTS_JSON.read_text(encoding="utf-8"))
    fields = data["fields"]
    flags: list[FlatFlag] = []
    for f in fields:
        for fl in f.get("flags", []):
            flags.append(FlatFlag(
                page=f["page_no"], chapter=f.get("chapter") or "",
                label=f.get("label") or "", role=f.get("role") or "",
                value=f.get("value_raw") or f.get("value") or "",
                severity=fl["severity"], category=fl.get("category", ""),
                code=fl["code"], message=fl.get("message", ""),
                expected=fl.get("expected") or "—", actual=fl.get("actual") or "—",
            ))
    flags.sort(key=lambda x: (x.severity != "error", x.code, x.page))
    n_err   = sum(1 for f in flags if f.severity == "error")
    n_warn  = sum(1 for f in flags if f.severity == "warning")
    n_auto  = sum(1 for f in fields if f.get("status") == "auto_accepted")
    n_rev   = sum(1 for f in fields if f.get("status") == "needs_review")
    return flags, len(fields), n_err, n_warn, n_auto


def load_stub() -> tuple[list[FlatFlag], int, int, int, int]:
    """Stub-Extraktor: vollständige Pipeline, gut für Regel-Tests."""
    doc = StubExtractor().extract()
    normalize(doc); validate(doc); score(doc)
    flags = _flat_from_doc(doc)
    all_f = doc.all_fields()
    n_err  = sum(1 for f in flags if f.severity == "error")
    n_warn = sum(1 for f in flags if f.severity == "warning")
    n_auto = sum(1 for f in all_f if f.status == FieldStatus.AUTO_ACCEPTED)
    return flags, len(all_f), n_err, n_warn, n_auto


def load_revalidate() -> tuple[list[FlatFlag], int, int, int, int]:
    """Lädt JSON-Felder und führt Regeln NEU aus — zeigt Wirkung von Regel-Änderungen.
    Hinweis: soll/calc_expr fehlen im JSON → RANGE/CALC_FORMULA nicht rekonstruierbar."""
    data    = json.loads(RESULTS_JSON.read_text(encoding="utf-8"))
    entries = data["fields"]
    doc = Document(doc_no="revalidate", title="Re-Validate", page_count=46)
    block_map: dict[tuple, Block] = {}
    for e in entries:
        chap = (e.get("chapter") or "").strip()
        pno  = e["page_no"]
        key  = (chap, pno)
        if key not in block_map:
            block_map[key] = Block(chapter=chap, page_no=pno, template="real")
        b = block_map[key]
        bbox_raw = e.get("bbox")
        bbox = BBox(*bbox_raw) if bbox_raw and len(bbox_raw) == 4 else None
        val_raw = str(e.get("value_raw") or e.get("value") or "")
        f = Field(page_no=pno, chapter=chap, role=e.get("role"),
                  label_raw=e.get("label") or "", value_raw=val_raw, bbox=bbox)
        f.reads = [Read(model="real", value_raw=val_raw, confidence=e.get("confidence", 1.0))]
        b.fields.append(f); f.block_key = b.key
    doc.blocks = list(block_map.values())
    normalize(doc); validate(doc); score(doc)
    flags = _flat_from_doc(doc)
    all_f = doc.all_fields()
    n_err  = sum(1 for f in flags if f.severity == "error")
    n_warn = sum(1 for f in flags if f.severity == "warning")
    n_auto = sum(1 for f in all_f if f.status == FieldStatus.AUTO_ACCEPTED)
    return flags, len(all_f), n_err, n_warn, n_auto


# ── Anzeige ───────────────────────────────────────────────────────────────────

def _header(flags: list[FlatFlag], n_fields: int, n_err: int, n_warn: int,
            n_auto: int, mode: str) -> None:
    titles = {"real": "Echte Pipeline  [dim](extracted_fields.json)[/dim]",
              "stub": "Stub-Pipeline  [dim](28 Testfelder)[/dim]",
              "revalidate": "Re-Validierung  [dim](JSON-Felder + neue Regeln)[/dim]"}
    colors = {"real": "bright_blue", "stub": "yellow", "revalidate": "green"}
    console.print()
    console.print(Panel(
        f"  [bold red]{n_err} Fehler[/bold red]   "
        f"[bold yellow]{n_warn} Warnungen[/bold yellow]   "
        f"[bold green]{n_auto} auto-akzeptiert[/bold green]   "
        f"[dim]{n_fields} Felder gesamt[/dim]",
        title=f"[bold]{titles.get(mode, mode)}[/bold]",
        border_style=colors.get(mode, "white"),
    ))


def cmd_overview(flags: list[FlatFlag], n_fields: int, n_err: int,
                 n_warn: int, n_auto: int, mode: str) -> None:
    _header(flags, n_fields, n_err, n_warn, n_auto, mode)
    if not flags:
        console.print("[bold green]  Keine Flags.[/bold green]")
        return

    tbl = Table(box=box.SIMPLE_HEAD, show_edge=False, padding=(0, 1))
    tbl.add_column("",       width=5,  no_wrap=True)
    tbl.add_column("Seite",  width=5,  style="dim")
    tbl.add_column("Code",   width=22, style="bold")
    tbl.add_column("Feld",   width=26)
    tbl.add_column("Ist",    width=22)
    tbl.add_column("Erwartet", width=22)

    last_code = None
    for f in flags:
        if f.code != last_code and last_code is not None:
            tbl.add_row("", "", "", "", "", "")
        last_code = f.code
        cat_col = CAT_COLOR.get(f.category, "white")
        tbl.add_row(
            SEV_RICH[f.severity],
            f"p{f.page}",
            f"[{cat_col}]{f.code}[/{cat_col}]",
            (f.label or f.role)[:25],
            str(f.actual)[:20],
            str(f.expected)[:20],
        )
    console.print(tbl)
    console.print(f"  [dim]Tipp: [bold]page 10[/bold]  [bold]code 4EYES_DISTINCT[/bold]  "
                  f"[bold]rule rule_four_eyes[/bold]  [bold]stats[/bold][/dim]")


def cmd_page(page_no: int, flags: list[FlatFlag]) -> None:
    pf = [f for f in flags if f.page == page_no]
    console.print()
    console.print(Rule(f"[bold]Seite {page_no}[/bold]  —  {len(pf)} Flag(s)"))
    if not pf:
        console.print("  [green]Keine Flags auf dieser Seite.[/green]")
        return
    for f in pf:
        _show_flag_card(f)


def cmd_code(code: str, flags: list[FlatFlag]) -> None:
    cf = [f for f in flags if f.code.lower() == code.lower()]
    console.print()
    console.print(Rule(f"[bold]{code}[/bold]  —  {len(cf)} Vorkommen"))
    rule = FLAG_CODE_TO_RULE.get(code, "?")
    meta = RULE_META.get(rule)
    if meta:
        console.print(f"  [dim]Regel: [bold]{rule}[/bold]   Kategorie: {meta[0]}[/dim]")
        console.print(f"  [italic]{meta[1]}[/italic]")
    if not cf:
        console.print("  [green]Kein Vorkommen.[/green]")
        return
    for f in cf:
        _show_flag_card(f)


def cmd_rule(name: str, flags: list[FlatFlag]) -> None:
    # Finde alle Codes die zu dieser Regel gehören
    codes = {c for c, r in FLAG_CODE_TO_RULE.items() if r == name}
    rf = [f for f in flags if f.code in codes]
    meta = RULE_META.get(name, ("?", "Unbekannte Regel"))
    console.print()
    console.print(Rule(f"[bold]{name}[/bold]  [{CAT_COLOR.get(meta[0], 'white')}]{meta[0]}[/{CAT_COLOR.get(meta[0], 'white')}]"))
    console.print(f"  [italic]{meta[1]}[/italic]")
    console.print(f"  [dim]Codes: {', '.join(sorted(codes)) or '(keine bekannten Codes)'}[/dim]")
    console.print()
    if not rf:
        console.print("  [green]Kein Vorkommen in den aktuellen Daten.[/green]")
        return
    for f in rf:
        _show_flag_card(f)


def _show_flag_card(f: FlatFlag) -> None:
    cat_col = CAT_COLOR.get(f.category, "white")
    console.print(Panel(
        f"{SEV_RICH[f.severity]}  [{cat_col}][bold]{f.code}[/bold][/{cat_col}]\n"
        f"[dim]Seite {f.page}  |  {f.chapter}  |  {f.role}[/dim]\n"
        f"[bold]Feld:[/bold]      {f.label}\n"
        f"[bold]Wert:[/bold]      {f.value!r}\n"
        f"[bold]Ist:[/bold]       [red]{f.actual}[/red]\n"
        f"[bold]Erwartet:[/bold]  [green]{f.expected}[/green]\n"
        f"[italic dim]{f.message}[/italic dim]",
        border_style={"error": "red", "warning": "yellow"}.get(f.severity, "white"),
        padding=(0, 2),
    ))


def cmd_stats(flags: list[FlatFlag], n_fields: int) -> None:
    console.print()
    console.print(Rule("[bold]Statistik[/bold]"))

    # Nach Code
    from collections import Counter
    by_code = Counter(f.code for f in flags)
    by_page = Counter(f.page for f in flags)
    by_cat  = Counter(f.category for f in flags)

    t1 = Table("Code", "Anzahl", "Regel", box=box.SIMPLE_HEAD, show_edge=False)
    for code, n in by_code.most_common(15):
        rule = FLAG_CODE_TO_RULE.get(code, "?")
        sev  = next((f.severity for f in flags if f.code == code), "?")
        col  = "red" if sev == "error" else "yellow"
        t1.add_row(f"[{col}]{code}[/{col}]", str(n), rule)

    t2 = Table("Seite", "Flags", box=box.SIMPLE_HEAD, show_edge=False)
    for pg, n in sorted(by_page.items()):
        bar = "█" * min(n, 20)
        t2.add_row(f"p{pg}", f"{bar} {n}")

    t3 = Table("Kategorie", "Anzahl", box=box.SIMPLE_HEAD, show_edge=False)
    for cat, n in by_cat.most_common():
        col = CAT_COLOR.get(cat, "white")
        t3.add_row(f"[{col}]{cat}[/{col}]", str(n))

    console.print(Columns([t1, t2, t3], padding=(0, 4)))


def cmd_rules_list() -> None:
    console.print()
    console.print(Rule("[bold]Alle Regeln[/bold]"))
    tbl = Table(box=box.SIMPLE_HEAD, show_edge=False, padding=(0, 1))
    tbl.add_column("Regel",      width=28, style="bold cyan")
    tbl.add_column("Ebene",      width=10)
    tbl.add_column("Kategorie",  width=16)
    tbl.add_column("Beschreibung")
    levels = {
        "rule_date_format": "Feld", "rule_nks": "Feld",
        "rule_range": "Feld", "rule_formula": "Feld",
        "rule_net_mass": "Block", "rule_volume": "Block",
        "rule_four_eyes": "Block", "rule_end_after_start": "Block",
        "rule_dates_document": "Dokument", "rule_kuerzel_document": "Dokument",
        "rule_xref_document": "Dokument",
    }
    for name, (cat, desc) in RULE_META.items():
        col = CAT_COLOR.get(cat, "white")
        tbl.add_row(name, levels.get(name, "?"), f"[{col}]{cat}[/{col}]", desc)
    console.print(tbl)


def cmd_find(query: str, flags: list[FlatFlag]) -> None:
    q = query.lower().strip()
    found = [f for f in flags
             if q in f.label.lower() or q in f.value.lower()
             or q in f.code.lower() or q in f.role.lower()
             or q in f.message.lower()]
    console.print()
    console.print(Rule(f"[bold]Suche: {query!r}[/bold]  —  {len(found)} Treffer"))
    for f in found:
        _show_flag_card(f)


def cmd_diff(real_flags: list[FlatFlag], stub_flags: list[FlatFlag]) -> None:
    real_codes = Counter(f.code for f in real_flags)
    stub_codes = Counter(f.code for f in stub_flags)
    all_codes  = sorted(set(real_codes) | set(stub_codes))
    console.print()
    console.print(Rule("[bold]Vergleich: Echte Daten vs Stub[/bold]"))
    tbl = Table("Code", "Echt", "Stub", "Diff", box=box.SIMPLE_HEAD, show_edge=False)
    for code in all_codes:
        r, s = real_codes.get(code, 0), stub_codes.get(code, 0)
        diff = r - s
        diff_str = f"[green]+{diff}[/green]" if diff > 0 else f"[red]{diff}[/red]" if diff < 0 else "[dim]=0[/dim]"
        tbl.add_row(code, str(r), str(s), diff_str)
    console.print(tbl)


# ── Interaktive Tester ────────────────────────────────────────────────────────

def _make_field(value_raw: str, role: str | None = None, soll: str | None = None,
                nks: int | None = None, calc_expr: str | None = None,
                conf: float = 0.9, label: str = "TestFeld", chapter: str = "DEBUG",
                page_no: int = 1) -> Field:
    f = Field(page_no=page_no, chapter=chapter, role=role, label_raw=label,
              value_raw=value_raw, nks=nks, soll=soll, calc_expr=calc_expr)
    f.reads = [Read(model="debug", value_raw=value_raw, confidence=conf)]
    vtype = detect_value_type(value_raw)
    f.value_type = vtype
    from app.pipeline.normalize import parse_date, parse_time, parse_datetime
    if vtype == "number":
        val, dec = parse_german_number(value_raw)
        f.value, f.decimals = val, dec
    elif vtype == "date":    f.value = parse_date(value_raw)
    elif vtype == "time":    f.value = parse_time(value_raw)
    elif vtype == "datetime":f.value = parse_datetime(value_raw)
    elif vtype == "bool":    f.value = value_raw.strip().lower() in {"ja","x","✓","true"}
    else:                    f.value = value_raw
    return f


ROLE_MAP = {"tare": Role.TARE_MASS, "gross": Role.GROSS_MASS, "net": Role.NET_MASS,
            "vol": Role.VOLUME, "rho": Role.DENSITY, "conc": Role.CONCENTRATION,
            "proc": Role.SIGNATURE_PROCESSED, "chk": Role.SIGNATURE_CHECKED,
            "start": Role.HOLD_START, "end": Role.HOLD_END, "calc": Role.CALC_RESULT}


def _role(s: str) -> str | None:
    s = s.strip().lower()
    return ROLE_MAP.get(s, s if s in vars(Role).values() else None)


def _int(s: str) -> int | None:
    try: return int(s.strip())
    except: return None


def _float(s: str) -> float | None:
    try: return float(s.strip().replace(",", "."))
    except: return None


def _show_flags(flags: list[Flag], ctx: str = "") -> None:
    if not flags:
        console.print(f"  [bold green]PASS[/bold green]  {ctx} — keine Flags")
        return
    for fl in flags:
        sev_col = "red" if fl.severity == Severity.ERROR else "yellow"
        console.print(
            f"  [{sev_col}][bold]{fl.code}[/bold][/{sev_col}]  "
            f"[dim]Erwartet: [green]{fl.expected}[/green]  Ist: [red]{fl.actual}[/red][/dim]\n"
            f"  [italic dim]{fl.message}[/italic dim]"
        )


def test_field_repl() -> None:
    console.print(); console.print(Rule("[bold cyan]Feld-Tester[/bold cyan]"))
    console.print("[dim]Rollen: tare gross net vol rho conc proc chk start end calc\n"
                  "Felder leer lassen = Standardwert.  q = zurück[/dim]")
    d = dict(v="10.6.2026", r="proc", soll="", nks="", calc="", conf="0.9")
    while True:
        console.print("\n[dim]──────────────────────────────────────────────[/dim]")
        try:
            d["v"]    = Prompt.ask("  value_raw ", default=d["v"])
            if d["v"].lower() in ("q","quit"): break
            d["r"]    = Prompt.ask("  role      ", default=d["r"])
            d["soll"] = Prompt.ask("  soll      ", default=d["soll"])
            d["nks"]  = Prompt.ask("  nks       ", default=d["nks"])
            d["calc"] = Prompt.ask("  calc_expr ", default=d["calc"])
            d["conf"] = Prompt.ask("  conf      ", default=d["conf"])
        except (KeyboardInterrupt, EOFError): break
        f = _make_field(d["v"], role=_role(d["r"]), soll=d["soll"] or None,
                        nks=_int(d["nks"]), calc_expr=d["calc"] or None,
                        conf=_float(d["conf"]) or 0.9)
        console.print(f"  [dim]→ type={f.value_type}  value={f.value!r}  decimals={f.decimals}[/dim]")
        flags: list[Flag] = []
        for rule in R.FIELD_RULES: flags.extend(rule(f))
        _show_flags(flags, d["v"])


def test_bilanz_repl() -> None:
    console.print(); console.print(Rule("[bold cyan]Block-Tester: Bilanzierung[/bold cyan]"))
    console.print("[dim]Alle Werte als deutsche Zahl (z.B. 1,10).  q = zurück[/dim]")
    d = dict(tare="100", gross="300", net="200", rho="1,10", vol="220")
    while True:
        console.print("\n[dim]──────────────────────────────────────────────[/dim]")
        try:
            for k in d:
                d[k] = Prompt.ask(f"  {k:<6}", default=d[k])
            if list(d.values())[0].lower() in ("q","quit"): break
        except (KeyboardInterrupt, EOFError): break
        fields = [
            _make_field(d["tare"],  role=Role.TARE_MASS,  label="m Tara"),
            _make_field(d["gross"], role=Role.GROSS_MASS, label="m Brutto"),
            _make_field(d["net"],   role=Role.NET_MASS,   label="m Netto"),
            _make_field(d["rho"],   role=Role.DENSITY,    label="rho"),
            _make_field(d["vol"],   role=Role.VOLUME,     label="V Netto"),
        ]
        b = Block(chapter="DEBUG", page_no=1, template="bilanzierung")
        b.fields = fields
        for f in fields: f.block_key = b.key
        R.rule_net_mass(b); R.rule_volume(b)
        all_f: list[Flag] = [fl for f in fields for fl in f.flags]
        console.print(f"  [dim]Tara={fields[0].value}  Brutto={fields[1].value}  "
                      f"Netto={fields[2].value}  ρ={fields[3].value}  V={fields[4].value}[/dim]")
        _show_flags(all_f)


def test_sig_repl() -> None:
    console.print(); console.print(Rule("[bold cyan]Block-Tester: Vier-Augen[/bold cyan]"))
    console.print("[dim]Format: DD.MM.YYYY / kuerzel  (z.B. 10.06.2026 / ohe).  q = zurück[/dim]")
    d = dict(proc="10.06.2026 / ohe", chk="09.06.2026 / ohe")
    while True:
        console.print("\n[dim]──────────────────────────────────────────────[/dim]")
        try:
            d["proc"] = Prompt.ask("  Bearbeitet", default=d["proc"])
            if d["proc"].lower() in ("q","quit"): break
            d["chk"]  = Prompt.ask("  Geprueft  ", default=d["chk"])
        except (KeyboardInterrupt, EOFError): break
        fp = _make_field(d["proc"], role=Role.SIGNATURE_PROCESSED, label="Bearbeitet")
        fc = _make_field(d["chk"],  role=Role.SIGNATURE_CHECKED,   label="Geprueft")
        b  = Block(chapter="DEBUG", page_no=1, template="signature")
        b.fields = [fp, fc]; fp.block_key = fc.block_key = b.key
        R.rule_four_eyes(b)
        _show_flags([*fp.flags, *fc.flags])


def test_range_repl() -> None:
    console.print(); console.print(Rule("[bold cyan]Feld-Tester: Bereichsprüfung[/bold cyan]"))
    console.print("[dim]Soll: '20 - 30'  '<= 65'  '>= 5'  '11,95 (8,56 - 23,30)'.  q = zurück[/dim]")
    d = dict(v="32", soll="20 - 30", r="calc")
    while True:
        console.print("\n[dim]──────────────────────────────────────────────[/dim]")
        try:
            d["v"]    = Prompt.ask("  value", default=d["v"])
            if d["v"].lower() in ("q","quit"): break
            d["soll"] = Prompt.ask("  soll ", default=d["soll"])
            d["r"]    = Prompt.ask("  role ", default=d["r"])
        except (KeyboardInterrupt, EOFError): break
        parsed = parse_soll(d["soll"])
        console.print(f"  [dim]parse_soll → {parsed}[/dim]")
        f = _make_field(d["v"], role=_role(d["r"]), soll=d["soll"] or None)
        console.print(f"  [dim]normalisiert: {f.value!r}[/dim]")
        _show_flags(R.rule_range(f), d["v"])


def test_formula_repl() -> None:
    console.print(); console.print(Rule("[bold cyan]Feld-Tester: Formelprüfung[/bold cyan]"))
    console.print("[dim]calc_expr: z.B. '6,6 * 45 - 4,3 * 0,75'  value: eingetragenes Ergebnis.  q = zurück[/dim]")
    d = dict(v="2021,78", calc="6,6 * 45 - 4,3 * 0,75", nks="", r="calc")
    while True:
        console.print("\n[dim]──────────────────────────────────────────────[/dim]")
        try:
            d["v"]    = Prompt.ask("  value    ", default=d["v"])
            if d["v"].lower() in ("q","quit"): break
            d["calc"] = Prompt.ask("  calc_expr", default=d["calc"])
            d["nks"]  = Prompt.ask("  nks      ", default=d["nks"])
            d["r"]    = Prompt.ask("  role     ", default=d["r"])
        except (KeyboardInterrupt, EOFError): break
        console.print(f"  [dim]safe_arith → {R.safe_arith(d['calc'])}[/dim]")
        f = _make_field(d["v"], role=_role(d["r"]), nks=_int(d["nks"]), calc_expr=d["calc"] or None)
        _show_flags(R.rule_formula(f), d["v"])


def test_xref_repl() -> None:
    console.print(); console.print(Rule("[bold cyan]Dokument-Tester: XREF / Übertrag[/bold cyan]"))
    console.print("[dim]Quell-Kapitel + Rolle + Wert, dann Übertrag-Kapitel + Wert.  q = zurück[/dim]")
    d = dict(sc="5.3.1", sr="net", sv="200", xc="5.4", xv="200")
    while True:
        console.print("\n[dim]──────────────────────────────────────────────[/dim]")
        try:
            d["sc"] = Prompt.ask("  Quell-Kapitel ", default=d["sc"])
            if d["sc"].lower() in ("q","quit"): break
            d["sr"] = Prompt.ask("  Quell-Rolle   ", default=d["sr"])
            d["sv"] = Prompt.ask("  Quell-Wert    ", default=d["sv"])
            d["xc"] = Prompt.ask("  Übertrag-Kap  ", default=d["xc"])
            d["xv"] = Prompt.ask("  Übertrag-Wert ", default=d["xv"])
        except (KeyboardInterrupt, EOFError): break
        role_val = _role(d["sr"]) or d["sr"]
        src_f = _make_field(d["sv"], role=role_val, label=f"Quellwert ({d['sc']})", chapter=d["sc"])
        xref_f = _make_field(d["xv"], role=role_val,
                             label=f"Übertrag Kapitel {d['sc']}", chapter=d["xc"])
        doc = Document(doc_no="XREF_TEST", title="XREF Test")
        b1 = Block(chapter=d["sc"], page_no=1, template="test"); b1.fields = [src_f]; src_f.block_key = b1.key
        b2 = Block(chapter=d["xc"], page_no=2, template="test"); b2.fields = [xref_f]; xref_f.block_key = b2.key
        doc.blocks = [b1, b2]; normalize(doc); R.rule_xref_document(doc)
        _show_flags(xref_f.flags)


# ── Watch-Modus ───────────────────────────────────────────────────────────────
WATCH_FILES = [
    BACKEND / "app" / "pipeline" / "validate" / "rules.py",
    BACKEND / "app" / "pipeline" / "validate" / "engine.py",
    BACKEND / "app" / "pipeline" / "normalize.py",
    BACKEND / "app" / "pipeline" / "validate" / "uncertainty.py",
]


def cmd_watch(mode: str = "revalidate") -> None:
    console.print(); console.print(Rule(f"[bold yellow]Watch-Modus  ({mode})  —  Strg+C zum Beenden[/bold yellow]"))
    for p in WATCH_FILES:
        console.print(f"  [dim]{p.name}[/dim]")
    mtimes = {p: p.stat().st_mtime for p in WATCH_FILES if p.exists()}
    last: tuple[int, int] | None = None
    try:
        while True:
            changed = any(
                p.stat().st_mtime != mtimes.get(p)
                for p in WATCH_FILES if p.exists()
            )
            if changed or last is None:
                for p in WATCH_FILES:
                    if p.exists(): mtimes[p] = p.stat().st_mtime
                mods = ["app.pipeline.normalize","app.pipeline.validate.rules",
                        "app.pipeline.validate.engine","app.pipeline.validate.uncertainty"]
                for m in mods:
                    if m in sys.modules: importlib.reload(sys.modules[m])
                try:
                    if mode == "stub":
                        flags, n_fields, n_err, n_warn, n_auto = load_stub()
                    else:
                        flags, n_fields, n_err, n_warn, n_auto = load_revalidate()
                    delta = ""
                    if last:
                        de = n_err - last[0]; dw = n_warn - last[1]
                        if de or dw:
                            delta = f"  [dim](Δ Fehler: {'[red]' if de>0 else '[green]'}{de:+d}{'[/red]' if de>0 else '[/green]'}  Δ Warn: {dw:+d})[/dim]"
                    ts = time.strftime("%H:%M:%S")
                    console.print(
                        f"  [dim]{ts}[/dim]  [bold red]{n_err} Fehler[/bold red]  "
                        f"[bold yellow]{n_warn} Warnungen[/bold yellow]{delta}"
                    )
                    last = (n_err, n_warn)
                except Exception as e:
                    console.print(f"  [red]Fehler: {e}[/red]")
            time.sleep(0.4)
    except KeyboardInterrupt:
        console.print("\n  [dim]Watch beendet.[/dim]")


# ── Hilfe ─────────────────────────────────────────────────────────────────────
HELP = """
[bold]Daten-Modus:[/bold]
  [cyan]run[/cyan]              Echte Daten (JSON) — exaktes Match mit Web-App [dim](21 Fehler)[/dim]
  [cyan]run stub[/cyan]         Stub-Pipeline re-run [dim](28 Felder, für Regel-Tests)[/dim]
  [cyan]run revalidate[/cyan]   JSON-Felder + Regeln neu ausführen [dim](zeigt Regel-Änderungen)[/dim]

[bold]Navigation:[/bold]
  [cyan]page <N>[/cyan]         Alle Flags auf Seite N  [dim](z.B. page 10)[/dim]
  [cyan]code <CODE>[/cyan]      Alle Vorkommen eines Flag-Codes  [dim](z.B. code 4EYES_DISTINCT)[/dim]
  [cyan]rule <name>[/cyan]      Alle Flags einer Regel  [dim](z.B. rule four_eyes)[/dim]
  [cyan]find <text>[/cyan]      Flags nach Feld/Wert/Code durchsuchen
  [cyan]stats[/cyan]            Verteilung nach Code / Seite / Kategorie
  [cyan]diff[/cyan]             Echte Daten vs Stub vergleichen
  [cyan]rules[/cyan]            Alle Regeln auflisten

[bold]Interaktive Tester:[/bold]
  [cyan]test field[/cyan]       Alle Feld-Regeln interaktiv testen
  [cyan]test bilan[/cyan]       Bilanzierung: net_mass + volume
  [cyan]test sig[/cyan]         Vier-Augen-Prinzip
  [cyan]test range[/cyan]       Bereichsprüfung (rule_range)
  [cyan]test form[/cyan]        Formelprüfung (rule_formula)
  [cyan]test xref[/cyan]        Übertrag / Kapitel-Querverweis

[bold]Utilities:[/bold]
  [cyan]arith <expr>[/cyan]     Ausdruck auswerten: arith 6,6 * 45 - 4,3 * 0,75
  [cyan]soll <spec>[/cyan]      Soll-Spec parsen: soll 20 - 30
  [cyan]watch[/cyan]            Auto-reload bei rules.py-Änderungen  [dim](revalidate)[/dim]
  [cyan]watch stub[/cyan]       Watch im Stub-Modus
  [cyan]clear / q[/cyan]        Bildschirm / Beenden
"""

# ── Hauptprogramm ─────────────────────────────────────────────────────────────

def _match_rule(token: str) -> str | None:
    token = token.lower().replace("rule_", "").strip()
    for name in RULE_META:
        if token in name: return name
    return None

from collections import Counter   # noqa: E402  (schon oben importiert, hier nochmal für Inline)


def main() -> None:
    args = sys.argv[1:]
    start_mode = "stub" if "--stub" in args else "real"

    console.clear()
    console.print(Panel(
        "[bold bright_blue]BioDize — Rule Debugger[/bold bright_blue]  [dim]v2[/dim]\n"
        "[dim][bold]help[/bold] für alle Befehle  |  [bold]run[/bold] = echte Daten  |  "
        "[bold]run stub[/bold] = Stub-Pipeline[/dim]",
        border_style="bright_blue", padding=(1, 4),
    ))

    if "--watch" in args:
        cmd_watch()
        return

    # Initiales Laden
    try:
        if start_mode == "real" and RESULTS_JSON.exists():
            flags, n_fields, n_err, n_warn, n_auto = load_real()
            mode = "real"
        else:
            flags, n_fields, n_err, n_warn, n_auto = load_stub()
            mode = "stub"
        cmd_overview(flags, n_fields, n_err, n_warn, n_auto, mode)
    except Exception as e:
        console.print(f"[red]Start-Fehler: {e}[/red]")
        traceback.print_exc()
        flags, n_fields, n_err, n_warn, n_auto, mode = [], 0, 0, 0, 0, "stub"

    stub_flags: list[FlatFlag] | None = None

    while True:
        console.print()
        try:
            cmd = Prompt.ask("[bold bright_blue]debug[/bold bright_blue]").strip()
        except (KeyboardInterrupt, EOFError): break

        if not cmd: continue
        parts = cmd.split(None, 1)
        verb  = parts[0].lower()
        rest  = parts[1].strip() if len(parts) > 1 else ""

        try:
            if verb in ("q", "quit", "exit"): break

            elif verb in ("help", "h", "?"): console.print(HELP)

            elif verb == "clear": console.clear()

            elif verb == "run":
                sub = rest.lower()
                if sub in ("stub",):
                    flags, n_fields, n_err, n_warn, n_auto = load_stub(); mode = "stub"
                elif sub in ("revalidate", "reval", "re"):
                    flags, n_fields, n_err, n_warn, n_auto = load_revalidate(); mode = "revalidate"
                else:
                    flags, n_fields, n_err, n_warn, n_auto = load_real(); mode = "real"
                cmd_overview(flags, n_fields, n_err, n_warn, n_auto, mode)

            elif verb == "page":
                try: pg = int(rest)
                except ValueError: console.print("[red]Verwendung: page <Seitenzahl>[/red]"); continue
                cmd_page(pg, flags)

            elif verb == "code":
                if not rest: console.print("[red]Verwendung: code <FLAG_CODE>[/red]"); continue
                cmd_code(rest.upper(), flags)

            elif verb == "rule":
                name = _match_rule(rest) if rest else None
                if not name: console.print(f"[red]Regel nicht gefunden: {rest!r}[/red]"); cmd_rules_list(); continue
                cmd_rule(name, flags)

            elif verb == "rules": cmd_rules_list()

            elif verb == "find":
                if not rest: console.print("[red]Verwendung: find <text>[/red]"); continue
                cmd_find(rest, flags)

            elif verb == "stats": cmd_stats(flags, n_fields)

            elif verb == "diff":
                if stub_flags is None:
                    console.print("  [dim]Lade Stub-Daten für Vergleich ...[/dim]")
                    stub_flags, *_ = load_stub()
                real_f, *_ = load_real() if RESULTS_JSON.exists() else (flags, 0, 0, 0, 0)
                cmd_diff(real_f, stub_flags)

            elif verb == "test":
                sub = rest.lower()
                if   sub.startswith("field") or sub=="f":  test_field_repl()
                elif sub.startswith("bilan") or sub=="b":  test_bilanz_repl()
                elif sub.startswith("sig")   or sub=="s":  test_sig_repl()
                elif sub.startswith("range") or sub=="r":  test_range_repl()
                elif sub.startswith("form")  or sub=="fo": test_formula_repl()
                elif sub.startswith("xref")  or sub=="x":  test_xref_repl()
                else: console.print("  [red]Optionen: field  bilan  sig  range  form  xref[/red]")

            elif verb == "watch": cmd_watch("stub" if rest == "stub" else "revalidate")

            elif verb == "arith":
                console.print(f"  [dim]{rest!r}[/dim] → [bold]{R.safe_arith(rest)}[/bold]")

            elif verb == "soll":
                console.print(f"  [dim]{rest!r}[/dim] → [bold]{parse_soll(rest)}[/bold]")

            else:
                console.print(f"  [red]Unbekannt:[/red] {cmd!r}  ([bold]help[/bold])")

        except Exception as e:
            console.print(f"  [bold red]Fehler:[/bold red] {e}")
            traceback.print_exc()

    console.print("\n  [dim]Debugger beendet.[/dim]")


if __name__ == "__main__":
    main()
