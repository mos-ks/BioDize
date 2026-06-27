"""Normalize: parse EU-format values, assign roles, parse Soll ranges.

Pure functions (unit-tested in tests/test_normalize.py). German conventions:
  * decimal comma: "4,50" -> 4.5 (2 decimals); "1,100" -> 1.1
  * thousands dot:  "1.100" -> 1100
  * dates DD.MM.YYYY; times HH:MM (24h)
"""
from __future__ import annotations

import re
from datetime import date, datetime, time

from app.domain.roles import Role
from app.pipeline.model import Document, Field

_DATE = re.compile(r"^\s*(\d{1,2})\.(\d{1,2})\.(\d{4})\s*$")
_TIME = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*$")
_DATETIME = re.compile(r"^\s*(\d{1,2}\.\d{1,2}\.\d{4})\s*[/|\-–—]?\s*(\d{1,2}:\d{2})\s*$")
_NUMBER = re.compile(r"^-?\d{1,3}(\.\d{3})*(,\d+)?$|^-?\d+(,\d+)?$")
_NUM_TOKEN = re.compile(r"-?\d+(?:[.,]\d+)?")


# --- numbers ----------------------------------------------------------------

def parse_german_number(raw: str) -> tuple[float | None, int | None]:
    """Return (value, decimal_places) or (None, None)."""
    s = (raw or "").strip()
    if not s or not _NUMBER.match(s):
        return None, None
    decimals = len(s.split(",")[1]) if "," in s else 0
    if "," in s:
        cleaned = s.replace(".", "").replace(",", ".")   # dot=thousands, comma=decimal
    else:
        cleaned = s.replace(".", "")                      # bare dots are thousands separators
    try:
        return float(cleaned), decimals
    except ValueError:
        return None, None


def _num(token: str) -> float | None:
    val, _ = parse_german_number(token)
    return val


# --- dates / times ----------------------------------------------------------

def is_zero_padded_date(raw: str) -> bool:
    """True only if day and month are two digits (DD.MM.YYYY)."""
    return bool(re.match(r"^\s*\d{2}\.\d{2}\.\d{4}\s*$", raw or ""))


def _correct_year(y: int, ref_year: int = 2026) -> int:
    """Korrigiert OCR-Jahresfehler wenn genau eine Ziffer falsch gelesen wurde.

    Pharma-Batch-Records werden in einem einzigen Jahr ausgefuehrt.
    Alle Daten muessen ref_year sein. Ein-Ziffer-Fehler werden korrigiert:
      2016 -> 2026 (1 statt 2)
      2025 -> 2026 (5 statt 6)
      2027 -> 2026 (7 statt 6)
      2028 -> 2026 (8 statt 6)
      2076 -> 2026 (7 statt 2)
    Zwei-Ziffer-Fehler (z.B. 2018) bleiben erhalten -- zu riskant.
    """
    if y == ref_year:
        return y
    y_str, ref_str = str(y), str(ref_year)
    if len(y_str) == len(ref_str):
        diffs = sum(1 for a, b in zip(y_str, ref_str) if a != b)
        if diffs == 1:
            return ref_year
        # 2 Ziffern falsch UND Jahr liegt weit ausserhalb (>2 Jahre) -> OCR-Fehler
        # Beispiel: 2018 (8 Jahre vor Referenz) korrigiert zu 2026
        if diffs == 2 and abs(y - ref_year) > 2:
            return ref_year
    return y


def parse_date(raw: str) -> date | None:
    m = _DATE.match(raw or "")
    if not m:
        return None
    d, mo, y = (int(x) for x in m.groups())
    y = _correct_year(y)
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def parse_time(raw: str) -> time | None:
    m = _TIME.match(raw or "")
    if not m:
        return None
    h, mi = (int(x) for x in m.groups())
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        return None
    return time(h, mi)


