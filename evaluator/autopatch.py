"""
BioDize — Autopatch Prompt Generator v3
=========================================
Erweitert um:
  - Bbox-Kollisionserkennung (ueberlappende Felder)
  - Ground-Truth-Abgleich (Coverage, Wertgenauigkeit)
  - Layout-Konsistenz-Check (gleiche Positionen in neuen Batches?)
  - Cross-Batch-Validierung

Starten:  py autopatch.py                  # alle Errors + volle Analyse
          py autopatch.py --warnings       # auch Warnungen
          py autopatch.py --code 4EYES     # nur bestimmter Code
          py autopatch.py --page 11        # nur eine Seite
          py autopatch.py --bbox-only      # nur Kollisionsanalyse
          py autopatch.py --gt-only        # nur Ground-Truth-Vergleich
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT    = Path(__file__).parent.parent.resolve()
VENV_PY = ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
if VENV_PY.exists() and Path(sys.executable).resolve() != VENV_PY.resolve():
    sys.exit(subprocess.run([str(VENV_PY)] + sys.argv).returncode)

BACKEND      = ROOT / "backend"
RULES_FILE   = BACKEND / "app" / "pipeline" / "validate" / "rules.py"
RESULTS_JSON = ROOT / "results" / "extracted_fields.json"
PAGES_DIR    = BACKEND / "var" / "pages"
CROPS_DIR    = ROOT / "crops"
GT_DIR       = ROOT / "ground_truth"
OUT_FILE     = ROOT / "autopatch_prompts.md"

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

try:
    from rich.console import Console
    from rich.panel import Panel
except ImportError:
    subprocess.run([str(VENV_PY), "-m", "pip", "install", "rich", "--quiet"])
    from rich.console import Console
    from rich.panel import Panel

from PIL import Image, ImageDraw, ImageFont

console = Console(force_terminal=True)

# ── Domain-Kontext (Fehlertypen) ─────────────────────────────────────────────

DOMAIN_CONTEXT = {
    "4EYES_DISTINCT": """\
**GMP §5.2:** Zwei verschiedene Personen fuer Bearbeitet + Geprueft.
Typische OCR-Fehler: "ohe"/"ohr", "han"/"hau" -- aehnliche Buchstaben.
Signatur-Kuerzel sind 2-3 Buchstaben, handgeschrieben.""",

    "4EYES_ORDER": """\
**GMP:** Geprueft-Datum MUSS nach Bearbeitet-Datum liegen.
OCR-Fehler: Jahresziffern werden verwechselt (2026->2025, 2026->2076).""",

    "CALC_NET_MASS": """\
**Formel:** m Netto = m Brutto - m Tara.
OCR-Fehler: Ziffern 3/8, 6/0, 1/7 werden oft verwechselt.""",

    "CALC_VOLUME": """\
**Formel:** V = m / rho (Division -- ground-truth-verifiziert).
Wenn rho im Label steht (z.B. 'V = m / rho; rho = 1,100 kg/L'), wird es daraus extrahiert.""",

    "CALC_FORMULA": """\
**Formel-Ergebnis:** Handschriftliches Ergebnis gegen nachberechnete Formel.
OCR-Fehler: Kommafehler (1,18 vs 11,8), falsche Einheit.""",

    "RANGE_SOLL": """\
**Sollbereich:** Wert muss in gedrucktem Bereich liegen.
OCR-Fehler: Sollbereich unvollstaendig gelesen (z.B. '7' statt '7-19').""",

    "SIG_INCOMPLETE": """\
**GMP:** Signatur braucht Datum UND Kuerzel.
Wenn nur eines fehlt, ist die Signatur unvollstaendig (GxP-Verstoß).""",

    "MISSING_SIGNATURE": """\
**GMP:** Pflichtfeld ist leer -- weder Datum noch Kuerzel vorhanden.""",

    "FMT_DATE_PADDING": """\
**Format:** Datum muss TT.MM.JJJJ sein (01.06.2026, nicht 1.6.2026).""",

    "DATE_BEFORE_PRINT": """\
