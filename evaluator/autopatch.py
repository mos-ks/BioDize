"""
BioDize — Autopatch Prompt Generator v2
=========================================
Generiert EINEN optimierten Prompt pro Fehlertyp (nicht pro Vorkommen).
Gruppiert ähnliche Fehler, gibt Domain-Kontext, konkrete Handlungsanweisungen.

Starten:  py autopatch.py                 # alle Errors
          py autopatch.py --warnings      # auch Warnungen
          py autopatch.py --code 4EYES    # nur bestimmter Code
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()  # evaluator/ -> repo root
VENV_PY = ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
if VENV_PY.exists() and Path(sys.executable).resolve() != VENV_PY.resolve():
    sys.exit(subprocess.run([str(VENV_PY)] + sys.argv).returncode)

BACKEND      = ROOT / "backend"
RULES_FILE   = BACKEND / "app" / "pipeline" / "validate" / "rules.py"
RESULTS_JSON = ROOT / "results" / "extracted_fields.json"
PAGES_DIR    = BACKEND / "var" / "pages"
CROPS_DIR    = ROOT / "crops"

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

try:
    from rich.console import Console
    from rich.panel import Panel
except ImportError:
    subprocess.run([str(VENV_PY), "-m", "pip", "install", "rich", "--quiet"])
    from rich.console import Console
    from rich.panel import Panel

from PIL import Image

console = Console(force_terminal=True)

# ---------------------------------------------------------------------------
# Domain-Kontext pro Fehlertyp — das ist was die Prompts nützlich macht
# ---------------------------------------------------------------------------

DOMAIN_CONTEXT = {
    "4EYES_DISTINCT": """\
**Pharma-Kontext (GMP §5.2):** Jeder Prozessschritt muss von ZWEI verschiedenen Personen
unterschrieben werden. Bearbeitet-Kürzel ≠ Geprüft-Kürzel ist eine GMP-Kernanforderung.

**Was der Scan zeigen muss:** Zwei verschiedene Handschriften in den Kürzel-Feldern.
**Typische OCR-Fehler:** Ähnliche Kürzel werden verwechselt (z.B. "ohe" vs "ohr", "han" vs "hau").
**Wichtig:** Kürzel sind 2-3 Buchstaben, handgeschrieben — prüfe ob Buchstaben ambig sind.""",

    "4EYES_ORDER": """\
**Pharma-Kontext:** Geprüft-Datum MUSS nach Bearbeitet-Datum liegen (review follows execution).
Wenn Geprüft-Datum früher ist: entweder Dokumentationsfehler oder OCR-Jahresverwechslung.

**Typische OCR-Fehler:** Jahresziffern werden verwechselt (2026→2025, 2026→2076).
**Prüfe:** Sind die Jahreszahlen im Scan eindeutig oder ambig?""",

    "CALC_NET_MASS": """\
**Formel:** m_Netto = m_Brutto - m_Tara
**Typische Fehler:** Tippfehler beim Eintragen, falsche Einheit, Übertragsfehler vom vorherigen Block.
**OCR-Fehler:** Ziffern 3/8, 6/0, 1/7 werden oft verwechselt.
**Prüfe:** Lies alle drei Werte (Tara, Brutto, Netto) direkt vom Scan ab.""",

    "CALC_FORMULA": """\
**Kontext:** Das Formular druckt eine Formel mit Lücken vor. Der Mitarbeiter trägt Werte ein
und berechnet das Ergebnis handschriftlich. Die Regel berechnet die Formel nach.
**Typische Fehler:** Falsches Ergebnis eingetragen, Kommafehler (1,18 vs 11,8), Einheitenfehler.
**Prüfe:** Was steht links von "=" im Scan? Was rechts? Ist das Ergebnis plausibel?""",

    "RANGE_SOLL": """\
**Kontext:** Das Formular gibt einen Sollbereich vor (z.B. "20-30 Hübe/min"). Der eingetragene
Wert muss in diesem Bereich liegen. Liegt er außerhalb → Abweichung, muss dokumentiert werden.
**Typische Fehler:** Wert korrekt eingetragen aber Sollbereich falsch gelesen (OCR).
**Prüfe:** Was steht im Soll-Feld? Was ist der eingetragene Istwert? Stimmt der Vergleich?""",

    "DATE_BEFORE_PRINT": """\