def parse_datetime(raw: str) -> datetime | None:
    m = _DATETIME.match(raw or "")
    if not m:
        return None
    d = parse_date(m.group(1))
    t = parse_time(m.group(2))
    if d and t:
        return datetime.combine(d, t)
    return None


# --- value typing -----------------------------------------------------------

def detect_value_type(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return "empty"
    if _DATETIME.match(s):
        return "datetime"
    if _DATE.match(s):
        return "date"
    if _TIME.match(s):
        return "time"
    if s.lower() in {"ja", "nein", "x", "✓", "true", "false"}:
        return "bool"
    if _NUMBER.match(s):
        return "number"
    return "text"


# --- Soll ranges ------------------------------------------------------------

def parse_soll(soll: str | None) -> dict | None:
    """Parse a Soll spec into {min, max, target}.

    Handles: "2 - 8", "20 - 30", "<= 3", ">= 5", "75 (8 - 165)",
    "11,95 (8,56 - 23,30)", "<= 65", single "1".
    """
    if not soll:
        return None
    s = soll.replace("≤", "<=").replace("≥", ">=")
    s = s.replace("–", "-").replace("—", "-").strip()      # en/em dash -> hyphen
    nums = [_num(t) for t in _NUM_TOKEN.findall(s) if _num(t) is not None]
    if not nums:
        return None
    # Range inside parentheses takes precedence as (min, max); target is the
    # number BEFORE the paren (positional), which may equal a range endpoint.
    paren = re.search(r"\(([^)]*)\)", s)
    if paren:
        pnums = [_num(t) for t in _NUM_TOKEN.findall(paren.group(1)) if _num(t) is not None]
        out_nums = [_num(t) for t in _NUM_TOKEN.findall(s[:paren.start()]) if _num(t) is not None]
        target = out_nums[0] if out_nums else None
        if len(pnums) >= 2:
            return {"min": min(pnums), "max": max(pnums), "target": target}
    if "<=" in s:
        return {"min": None, "max": nums[0], "target": None}
    if ">=" in s:
        return {"min": nums[0], "max": None, "target": None}
    if "-" in s and len(nums) >= 2:
        return {"min": min(nums[:2]), "max": max(nums[:2]), "target": None}
    return {"min": None, "max": None, "target": nums[0]}


# --- role assignment (fallback for extractors that don't set roles) ---------

_ROLE_KEYWORDS: list[tuple[str, str]] = [
    ("tara", Role.TARE_MASS),
    ("brutto", Role.GROSS_MASS),
    ("netto", Role.NET_MASS),
    ("rho", Role.DENSITY), ("dichte", Role.DENSITY),
    ("start", Role.HOLD_START),
    ("erlaubte", Role.HOLD_END), ("ende", Role.HOLD_END),
    ("dauer", Role.HOLD_DURATION),
    ("temperatur", Role.TEMPERATURE_SETPOINT),
    ("bearbeitet", Role.SIGNATURE_PROCESSED),
    ("geprueft", Role.SIGNATURE_CHECKED), ("geprüft", Role.SIGNATURE_CHECKED),
    ("review", Role.SIGNATURE_CHECKED), ("unterschrift", Role.SIGNATURE_CHECKED),
    ("volumen", Role.VOLUME),
]


def assign_role(label: str, unit: str | None) -> str | None:
    low = (label or "").lower()
    stripped = low.strip()
    # Check the V/C prefix BEFORE the substring keywords, else "V Netto" matches
    # "netto" -> NET_MASS instead of VOLUME.
    if stripped.startswith("v ") or unit == "L":
        return Role.VOLUME
    if stripped.startswith("c ") or "konzentration" in low or "ipc" in low:
        return Role.CONCENTRATION
    for kw, role in _ROLE_KEYWORDS:
        if kw in low:
            return role
    return None


# --- Kürzel-Normalisierung --------------------------------------------------

def _levenshtein(a: str, b: str) -> int:
    """Levenshtein-Distanz zwischen zwei Strings."""
    if a == b: return 0
    la, lb = len(a), len(b)
    prev = list(range(lb + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j-1] + 1, prev[j-1] + (ca != cb)))
        prev = cur
    return prev[lb]