**Druckdatum:** 09.06.2026 -- kein Datum darf davor liegen.
OCR-Fehler: 2026->2025 (6/5 aehnlich), 2026->2016 (1/2 aehnlich).""",

    "DATE_FAR_FUTURE": """\
**Plausibilitaet:** Datum >180 Tage nach Druckdatum.
OCR-Fehler: 2026->2028 (6/8 aehnlich), 2026->2076 (2/7 aehnlich).""",

    "KUERZEL_UNKNOWN": """\
**Personalliste:** Kuerzel nicht in Beteiligte-Personen (Seite 4).
Edit-Distance-2-Toleranz -- nur klar unregistrierte Kuerzel werden markiert.""",

    "XREF_CARRIED_MATCH": """\
**Uebertrag:** Wert 'Uebertrag Kapitel X' muss mit Quellfeld uebereinstimmen.""",

    "XREF_NEAR_MISS": """\
**Uebertrag:** Minimale Abweichung -- wahrscheinlich Rundung.""",

    "EXTRACT_LOW_CONF": """\
**OCR-Konfidenz:** Texterkennung war unsicher. Original-Scan pruefen.""",

    "CALC_ROUNDING": """\
**Rundung:** Ergebnis weicht minimal vom Formelwert ab.""",
}

FLAG_CODE_TO_RULE = {
    "FMT_DATE_PADDING":  "rule_date_format",
    "FMT_NKS":           "rule_nks",
    "FMT_TIME_RANGE":    "rule_time_format",
    "RANGE_SOLL":        "rule_range",
    "CALC_FORMULA":      "rule_formula",
    "CALC_ROUNDING":     "rule_formula",
    "CALC_NET_MASS":     "rule_net_mass",
    "CALC_VOLUME":       "rule_volume",
    "4EYES_ORDER":       "rule_four_eyes",
    "4EYES_DISTINCT":    "rule_four_eyes",
    "DATE_BEFORE_PRINT": "rule_dates_document",
    "DATE_FAR_FUTURE":   "rule_dates_document",
    "KUERZEL_UNKNOWN":   "rule_kuerzel_document",
    "KUERZEL_UNRESOLVED":"(resolve.py)",
    "XREF_CARRIED_MATCH":"rule_xref_document",
    "XREF_NEAR_MISS":    "rule_xref_document",
    "MISSING_SIGNATURE": "rule_presence",
    "SIG_INCOMPLETE":    "rule_presence",
    "MISSING_CHECKMARK": "rule_presence",
    "EXTRACT_LOW_CONF":  "(uncertainty scorer)",
}

CODE_PRIORITY = {
    "CALC_NET_MASS":0,"CALC_VOLUME":1,"CALC_FORMULA":2,
    "RANGE_SOLL":3,"4EYES_ORDER":4,"4EYES_DISTINCT":5,
    "SIG_INCOMPLETE":6,"MISSING_SIGNATURE":7,
    "DATE_BEFORE_PRINT":8,"DATE_FAR_FUTURE":9,
    "KUERZEL_UNKNOWN":10,"XREF_CARRIED_MATCH":11,
}

# ── Bbox-Analyse ──────────────────────────────────────────────────────────────

def iou(b1, b2) -> float:
    ix0=max(b1[0],b2[0]); iy0=max(b1[1],b2[1])
    ix1=min(b1[2],b2[2]); iy1=min(b1[3],b2[3])
    inter=max(0.0,ix1-ix0)*max(0.0,iy1-iy0)
    a1=(b1[2]-b1[0])*(b1[3]-b1[1]); a2=(b2[2]-b2[0])*(b2[3]-b2[1])
    union=a1+a2-inter
    return round(inter/union,3) if union>0 else 0.0


def detect_bbox_collisions(fields: list) -> list[dict]:
    """Findet ueberlappende Bounding-Boxes auf derselben Seite."""
    by_page: dict[int, list] = defaultdict(list)
    for f in fields:
        if f.get("bbox") and len(f["bbox"]) == 4:
            area = (f["bbox"][2]-f["bbox"][0])*(f["bbox"][3]-f["bbox"][1])
            if area > 0.0001:  # Mindestgroesse
                by_page[f["page_no"]].append(f)

    collisions = []
    for page, pf in by_page.items():
        for i, f1 in enumerate(pf):
            for f2 in pf[i+1:]:
                overlap = iou(f1["bbox"], f2["bbox"])
                if overlap > 0.10:
                    collisions.append({
                        "page":    page,
                        "field1":  f1.get("label","?")[:35],
                        "field2":  f2.get("label","?")[:35],
                        "overlap": overlap,
                        "bbox1":   f1["bbox"],
                        "bbox2":   f2["bbox"],
                        "val1":    f1.get("value_raw",""),
                        "val2":    f2.get("value_raw",""),
                    })
    return sorted(collisions, key=lambda c: -c["overlap"])


def bbox_coverage_stats(fields: list) -> dict:
    """Statistiken ueber Bbox-Abdeckung und Qualitaet."""
    total         = len(fields)
    with_bbox     = sum(1 for f in fields if f.get("bbox"))
    empty_bbox    = total - with_bbox
    # Felder ohne Bbox nach Rolle gruppieren
    no_bbox_roles = defaultdict(int)
    for f in fields:
        if not f.get("bbox"):
            no_bbox_roles[f.get("role") or "(kein Role)"] += 1
    # Durchschnittliche Box-Groesse
    sizes = []
    for f in fields:
        b = f.get("bbox")
        if b and len(b)==4:
            sizes.append((b[2]-b[0])*(b[3]-b[1]))
    avg_size = round(sum(sizes)/len(sizes), 4) if sizes else 0
    return dict(
        total=total, with_bbox=with_bbox, without_bbox=empty_bbox,
        coverage_pct=round(with_bbox/total*100,1) if total else 0,
        avg_bbox_area=avg_size,
        no_bbox_by_role=dict(sorted(no_bbox_roles.items(), key=lambda x:-x[1])[:10]),
    )


# ── Ground-Truth-Abgleich ─────────────────────────────────────────────────────

def load_ground_truth() -> dict[int, dict]:
    """Laedt alle Ground-Truth-Seiten."""
    gt: dict[int, dict] = {}
    if not GT_DIR.exists():
        return gt
    for f in sorted(GT_DIR.glob("page_*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            gt[data["page"]] = data
        except Exception:
            pass
    return gt


def compare_to_ground_truth(page_no: int, extracted: list, gold: dict) -> dict:
    """Vergleicht extrahierte Felder mit Ground Truth fuer eine Seite."""
    gold_fields = gold.get("fields", [])
    gold_labels = {gf["label"].lower().strip() for gf in gold_fields}

    # Coverage: wie viele Gold-Felder wurden gefunden?
    found = []; missing = []
    for gf in gold_fields:
        gl = gf["label"].lower().strip()
        match = next((f for f in extracted
                      if gl in (f.get("label","") or "").lower()
                      or (f.get("label","") or "").lower() in gl), None)
        if match:
            found.append({"gold": gf["label"], "extracted": match.get("label",""),
                          "gold_val": gf.get("value",""),
                          "ext_val":  match.get("value_raw","")})
        else:
            missing.append(gf["label"])

    # Extra-Felder (extrahiert aber nicht in Gold)
    extra = []
    for ef in extracted:
        el = (ef.get("label","") or "").lower().strip()
        if not any(el in gl or gl in el for gl in gold_labels):
            extra.append(ef.get("label","?"))

    # Wertgenauigkeit fuer gefundene Felder
    value_correct = value_wrong = 0
    wrong_details = []
    for pair in found:
        gv = pair["gold_val"].strip().lower().replace(",",".")
        ev = pair["ext_val"].strip().lower().replace(",",".")
        if gv and ev:
            if gv == ev or gv in ev or ev in gv:
                value_correct += 1
            else:
                value_wrong += 1
                wrong_details.append({
                    "label": pair["gold"],
                    "gold":  pair["gold_val"],
                    "ocr":   pair["ext_val"],
                })

    # Erwartete Regelverstoesse vs tatsaechlich ausgeloeste
    expected_violations = gold.get("expected_violations", [])

    return dict(
        page=page_no, section=gold.get("section",""),
        gold_total=len(gold_fields), found=len(found), missing=missing,
        extra=extra[:10],
        value_correct=value_correct, value_wrong=value_wrong,
        wrong_details=wrong_details,
        expected_violations=[v["rule"] for v in expected_violations],
        coverage_pct=round(len(found)/len(gold_fields)*100,1) if gold_fields else 0,
    )


# ── Seiten-Visualisierung ─────────────────────────────────────────────────────

def render_page_overview(page_no: int, fields: list,
                         gold_fields: list | None = None,
                         collisions: list | None = None) -> Path | None:
    """Rendert ganze Seite mit farbigen Bbox-Overlays (alle Felder)."""
    img_path = PAGES_DIR / f"page_{page_no:03d}.png"
    if not img_path.exists():
        return None

    img = Image.open(img_path).convert("RGB")
    iw, ih = img.size
    draw = ImageDraw.Draw(img, "RGBA")

    # Kollidierende Boxen merken
    collision_fields = set()
    if collisions:
        for c in [col for col in collisions if col["page"]==page_no]:
            collision_fields.add(c["field1"][:35])
            collision_fields.add(c["field2"][:35])

    # Alle extrahierten Felder zeichnen
    for f in fields:
        b = f.get("bbox")
        if not b or len(b) != 4:
            continue
        x0,y0,x1,y1 = int(b[0]*iw),int(b[1]*ih),int(b[2]*iw),int(b[3]*ih)
        lbl = (f.get("label","") or "")[:35]
        flags = f.get("flags",[])

        if lbl in collision_fields:
            color = (255, 80, 0, 80); outline = (255, 80, 0)   # orange = Kollision
        elif any(fl.get("severity")=="error" for fl in flags):
            color = (220, 0, 0, 60); outline = (220, 0, 0)     # rot = Fehler
        elif any(fl.get("severity")=="warning" for fl in flags):
            color = (220, 160, 0, 50); outline = (200, 140, 0) # gelb = Warnung
        else:
            color = (0, 160, 0, 30); outline = (0, 130, 0)     # gruen = OK

        draw.rectangle([x0,y0,x1,y1], fill=color, outline=outline, width=2)

    # Gold-Felder die FEHLEN als gestrichelten Rahmen zeigen
    # (wir kennen ihre Position nicht ohne echte Extraktion -- als Text-Overlay)

    # Legende
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", max(12, iw//120))
    except Exception:
        font = ImageFont.load_default()
    legend = [
        ((0,130,0), "OK"),
        ((200,140,0), "Warnung"),
        ((220,0,0), "Fehler"),
        ((255,80,0), "Kollision"),
    ]
    lx,ly = 8,8
    for col, label in legend:
        draw.rectangle([lx,ly,lx+14,ly+14], fill=col+(200,), outline=col)
        draw.text((lx+18, ly), label, fill=(0,0,0), font=font)
        lx += 90

    # Ausgabe
    CROPS_DIR.mkdir(exist_ok=True)
    out = CROPS_DIR / f"p{page_no:02d}_overview.png"
    # Skalieren auf max 1400px Breite
    if iw > 1400:
        scale = 1400/iw
        img = img.resize((1400, int(ih*scale)), Image.BILINEAR)
    img.save(str(out))
    return out


def crop_bbox(page_no: int, bbox: list, pad=0.06) -> Path | None:
    """Einzelnes Feld-Crop mit Padding."""
    img_path = PAGES_DIR / f"page_{page_no:03d}.png"
    if not img_path.exists():
        return None
    img = Image.open(img_path)
    w,h = img.size
    x0=max(0,int((bbox[0]-pad)*w)); y0=max(0,int((bbox[1]-pad)*h))
    x1=min(w,int((bbox[2]+pad)*w)); y1=min(h,int((bbox[3]+pad)*h))
    if x1<=x0 or y1<=y0: return None
    crop = img.crop((x0,y0,x1,y1))
    CROPS_DIR.mkdir(exist_ok=True)
    out = CROPS_DIR / f"p{page_no:02d}_{bbox[0]:.2f}.png"
    crop.save(str(out))
    return out


# ── Regelcode-Extraktion ──────────────────────────────────────────────────────

def extract_rule_source(rule_name: str | None) -> str:
    if not rule_name or rule_name.startswith("("):
        return f"# {rule_name or 'intern'}"
    try:
        src = RULES_FILE.read_text(encoding="utf-8")
        tree = ast.parse(src)
        lines = src.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == rule_name:
                return "\n".join(lines[node.lineno-1:node.end_lineno])
    except Exception:
        pass
    return f"# {rule_name} nicht gefunden"


# ── Prompt-Bausteine ─────────────────────────────────────────────────────────

def build_rule_section(code: str, occurrences: list[dict],
                       rule_name: str | None, rule_src: str,
                       all_fields: list, collisions: list) -> str:
    n = len(occurrences)
    ctx = DOMAIN_CONTEXT.get(code, "")

    # Vorkommen
    occ_lines = []
    for i, occ in enumerate(occurrences, 1):
        bbox = occ.get("bbox")
        crop_path = crop_bbox(occ["page_no"], bbox) if bbox else None
        page_collision = [c for c in collisions if c["page"]==occ["page_no"]
                          and (occ.get("label","")[:35] in (c["field1"],c["field2"]))]
        col_note = ""
        if page_collision:
            col_note = f"\n  ⚠ BBOX-KOLLISION: ueberlappt mit '{page_collision[0]['field2'] if page_collision[0]['field1']==occ.get('label','')[:35] else page_collision[0]['field1']}' (IoU={page_collision[0]['overlap']})"
        occ_lines.append(
            f"### Vorkommen {i}/{n} — Seite {occ['page_no']}, Kapitel {occ.get('chapter','?')}\n"
            f"- Feld: **{occ.get('label','?')}** (Rolle: `{occ.get('role','?')}`)\n"
            f"- OCR-Wert: `{occ.get('value_raw','?')}`\n"
            f"- Erwartet: `{occ.get('expected','?')}` | Gefunden: `{occ.get('actual','?')}`\n"
            f"- Meldung: {occ.get('message','?')}{col_note}\n"
            + (f"- **Feld-Crop:** `{crop_path}` <- Read-Tool\n" if crop_path else "")
            + (f"- **Seiten-Overview:** `{CROPS_DIR}/p{occ['page_no']:02d}_overview.png` <- Read-Tool\n")
        )

    return f"""## Fehlertyp: `{code}` ({n}× {occurrences[0].get('severity','?').upper()})