**Kontext:** Das Chargenprotokoll wurde am 09.06.2026 gedruckt. Alle handgeschriebenen Daten
müssen ≥ 09.06.2026 sein. Davor liegende Daten = Dokumentationsfehler oder OCR-Jahresfehler.
**Häufigster OCR-Fehler:** "2026" wird als "2025" gelesen (6→5 bei schlechter Handschrift).
**Prüfe:** Ist die letzte Jahresziffer eindeutig eine 6 oder könnte sie eine 5 sein?""",

    "DATE_FAR_FUTURE": """\
**Kontext:** Daten > 180 Tage nach Druckdatum (09.06.2026) sind unplausibel.
**Fast immer OCR-Fehler:** "2026" → "2076" (2→7 bei ähnlicher Handschrift) oder ähnliches.
**Prüfe:** Schau dir die Jahreszahl genau an. Ist sie eindeutig lesbar?""",

    "KUERZEL_UNKNOWN": """\
**Kontext:** Auf Seite 4 steht die Personalliste (Beteiligte Personen) mit allen Kürzeln.
Registrierte Kürzel: "ohe", "han". Jedes Unterschriftskürzel muss dort stehen (±2 Zeichen OCR-Toleranz).
**Prüfe:** Welches Kürzel ist tatsächlich im Scan? Ähnelt es "ohe" oder "han"?""",

    "XREF_MISMATCH": """\
**Kontext:** "Übertrag Kapitel X" bedeutet: dieser Wert wurde aus Kapitel X übernommen.
Er muss identisch mit dem Quellwert sein. Abweichung = falscher Übertrag oder OCR-Lesefehler.
**Häufig:** Zeitangaben werden falsch übertragen (09:27 vs 08:27), oder Datum-Jahresfehler.
**Prüfe:** Was steht tatsächlich im Übertrag-Feld? Passt es zum Quellwert?""",

    "CALC_ROUNDING": """\