def _extract_kuerzel(raw: str) -> tuple[str, str] | None:
    """'10.06.2026 / ohe' → ('10.06.2026 / ', 'ohe')"""
    parts = (raw or "").split("/", 1)
    if len(parts) != 2:
        return None
    prefix = parts[0] + "/"
    k = parts[1].strip()
    return (prefix, k) if k else None


def normalize_kuerzel(doc: Document) -> None:
    """Korrigiert OCR-Lesefehler in Kürzeln durch Abgleich mit Personalliste.

    GPT-5.5 liest handschriftliche 3-Buchstaben-Kürzel häufig falsch
    (ohe → ohp/ohr/o4e/olp/dh). Diese Funktion mappt solche Varianten
    auf das nächste registrierte Kürzel wenn Edit-Distanz ≤ 2.
    """
    from app.domain.roles import Role as R

    # Personalliste aufbauen -- "Kürzel" / "Kuerzel" / "kurzel" alle abfangen
    registry: set[str] = set()
    for f in doc.all_fields():
        lbl = (f.label_raw or "").strip().lower()
        lbl_norm = lbl.replace("ü", "u").replace("ue", "u")
        if lbl_norm in ("kurzel", "kuerzel") and f.value_raw:
            registry.add(f.value_raw.strip().lower())

    if len(registry) < 2:
        return  # zu wenig registrierte Kürzel für sichere Normalisierung

    sig_roles = {R.SIGNATURE_PROCESSED, R.SIGNATURE_CHECKED}
    corrected = 0

    for fld in doc.all_fields():
        if fld.role not in sig_roles:
            continue
        parsed = _extract_kuerzel(fld.value_raw or "")
        if not parsed:
            continue
        prefix, k = parsed
        k_low = k.lower()

        if k_low in registry:
            continue  # bereits korrekt

        # Nächstes Kürzel in der Personalliste suchen
        best_dist = 99
        best_k    = None
        for reg_k in registry:
            d = _levenshtein(k_low, reg_k)
            if d < best_dist:
                best_dist, best_k = d, reg_k

        # Nur korrigieren wenn eindeutig nah dran (≤ 2 Editierungen)
        if best_k and best_dist <= 2:
            canonical = best_k
            fld.value_raw = prefix + " " + canonical
            if fld.reads:
                fld.reads[0].value_raw = fld.value_raw
            corrected += 1

    if corrected:
        import logging
        logging.getLogger(__name__).debug(
            f"normalize_kuerzel: {corrected} Kürzel-OCR-Fehler korrigiert"
        )


# --- entry point ------------------------------------------------------------

def normalize(doc: Document) -> Document:
    for fld in doc.all_fields():
        if fld.role is None:
            fld.role = assign_role(fld.label_raw, fld.unit)

        vtype = detect_value_type(fld.value_raw)
        if fld.value_type != "checkbox":     # preserve the extractor's checkbox marker
            fld.value_type = vtype

        if vtype == "number":
            val, decimals = parse_german_number(fld.value_raw)
            fld.value = val
            fld.decimals = decimals
        elif vtype == "date":
            fld.value = parse_date(fld.value_raw)
        elif vtype == "time":
            fld.value = parse_time(fld.value_raw)
        elif vtype == "datetime":
            fld.value = parse_datetime(fld.value_raw)
        elif vtype == "bool":
            fld.value = fld.value_raw.strip().lower() in {"ja", "x", "✓", "true"}
        else:
            fld.value = fld.value_raw

    # Kürzel-OCR-Fehler korrigieren (ohp/ohr/o4e → ohe etc.)
    normalize_kuerzel(doc)
    return doc