### Domain-Kontext
{ctx}

### Regelcode (`{rule_name or 'N/A'}`)
```python
{rule_src[:800]}
```

### {n} Vorkommen

{"".join(occ_lines)}
### Aufgabe
1. Lies die Feld-Crops und Seiten-Overviews (Read-Tool)
2. Entscheide fuer jedes Vorkommen: **LEGITIMER FEHLER** / **OCR-FEHLER** / **REGELBUG**
3. Bei REGELBUG: patche `backend/app/pipeline/validate/rules.py` direkt
4. Bei OCR-FEHLER mit Bbox-Kollision: pruefe ob Box-Position korrigiert werden muss
"""


def build_bbox_section(collisions: list, coverage: dict, all_fields: list) -> str:
    if not collisions:
        col_txt = "Keine Bbox-Kollisionen gefunden. Alle Felder haben separate Positionen."
    else:
        rows = []
        for c in collisions[:20]:
            rows.append(
                f"| p{c['page']:02d} | {c['field1'][:30]} | {c['field2'][:30]} "
                f"| {c['overlap']:.1%} | `{c['bbox1']}` |"
            )
        col_txt = (
            "| Seite | Feld 1 | Feld 2 | Ueberlappung | Bbox 1 |\n"
            "|-------|--------|--------|-------------|--------|\n"
            + "\n".join(rows)
        )
        col_txt += f"\n\nGesamt: **{len(collisions)} Kollisionen** auf "
        col_txt += f"{len({c['page'] for c in collisions})} Seiten."

    cov = coverage
    return f"""## Bbox-Analyse