**Kontext:** Das berechnete Ergebnis weicht minimal vom erwarteten ab — wahrscheinlich Rundung.
Ist kein echter Fehler, nur eine Warnung zur manuellen Prüfung.
**Prüfe:** Ist die Abweichung durch korrektes Runden erklärbar?""",
}

FLAG_CODE_TO_RULE = {
    "FMT_DATE_PADDING":     "rule_date_format",
    "FMT_NKS":              "rule_nks",
    "RANGE_SOLL":           "rule_range",
    "RANGE_SETPOINT":       "rule_range",
    "CALC_FORMULA":         "rule_formula",
    "CALC_ROUNDING":        "rule_formula",
    "CALC_NET_MASS":        "rule_net_mass",
    "CALC_VOLUME":          "rule_volume",
    "4EYES_ORDER":          "rule_four_eyes",
    "4EYES_DISTINCT":       "rule_four_eyes",
    "TIME_END_AFTER_START": "rule_end_after_start",
    "DATE_BEFORE_PRINT":    "rule_dates_document",
    "DATE_FAR_FUTURE":      "rule_dates_document",
    "KUERZEL_UNKNOWN":      "rule_kuerzel_document",
    "XREF_MISMATCH":        "rule_xref_document",
}

# Schwere-Priorität für Sortierung
CODE_PRIORITY = {
    "CALC_NET_MASS": 0, "CALC_FORMULA": 1, "CALC_VOLUME": 2,
    "RANGE_SOLL": 3, "4EYES_ORDER": 4, "4EYES_DISTINCT": 5,
    "DATE_BEFORE_PRINT": 6, "DATE_FAR_FUTURE": 7,
    "KUERZEL_UNKNOWN": 8, "XREF_MISMATCH": 9,
}


def extract_rule_source(rule_name: str | None) -> str:
    if not rule_name:
        return "(uncertainty scorer)"
    try:
        src   = RULES_FILE.read_text(encoding="utf-8")
        tree  = ast.parse(src)
        lines = src.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == rule_name:
                return "\n".join(lines[node.lineno - 1 : node.end_lineno])
    except Exception:
        pass
    return f"# {rule_name} nicht gefunden"


def crop_page(page_no: int, bbox: list[float], pad: float = 0.08) -> Path | None:
    img_path = PAGES_DIR / f"page_{page_no:03d}.png"
    if not img_path.exists():
        return None
    img = Image.open(img_path)
    w, h = img.size
    x0 = max(0, int((bbox[0] - pad) * w))
    y0 = max(0, int((bbox[1] - pad) * h))
    x1 = min(w, int((bbox[2] + pad) * w))
    y1 = min(h, int((bbox[3] + pad) * h))
    if x1 <= x0 or y1 <= y0:
        return None
    crop = img.crop((x0, y0, x1, y1))
    CROPS_DIR.mkdir(exist_ok=True)
    out = CROPS_DIR / f"p{page_no:02d}_{bbox[0]:.2f}.png"
    crop.save(str(out))
    return out


def get_block_context(page_no: int, chapter: str, all_fields: list[dict]) -> str:
    """Alle Felder desselben Blocks — Kontext für Berechnungsfehler."""
    block = [f for f in all_fields
             if f["page_no"] == page_no
             and (f.get("chapter") or "") == chapter
             and f.get("role")]
    if not block:
        return ""
    lines = []
    for f in block:
        flags_str = ", ".join(fl["code"] for fl in f.get("flags", []))
        flag_mark = f"  ← {flags_str}" if flags_str else ""
        lines.append(f"  {f.get('label','?'):<35} = {f.get('value_raw','?'):<15} "
                     f"[role={f.get('role','?')}]{flag_mark}")
    return "\n".join(lines)


def build_group_prompt(code: str, occurrences: list[dict],
                       rule_name: str | None, rule_src: str,
                       all_fields: list[dict]) -> str:
    """Einen hochwertigen Prompt für ALLE Vorkommen eines Fehlercodes."""

    domain = DOMAIN_CONTEXT.get(code, "")
    sev    = occurrences[0]["severity"].upper()
    n      = len(occurrences)

    # Crops generieren
    crops: list[tuple[dict, Path | None]] = []
    for occ in occurrences:
        bbox = occ.get("bbox")
        path = crop_page(occ["page_no"], bbox) if bbox else None
        crops.append((occ, path))

    # Vorkommen-Tabelle
    occ_lines = []
    for i, (occ, crop_path) in enumerate(crops, 1):
        occ_lines.append(
            f"### Vorkommen {i}/{n} — Seite {occ['page_no']}, Kapitel {occ.get('chapter','?')}\n"
            f"- Feld: **{occ.get('label','?')}** (Rolle: `{occ.get('role','?')}`)\n"
            f"- OCR-Wert: `{occ.get('value_raw','?')}`\n"
            f"- Erwartet: `{occ.get('expected','?')}`  →  Gefunden: `{occ.get('actual','?')}`\n"
            f"- Meldung: {occ.get('message','?')}\n"
            + (f"- **Screenshot:** `{crop_path}` ← Read-Tool\n"
               if crop_path else "- Screenshot: nicht verfügbar\n")
            + (f"\n**Block-Kontext (alle Felder dieser Seite/Kapitel):**\n```\n"
               f"{get_block_context(occ['page_no'], occ.get('chapter',''), all_fields)}\n```\n"
               if code in ("CALC_NET_MASS","CALC_FORMULA","CALC_VOLUME","RANGE_SOLL","XREF_MISMATCH")
               else "")
        )

    # Aktion
    action = _action_instructions(code, n, crops)

    return f"""# BioDize Autopatch — `{code}` ({n}× {sev})

## Domain-Kontext
{domain}

## Regelcode (`{rule_name or 'N/A'}`)
```python
{rule_src}
```

## {n} Vorkommen

{"".join(occ_lines)}
## Deine Aufgabe

{action}
"""


def _action_instructions(code: str, n: int, crops: list) -> str:
    """Konkrete, code-spezifische Handlungsanweisungen."""

    crop_instruction = "\n".join(
        f"- Seite {occ['page_no']}: `Read: {p}`"
        for occ, p in crops if p
    ) or "- Keine Screenshots verfügbar"

    base = f"**Schritt 1 — Alle Screenshots lesen:**\n{crop_instruction}\n\n"

    if code == "4EYES_DISTINCT":
        return base + f"""\
**Schritt 2 — Für jedes Vorkommen entscheiden:**
Prüfe ob Bearbeitet-Kürzel und Geprüft-Kürzel im Scan WIRKLICH identisch sind.

- **Identisch (z.B. beide "ohe")** → LEGITIMER FEHLER. Kein Patch. Notiere: "p[X]: legitim"
- **Verschieden aber OCR-Fehler (z.B. "ohe" vs "ohr")** → OCR-FEHLER.
  Korrektur: `py bulk_review.py` und manuell den richtigen Wert eintragen
- **Regel feuert obwohl Kürzel verschieden sind** → REGELBUG → patche `rule_four_eyes`

**Schritt 3 — Antwort:**
Für jede der {n} Seiten: "p[X]: legitim / OCR-Fehler ([was steht wirklich da]) / Regelbug"
Falls Regelbugs: patche `{RULES_FILE}` direkt."""

    elif code == "4EYES_ORDER":
        return base + """\
**Schritt 2 — Jahreszahlen im Scan prüfen:**
Lies beide Daten (Bearbeitet / Geprüft) direkt vom Scan ab.

- **Geprüft-Datum tatsächlich früher** → LEGITIMER FEHLER. Kein Patch.
- **OCR hat Jahreszahl falsch gelesen** (z.B. 2026→2025) → OCR-FEHLER.
  Wenn häufig: Normalisierungsregel in `normalize.py` verbessern.
- **Regel vergleicht Daten falsch** → REGELBUG → patche `rule_four_eyes`

**Schritt 3:** "p[X]: legitim / OCR-Fehler (richtig: [datum]) / Regelbug" """

    elif code in ("CALC_NET_MASS", "CALC_FORMULA", "CALC_VOLUME"):
        formula = {"CALC_NET_MASS": "Netto = Brutto - Tara",
                   "CALC_VOLUME":   "Volumen = Netto × Dichte",
                   "CALC_FORMULA":  "Formel aus calc_expr"}[code]
        return base + f"""\
**Schritt 2 — Alle Werte im Block vom Scan ablesen:**
Formel: `{formula}`

Lies JEDEN Wert direkt aus dem Scan (nicht aus der DB). Häufige OCR-Fehler:
- Komma statt Punkt (1,8 vs 18)
- Ähnliche Ziffern: 3/8, 6/0, 1/7, 5/6

- **Rechenfehler im Dokument** → LEGITIMER FEHLER. Kein Patch.
- **OCR hat Wert falsch gelesen** → OCR-FEHLER. Korrigiere den Wert via API oder bulk_review.
- **Regel berechnet falsch** → REGELBUG → patche die Regel.

**Schritt 3:** "p[X]: legitim (Tara=[X], Brutto=[Y], Netto=[Z]) / OCR-Fehler / Regelbug" """

    elif code == "RANGE_SOLL":
        return base + """\
**Schritt 2 — Wert und Sollbereich vom Scan ablesen:**

Lies BEIDE direkt aus dem Scan:
1. Was steht im SOLL-Feld? (gedruckt auf dem Formular)
2. Was steht als IST-Wert? (handgeschrieben)

- **Wert wirklich außerhalb Soll** → LEGITIMER FEHLER (Abweichung). Kein Patch.
- **Sollbereich falsch gelesen (OCR)** → Regel feuert fälschlicherweise → Regelbugs möglich.
- **Istwert falsch gelesen (OCR)** → OCR-FEHLER. Wert korrigieren.

**Schritt 3:** "p[X]: legitim (Soll=[X], Ist=[Y]) / OCR-Fehler / Regelbug" """

    elif code in ("DATE_BEFORE_PRINT", "DATE_FAR_FUTURE"):
        return base + """\
**Schritt 2 — Jahreszahl im Scan genau analysieren:**

Druckdatum: 09.06.2026. Bekannte OCR-Fehler: 2026→2025 (6/5 ähnlich) oder 2026→2076 (2/7).

Für jedes Vorkommen:
- **Jahreszahl im Scan eindeutig falsch** → LEGITIMER FEHLER im Dokument.
- **Handschrift ambig (6 sieht aus wie 5/7)** → OCR-FEHLER.
  Fix: `_correct_year()` in `normalize.py` bereits vorhanden — prüfe ob sie greift.
  Falls nicht: verbessere die Funktion für diesen spezifischen Fall.

**Schritt 3:** "p[X]: legitim / OCR-Fehler (richtig: 2026, OCR las: [X]) — normalize.py fix nötig: ja/nein" """

    elif code == "KUERZEL_UNKNOWN":
        return base + """\
**Schritt 2 — Kürzel im Scan mit Personalliste vergleichen:**

Registrierte Kürzel: `ohe`, `han` (aus Seite 4, Beteiligte Personen)
Edit-Distance-Toleranz: 2 Zeichen

- **Kürzel tatsächlich unbekannt** → LEGITIMER FEHLER (Person nicht registriert).
- **Kürzel ähnelt registriertem (OCR-Rauschen)** → Toleranz möglicherweise zu niedrig.
  Patch: erhöhe max_edits in `rule_kuerzel_document`.
- **Kürzel im Scan klar lesbar und registriert** → REGELBUG im Vergleich.