### Abdeckung
- Felder gesamt: **{cov['total']}**
- Mit Bbox: **{cov['with_bbox']}** ({cov['coverage_pct']}%)
- Ohne Bbox: **{cov['without_bbox']}** (werden NICHT im Page-Viewer angezeigt)
- Durchschn. Box-Groesse: {cov['avg_bbox_area']:.4f} (normiert)

**Felder ohne Bbox nach Rolle:**
{json.dumps(cov['no_bbox_by_role'], ensure_ascii=False, indent=2)}

### Kollisionsdetails (IoU > 10%)
{col_txt}

### Aufgabe
1. Oeffne die Seiten-Overviews (`crops/pXX_overview.png`) mit dem Read-Tool
2. Orangen Rahmen = kollidierende Boxen, rote = Fehler, gruen = OK
3. Bei Kollisionen: pruefe ob zwei Felder dieselbe Box zugeteilt wurden
4. Kollidierende Boxen koennen durch `set_bbox` API korrigiert werden:
   `PATCH /api/v1/fields/{{id}} {{action: "set_bbox", bbox: [x0,y0,x1,y1]}}`
"""


def build_gt_section(gt_results: list[dict]) -> str:
    if not gt_results:
        return "## Ground-Truth-Vergleich\n\nKein Ground-Truth verfuegbar."

    rows = []
    for r in gt_results:
        rows.append(
            f"| p{r['page']:02d} | {r['section'][:35]} | "
            f"{r['coverage_pct']:.0f}% ({r['found']}/{r['gold_total']}) | "
            f"{r['value_correct']}/{r['value_correct']+r['value_wrong']} | "
            f"{', '.join(r['expected_violations']) or '(keine)'} |"
        )

    missing_all = []
    for r in gt_results:
        for m in r.get("missing", []):
            missing_all.append(f"p{r['page']:02d}: {m}")

    wrong_vals = []
    for r in gt_results:
        for w in r.get("wrong_details", []):
            wrong_vals.append(
                f"p{r['page']:02d} | {w['label'][:30]} | "
                f"Gold: `{w['gold']}` | OCR: `{w['ocr']}`"
            )

    return f"""## Ground-Truth-Vergleich (8 Gold-Seiten)