**Schritt 3:** "p[X]: legitim / OCR-Fehler (ähnelt [ohe/han]) / Regelbug (max_edits erhöhen)" """

    elif code == "XREF_MISMATCH":
        return base + """\
**Schritt 2 — Übertrag-Wert und Quellwert vergleichen:**

Lies den Übertrag-Wert direkt aus dem Scan. Vergleiche mit dem Block-Kontext (Quellwert oben).

- **Werte tatsächlich verschieden** → LEGITIMER FEHLER (falscher Übertrag).
- **OCR hat Übertrag-Wert falsch gelesen** → OCR-FEHLER. Kein Regelbug.
- **Regel vergleicht falsch (z.B. Typ-Mismatch float vs string)** → REGELBUG → patche `rule_xref_document`.

**Schritt 3:** "p[X]: legitim / OCR-Fehler (richtig: [wert]) / Regelbug" """

    else:
        return base + """\
**Schritt 2:** Lies die Screenshots. Entscheide:
- LEGITIMER FEHLER → Kein Patch nötig
- OCR-FEHLER → Wert im System korrigieren
- REGELBUG → Patche die Regel in `rules.py`

**Schritt 3:** Antworte mit deinem Verdict pro Vorkommen + Patch falls nötig."""


def main() -> None:
    args             = sys.argv[1:]
    include_warnings = "--warnings" in args or "-w" in args
    code_filter      = next((args[i+1].upper() for i,a in enumerate(args)
                             if a == "--code" and i+1 < len(args)), None)

    if not RESULTS_JSON.exists():
        console.print("[red]results/extracted_fields.json nicht gefunden.[/red]")
        sys.exit(1)

    data       = json.loads(RESULTS_JSON.read_text(encoding="utf-8"))
    all_fields = data["fields"]

    # Alle Flags mit Feld-Kontext sammeln
    all_flags = []
    for f in all_fields:
        for fl in f.get("flags", []):
            all_flags.append({**fl,
                "page_no":   f["page_no"],
                "chapter":   f.get("chapter", ""),
                "label":     f.get("label", ""),
                "role":      f.get("role", ""),
                "value_raw": f.get("value_raw") or f.get("value", ""),
                "bbox":      f.get("bbox"),
            })

    filtered = [f for f in all_flags
                if (include_warnings or f["severity"] == "error")
                and (not code_filter or f["code"].startswith(code_filter))]

    if not filtered:
        console.print("[yellow]Keine Flags nach Filter.[/yellow]")
        return

    # Nach Code gruppieren
    by_code: dict[str, list[dict]] = defaultdict(list)
    for f in filtered:
        by_code[f["code"]].append(f)

    # Sortieren nach Priorität
    sorted_codes = sorted(by_code.keys(),
                          key=lambda c: (CODE_PRIORITY.get(c, 99), c))

    console.print()
    console.print(Panel(
        f"  [bold]{len(sorted_codes)} Fehlertypen[/bold]   "
        f"[bold red]{sum(1 for f in filtered if f['severity']=='error')} Errors[/bold red]   "
        f"[bold yellow]{sum(1 for f in filtered if f['severity']=='warning')} Warnungen[/bold yellow]   "
        f"[dim]{len(filtered)} Vorkommen gesamt[/dim]",
        title="[bold]BioDize Autopatch v2 — Gruppen-Prompts[/bold]",
        border_style="bright_blue",
    ))

    # Pro Gruppe einen Prompt bauen
    prompts = []
    for code in sorted_codes:
        occs      = by_code[code]
        rule_name = FLAG_CODE_TO_RULE.get(code)
        rule_src  = extract_rule_source(rule_name)
        prompt    = build_group_prompt(code, occs, rule_name, rule_src, all_fields)
        prompts.append((code, len(occs), prompt))
        console.print(f"  [dim]{code:<25} {len(occs)} Vorkommen[/dim]")

    # In Datei speichern
    out_file = ROOT / "autopatch_prompts.md"
    separator = "\n\n" + "─" * 80 + "\n\n"
    content = separator.join(p for _, _, p in prompts)
    out_file.write_text(content, encoding="utf-8")

    console.print(f"\n  [green]{len(prompts)} Gruppen-Prompts gespeichert: {out_file}[/green]")
    console.print(f"  [dim]Statt {len(filtered)} Einzel-Prompts → {len(prompts)} gruppierte Prompts[/dim]")

    # Notepad öffnen
    subprocess.Popen(["notepad.exe", str(out_file)])
    input("\n  Enter druecken zum Schliessen...")


if __name__ == "__main__":
    main()