### Uebersicht
| Seite | Abschnitt | Coverage | Wertgenauigkeit | Erwartete Verstoesse |
|-------|-----------|----------|-----------------|----------------------|
{"".join(rows)}

### Fehlende Felder (in Gold aber nicht extrahiert)
{chr(10).join(missing_all[:20]) or "(keine)"}

### Falsche Werte (extrahiert aber falsch)
| Seite | Feld | Gold-Wert | OCR-Wert |
|-------|------|-----------|----------|
{"".join(f'| {r} |' for r in wrong_vals[:15]) or "| (keine) |"}

### Layout-Konsistenz fuer neue Batches
Fuer zuverlassige Erkennung neuer Batches desselben Formulars:
- Alle {sum(r['gold_total'] for r in gt_results)} Gold-Felder muessen an aehnlichen
  normierten Positionen (±0.05) erscheinen
- Checkbox-Felder muessen als 'checkbox' Rolle erkannt werden
- Signatur-Felder brauchen vollstaendige Bbox fuer den Pruefer

### Aufgabe
1. Coverage < 80%: Fehlende Felder -- Extraktions-Prompt verbessern
2. Falsche Werte: OCR-Normalisierung oder Prompt-Anpassung
3. Verstoesse nicht erkannt: Regellogik pruefen (rules.py)
4. Verstoesse falsch positiv: Soll-Werte oder Formel-Extraktion pruefen
"""


def build_layout_section(all_fields: list, gt_data: dict) -> str:
    """Vergleicht erwartete Layout-Positionen mit tatsaechlichen Positionen."""
    if not gt_data:
        return "## Layout-Konsistenz\n\nKein Ground-Truth fuer Positions-Check verfuegbar."

    # Fuer jede GT-Seite: Vergleich der Field-Positionen
    position_issues = []
    for page_no, gold in gt_data.items():
        page_fields = [f for f in all_fields if f["page_no"]==page_no]
        for gf in gold.get("fields",[]):
            gl = gf["label"].lower().strip()
            match = next((f for f in page_fields
                          if gl in (f.get("label","") or "").lower()
                          or (f.get("label","") or "").lower() in gl), None)
            if match and match.get("bbox"):
                # Bbox-Groesse pruefen (sehr kleine Boxen = schlechte Lokalisierung)
                b = match["bbox"]
                area = (b[2]-b[0])*(b[3]-b[1])
                if area < 0.001:
                    position_issues.append({
                        "page": page_no, "field": gf["label"],
                        "issue": f"Sehr kleine Bbox (area={area:.4f}) -- moeglicherweise falsch lokalisiert",
                        "bbox": b,
                    })
                # Unplausible Positionen (z.B. Signatur-Felder oben auf der Seite)
                if gf["kind"]=="signature" and b[1] < 0.3:
                    position_issues.append({
                        "page": page_no, "field": gf["label"],
                        "issue": f"Signatur-Feld sehr weit oben (y={b[1]:.2f}) -- uebliche Position y>0.5",
                        "bbox": b,
                    })

    if not position_issues:
        pos_txt = "Keine Layout-Anomalien gefunden. Alle gefundenen Felder haben plausible Positionen."
    else:
        pos_txt = "\n".join(
            f"- **p{i['page']:02d} {i['field'][:35]}**: {i['issue']}"
            for i in position_issues[:15]
        )

    return f"""## Layout-Konsistenz-Check

### Positions-Anomalien
{pos_txt}

### Empfehlungen fuer neue Batches
Damit neue Batches desselben Formulars gleich zuverlaessig erkannt werden:

1. **Checkbox-Felder**: OCR-Engine muss "checked"/"unchecked" korrekt unterscheiden.
   Kleine Haekchen-Symbole brauchen hochaufloesende Bilder (>=200 DPI empfohlen).

2. **Signatur-Felder**: Kuerzel-Erkennung mit Beteiligte-Personen-Abgleich (resolve.py).
   Neue Batch = moeglicherweise neue Signaturen -- Roster aktuell halten.

3. **Berechnungs-Felder**: Formel-Extraktion aus Label-Text (z.B. 'rho = 1,100 kg/L').
   Bei neuen Batches koennen sich Dichte-Werte aendern -- Label-Parsing ist robuster als
   feste Werte.

4. **Bbox-Kollisionen**: Wenn gleiche Form-Vorlage aber anderer Inhalt ->
   Kollisionen deuten auf falsch gruppierte Felder hin (OCR-Block-Segmentierung).

5. **Datumsfelder**: _correct_year() korrigiert 1-2 Ziffer-Fehler (z.B. 2026->2016).
   Bei historischen Batches (anderes Jahr) -> ref_year anpassen.
"""


# ── Hauptprogramm ─────────────────────────────────────────────────────────────

def main() -> None:
    args             = sys.argv[1:]
    include_warnings = "--warnings" in args or "-w" in args
    bbox_only        = "--bbox-only" in args
    gt_only          = "--gt-only" in args
    code_filter      = next((args[i+1].upper() for i,a in enumerate(args)
                             if a=="--code" and i+1<len(args)), None)
    page_filter      = next((int(args[i+1]) for i,a in enumerate(args)
                             if a=="--page" and i+1<len(args)), None)

    if not RESULTS_JSON.exists():
        console.print("[red]results/extracted_fields.json nicht gefunden.[/red]")
        sys.exit(1)

    # Daten laden
    data       = json.loads(RESULTS_JSON.read_text(encoding="utf-8"))
    all_fields = data["fields"]
    gt_data    = load_ground_truth()

    console.print()
    console.print(Panel(
        f"  [bold]{len(all_fields)} Felder geladen[/bold]   "
        f"[dim]{len(gt_data)} Gold-Seiten verfuegbar[/dim]",
        title="[bold]BioDize Autopatch v3[/bold]",
        border_style="bright_blue",
    ))

    # ── Analyse ──────────────────────────────────────────────────────────
    console.print("  Analysiere Bbox-Kollisionen...")
    collisions = detect_bbox_collisions(all_fields)
    coverage   = bbox_coverage_stats(all_fields)
    console.print(f"  {len(collisions)} Kollisionen gefunden, {coverage['coverage_pct']}% Bbox-Abdeckung")

    # Seiten-Overviews rendern
    console.print("  Rendere Seiten-Overviews...")
    rendered_pages = set()
    for f in all_fields:
        pg = f["page_no"]
        if pg not in rendered_pages:
            page_f = [x for x in all_fields if x["page_no"]==pg]
            render_page_overview(pg, page_f,
                                 gold_fields=gt_data.get(pg,{}).get("fields"),
                                 collisions=collisions)
            rendered_pages.add(pg)
    console.print(f"  {len(rendered_pages)} Seiten-Overviews in crops/ gespeichert")

    # Ground-Truth-Vergleich
    gt_results = []
    for page_no, gold in gt_data.items():
        page_fields = [f for f in all_fields if f["page_no"]==page_no]
        gt_results.append(compare_to_ground_truth(page_no, page_fields, gold))

    # ── Flags sammeln ─────────────────────────────────────────────────────
    all_flags = []
    for f in all_fields:
        for fl in f.get("flags",[]):
            all_flags.append({**fl,
                "page_no":  f["page_no"],
                "chapter":  f.get("chapter",""),
                "label":    f.get("label",""),
                "role":     f.get("role",""),
                "value_raw":f.get("value_raw") or f.get("value",""),
                "bbox":     f.get("bbox"),
            })

    filtered = [f for f in all_flags
                if (include_warnings or f["severity"]=="error")
                and (not code_filter or f["code"].startswith(code_filter))
                and (page_filter is None or f["page_no"]==page_filter)]

    # Gruppieren nach Code
    by_code: dict[str, list] = defaultdict(list)
    for f in filtered:
        by_code[f["code"]].append(f)

    sorted_codes = sorted(by_code.keys(),
                          key=lambda c: (CODE_PRIORITY.get(c,99),c))

    # ── Prompts bauen ─────────────────────────────────────────────────────
    parts = []

    if not gt_only:
        # 1. Regel-Fehler-Prompts
        for code in sorted_codes:
            occs      = by_code[code]
            rule_name = FLAG_CODE_TO_RULE.get(code)
            rule_src  = extract_rule_source(rule_name)
            parts.append(build_rule_section(code, occs, rule_name, rule_src,
                                            all_fields, collisions))
            console.print(f"  {code:<25} {len(occs)} Vorkommen -> Prompt erstellt")

    if not bbox_only:
        # 2. Ground-Truth
        parts.append(build_gt_section(gt_results))
        # 3. Layout
        parts.append(build_layout_section(all_fields, gt_data))

    # 4. Bbox-Analyse (immer)
    parts.append(build_bbox_section(collisions, coverage, all_fields))

    # ── Speichern ─────────────────────────────────────────────────────────
    sep   = "\n\n" + "─"*80 + "\n\n"
    total = f"""# BioDize Autopatch — Vollstaendige Analyse
*Generiert: {len(parts)} Abschnitte | {len(filtered)} Flags | {len(collisions)} Bbox-Kollisionen | {len(gt_data)} Gold-Seiten*

{sep.join(parts)}
"""
    OUT_FILE.write_text(total, encoding="utf-8")
    console.print(f"\n  [green]{len(parts)} Abschnitte gespeichert: {OUT_FILE.name}[/green]")
    console.print(f"  Crops + Overviews: {CROPS_DIR}/")

    import subprocess as _sp
    _sp.Popen(["notepad.exe", str(OUT_FILE)])
    input("\n  Enter druecken zum Schliessen...")


if __name__ == "__main__":
    main()
