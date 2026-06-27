"""StubExtractor — deterministic, offline fixtures modeled on the real sample.

Lets the frontend integrate and the whole pipeline run with NO API calls. The
canonical fixture intentionally includes several of the document's planted errors
so that validation produces a realistic spread of flags out of the box:

  * p11 Bilanzierung (ABCE) — clean: net = gross - tare, V = net x rho.
  * p10 §5.2 signature  — Geprueft (09.06) BEFORE Bearbeitet (10.06)  -> 4-eyes error
                          + same Kuerzel both roles                    -> 4-eyes error.
  * p17 Wippgeschw.      — 32 vs Soll 20-30 (no deviation in stub)     -> range error.
  * p40 Bilanzierung nPZ — net 200 but gross-tare = 0                   -> calc error.
  * a date "10.6.2026"   — not zero-padded                             -> format error.

On top of the canonical sample there are three SIMULATED demo batches (batch
"Simulated") with their own planted-error mixes. They share the canonical's field
labels/units so the same validators bind — only the products, people and numbers
change. The API rotates through [canonical, strawberry, ganache, lemon] so each
"Process sample" click yields the next batch; direct/test calls always get the
canonical one (so the ground-truth tests stay deterministic).
"""
from __future__ import annotations

from datetime import date

from app.domain.roles import Role
from app.pipeline.model import BBox, Block, Document, Field, Read

# Sentinel the API passes to request the NEXT rotating demo batch (so a plain
# extract()/extract(None) — as the tests call — always returns the canonical one).
ROTATE_SAMPLE = "sample:rotate"


def _f(role, label, value, *, unit=None, nks=None, soll=None, calc_expr=None, bbox=None,
       model="stub", conf=0.9, required=True):
    field = Field(
        page_no=0, chapter="", role=role, label_raw=label, value_raw=value,
        unit=unit, nks=nks, soll=soll, calc_expr=calc_expr,
        bbox=BBox(*bbox) if bbox else None, is_required=required,
    )
    field.reads = [Read(model=model, value_raw=value, confidence=conf, bbox=field.bbox)]
    return field


def _assemble(doc: Document, blocks: list[Block]) -> Document:
    """Stamp each field with its block's page/chapter and attach the blocks."""
    for block in blocks:
        for fld in block.fields:
            fld.page_no = block.page_no
            fld.chapter = block.chapter
            fld.block_key = block.key
        doc.blocks.append(block)
    return doc


def _roster(page: int, people: list[tuple[str, str]]) -> Block:
    """Beteiligte-Personen block: the Kürzel registry resolve() snaps signatures to."""
    b = Block(chapter="1", page_no=page, template="personnel")
    for name, kuerzel in people:
        b.fields.append(_f(None, "Name Mitarbeiter", name, required=False))
        b.fields.append(_f(None, "Kürzel", kuerzel, required=False))
    return b


def _balance(page: int, chapter: str, tare: int, gross: int, net: int, *, net_conf: float = 0.9) -> Block:
    """A minimal mass-balance block (net = gross - tare when clean)."""
    b = Block(chapter=chapter, page_no=page, template="bilanzierung")
    b.fields = [
        _f(Role.TARE_MASS, "m Tara", str(tare), unit="kg", bbox=(0.61, 0.27, 0.78, 0.30)),
        _f(Role.GROSS_MASS, "m Brutto", str(gross), unit="kg", bbox=(0.61, 0.31, 0.78, 0.34)),
        _f(Role.NET_MASS, "m Netto", str(net), unit="kg", bbox=(0.61, 0.34, 0.78, 0.37), conf=net_conf),
    ]
    return b


# --- canonical sample (the real document) -----------------------------------

def _build_canonical(source_path: str | None = None) -> Document:
    doc = Document(
        doc_no="AB-ABC-123456",
        title="Herstellung von Vanilla Celebration Cake - B35 Baking",
        rev="7",
        project_code="ABC",
        generated_at=date(2026, 6, 9),
        page_count=46,
        declared_page_count=45,
        source_path=source_path,
    )

    # --- p11: Bilanzierung ABCE (clean mass balance) ---------------------
    # V = m * rho (physics: density kg/L). 200 * 1,10 = 220 is clean.
    b11 = Block(chapter="5.3.1", page_no=11, template="bilanzierung")
    b11.fields = [
        # low-confidence read -> EXTRACT_LOW_CONF warning ("ask when unsure")
        _f(Role.SAMPLE_ID, "Intermediat", "ABCE 12345", conf=0.78, bbox=(0.80, 0.23, 0.95, 0.26)),
        _f(Role.TARE_MASS, "m Tara", "100", unit="kg", bbox=(0.61, 0.27, 0.78, 0.30)),
        _f(Role.GROSS_MASS, "m Brutto", "300", unit="kg", bbox=(0.61, 0.31, 0.78, 0.34)),
        _f(Role.NET_MASS, "m Netto", "200", unit="kg", bbox=(0.61, 0.34, 0.78, 0.37)),
        _f(Role.DENSITY, "rho", "1,10", unit="kg/L", bbox=(0.45, 0.38, 0.55, 0.41)),
        _f(Role.VOLUME, "V Netto", "220", unit="L", calc_expr="200 * 1,10", bbox=(0.61, 0.38, 0.78, 0.41)),
        # form states (2 NKS) but only 1 decimal written -> FMT_NKS warning
        _f(Role.CONCENTRATION, "c ABC-DE (Blocking IPC)", "4,5", unit="g/L", nks=2, bbox=(0.61, 0.42, 0.78, 0.45)),
        _f(Role.HOLD_START, "Start Haltezeit", "10.06.2026 08:46", bbox=(0.45, 0.50, 0.70, 0.53)),
        _f(Role.HOLD_END, "Erlaubte Haltezeit", "10.06.2026 14:46", bbox=(0.45, 0.58, 0.70, 0.61)),
        _f(Role.TEMPERATURE_SETPOINT, "Haltetemperatur", "Ja", soll="2 - 8", unit="degC", bbox=(0.80, 0.54, 0.90, 0.57)),
        _f(Role.SIGNATURE_PROCESSED, "Bearbeitet", "10.06.2026 / ohe", bbox=(0.40, 0.70, 0.70, 0.73)),
        _f(Role.SIGNATURE_CHECKED, "Geprueft", "10.06.2026 / han", bbox=(0.40, 0.74, 0.70, 0.77)),
    ]

    # --- p10 §5.2: signature block with planted 4-eyes errors -----------
    b10 = Block(chapter="5.2", page_no=10, template="signature")
    b10.fields = [
        _f(Role.SIGNATURE_PROCESSED, "Bearbeitet", "10.06.2026 / ohe", bbox=(0.40, 0.78, 0.70, 0.81), conf=0.88),
        _f(Role.SIGNATURE_CHECKED, "Geprueft", "09.06.2026 / ohe", bbox=(0.40, 0.82, 0.70, 0.85), conf=0.62),
    ]

    # --- p17: range field, out of spec, no deviation --------------------
    b17 = Block(chapter="5.6.2", page_no=17, template="range")
    b17.fields = [
        _f(Role.CALC_RESULT, "Wippgeschwindigkeit", "32", unit="Huebe/min",
           soll="20 - 30", bbox=(0.61, 0.30, 0.78, 0.33), conf=0.84),
    ]

    # --- p40: Bilanzierung nPZ with planted calc error + bad date -------
    b40 = Block(chapter="5.13.1", page_no=40, template="bilanzierung")
    b40.fields = [
        _f(Role.TARE_MASS, "m Tara", "100", unit="kg", bbox=(0.61, 0.30, 0.78, 0.33)),
        _f(Role.GROSS_MASS, "m Brutto nPZ", "100", unit="kg", bbox=(0.61, 0.46, 0.78, 0.49)),
        _f(Role.NET_MASS, "m Netto nPZ", "200", unit="kg", bbox=(0.61, 0.50, 0.78, 0.53), conf=0.7),
        _f(Role.SIGNATURE_PROCESSED, "Bearbeitet", "10.6.2026 / ohe", bbox=(0.40, 0.70, 0.70, 0.73), conf=0.66),
        _f(Role.SIGNATURE_CHECKED, "Geprueft", "10.06.2026 / han", bbox=(0.40, 0.74, 0.70, 0.77)),
    ]

    # --- p36-like: multi-input formula error + a same-year before-print date
    # (cross-year misreads like 2016 are now auto-corrected by normalize._correct_year,
    # so the planted before-print date is in-year to still exercise DATE_BEFORE_PRINT).
    b36 = Block(chapter="5.12.3", page_no=36, template="calc")
    b36.fields = [
        _f(Role.CALC_RESULT, "Load Volumen", "2021,78", unit="L",
           calc_expr="6,6 * 45 - 4,3 * 0,75", bbox=(0.61, 0.55, 0.80, 0.58), conf=0.95),
        _f(Role.SIGNATURE_PROCESSED, "Bearbeitet", "05.06.2026 / abc", bbox=(0.40, 0.70, 0.70, 0.73), conf=0.95),
        _f(Role.SIGNATURE_CHECKED, "Geprueft", "10.06.2026 / han", bbox=(0.40, 0.74, 0.70, 0.77), conf=0.95),
    ]

    # --- p4: Beteiligte Personen — the Kuerzel registry -----------------
    b4 = Block(chapter="1", page_no=4, template="personnel")
    b4.fields = [
        _f(None, "Name Mitarbeiter", "Hans Mustermann", required=False),
        _f(None, "Kürzel", "han", required=False),
        _f(None, "Name Mitarbeiter", "Olga Herzig", required=False),
        _f(None, "Kürzel", "ohe", required=False),
    ]

    # --- p38-like: cross-reference (Übertrag) mismatch vs source in 5.3.1
    b38 = Block(chapter="5.12.5", page_no=38, template="xref")
    b38.fields = [
        _f(Role.HOLD_START, "Start Haltezeit (Übertrag Kapitel 5.3.1)",
           "09.06.2016 08:27", bbox=(0.45, 0.30, 0.70, 0.33), conf=0.9),
    ]

    return _assemble(doc, [b11, b10, b17, b40, b36, b4, b38])


# --- simulated demo batches (batch "Simulated") -----------------------------

def _build_strawberry(source_path: str | None = None) -> Document:
    """Sim 1: a net-mass calc error, an out-of-range value, a low-confidence read
    and an NKS-format warning."""
    doc = Document(
        doc_no="SIM0001 · Batch Simulated",
        title="Herstellung von Strawberry Mousse Filling (Simulated)",
        rev="1", project_code="SIM", generated_at=date(2026, 6, 10),
        page_count=46, declared_page_count=46,
    )
    people = _roster(4, [("Anna Berg", "abg"), ("Paul Krause", "pkr")])

    # p12: mass balance — net 200 but gross-tare = 0 -> calc error; low-conf id;
    # concentration written to 1 decimal where the form states 2 -> NKS warning.
    b12 = Block(chapter="5.3.1", page_no=12, template="bilanzierung")
    b12.fields = [
        _f(Role.SAMPLE_ID, "Intermediat", "STRW 2201", conf=0.55, bbox=(0.80, 0.23, 0.95, 0.26)),
        _f(Role.TARE_MASS, "m Tara", "80", unit="kg", bbox=(0.61, 0.27, 0.78, 0.30)),
        _f(Role.GROSS_MASS, "m Brutto", "80", unit="kg", bbox=(0.61, 0.31, 0.78, 0.34)),
        _f(Role.NET_MASS, "m Netto", "200", unit="kg", bbox=(0.61, 0.34, 0.78, 0.37), conf=0.72),
        _f(Role.DENSITY, "rho", "1,05", unit="kg/L", bbox=(0.45, 0.38, 0.55, 0.41)),
        _f(Role.VOLUME, "V Netto", "210", unit="L", calc_expr="200 * 1,05", bbox=(0.61, 0.38, 0.78, 0.41)),
        _f(Role.CONCENTRATION, "c ABC-DE (Blocking IPC)", "3,1", unit="g/L", nks=2, bbox=(0.61, 0.42, 0.78, 0.45)),
        _f(Role.SIGNATURE_PROCESSED, "Bearbeitet", "10.06.2026 / abg", bbox=(0.40, 0.70, 0.70, 0.73)),
        _f(Role.SIGNATURE_CHECKED, "Geprueft", "11.06.2026 / pkr", bbox=(0.40, 0.74, 0.70, 0.77)),
    ]

    # p17: range field out of spec (35 vs Soll 20-30).
    b17 = Block(chapter="5.6.2", page_no=17, template="range")
    b17.fields = [
        _f(Role.CALC_RESULT, "Wippgeschwindigkeit", "35", unit="Huebe/min",
           soll="20 - 30", bbox=(0.61, 0.30, 0.78, 0.33), conf=0.84),
    ]

    return _assemble(doc, [people, b12, b17])


def _build_ganache(source_path: str | None = None) -> Document:
    """Sim 2: a multi-input formula error, a Geprüft-before-Bearbeitet 4-eyes
    order error and a non zero-padded date."""
    doc = Document(
        doc_no="SIM0002 · Batch Simulated",
        title="Herstellung von Chocolate Ganache Coating (Simulated)",
        rev="1", project_code="SIM", generated_at=date(2026, 6, 8),
        page_count=46, declared_page_count=46,
    )
    people = _roster(4, [("Lena Fischer", "lfi"), ("Tom Wagner", "twa")])

    # p14: clean balance, but Bearbeitet date "9.6.2026" is not zero-padded -> format warning.
    b14 = Block(chapter="5.3.1", page_no=14, template="bilanzierung")
    b14.fields = [
        _f(Role.TARE_MASS, "m Tara", "100", unit="kg", bbox=(0.61, 0.27, 0.78, 0.30)),
        _f(Role.GROSS_MASS, "m Brutto", "320", unit="kg", bbox=(0.61, 0.31, 0.78, 0.34)),
        _f(Role.NET_MASS, "m Netto", "220", unit="kg", bbox=(0.61, 0.34, 0.78, 0.37)),
        _f(Role.DENSITY, "rho", "1,00", unit="kg/L", bbox=(0.45, 0.38, 0.55, 0.41)),
        _f(Role.VOLUME, "V Netto", "220", unit="L", calc_expr="220 * 1,00", bbox=(0.61, 0.38, 0.78, 0.41)),
        _f(Role.SIGNATURE_PROCESSED, "Bearbeitet", "9.6.2026 / lfi", bbox=(0.40, 0.70, 0.70, 0.73)),
        _f(Role.SIGNATURE_CHECKED, "Geprueft", "10.06.2026 / twa", bbox=(0.40, 0.74, 0.70, 0.77)),
    ]

    # p20: printed formula 6,0*40 - 2,0*0,5 = 239, but 280 written -> formula error;
    # Geprüft (11.06) BEFORE Bearbeitet (12.06) -> 4-eyes order error.
    b20 = Block(chapter="5.12.3", page_no=20, template="calc")
    b20.fields = [
        _f(Role.CALC_RESULT, "Load Volumen", "280", unit="L",
           calc_expr="6,0 * 40 - 2,0 * 0,5", bbox=(0.61, 0.55, 0.80, 0.58), conf=0.95),
        _f(Role.SIGNATURE_PROCESSED, "Bearbeitet", "12.06.2026 / lfi", bbox=(0.40, 0.70, 0.70, 0.73)),
        _f(Role.SIGNATURE_CHECKED, "Geprueft", "11.06.2026 / twa", bbox=(0.40, 0.74, 0.70, 0.77)),
    ]

    return _assemble(doc, [people, b14, b20])


def _build_lemon(source_path: str | None = None) -> Document:
    """Sim 3: an anomaly-detection showcase — five mass balances where one batch's
    net (and gross) sits far outside its peers -> STAT_OUTLIER — plus a signature
    pair signed by the same person -> 4-eyes error. Otherwise clean."""
    doc = Document(
        doc_no="SIM0003 · Batch Simulated",
        title="Herstellung von Lemon Glaze Topping (Simulated)",
        rev="1", project_code="SIM", generated_at=date(2026, 6, 9),
        page_count=46, declared_page_count=46,
    )
    people = _roster(4, [("Mia Schulz", "msc"), ("Jan Vogel", "jvo")])

    # Five clean balances (net = gross - tare each), so none are calc-errors and all
    # feed the outlier scorer. The last batch's net 350 / gross 400 is the outlier.
    balances = [
        _balance(30, "5.3.1", 50, 250, 200),
        _balance(31, "5.4.1", 50, 252, 202),
        _balance(32, "5.5.1", 50, 248, 198),
        _balance(33, "5.6.1", 50, 251, 201),
        _balance(34, "5.7.1", 50, 400, 350),   # <- anomalous batch
    ]

    # p30: both signatures by the SAME person -> 4-eyes (same person) error.
    sig = Block(chapter="5.3.1", page_no=30, template="signature")
    sig.fields = [
        _f(Role.SIGNATURE_PROCESSED, "Bearbeitet", "10.06.2026 / msc", bbox=(0.40, 0.78, 0.70, 0.81)),
        _f(Role.SIGNATURE_CHECKED, "Geprueft", "10.06.2026 / msc", bbox=(0.40, 0.82, 0.70, 0.85)),
    ]

    return _assemble(doc, [people, *balances, sig])


# Rotation order: canonical first (familiar), then the three simulated batches.
_VARIANTS = [_build_canonical, _build_strawberry, _build_ganache, _build_lemon]
_rotate_idx = 0


class StubExtractor:
    name = "stub"

    def extract(self, source_path: str | None = None, pages=None) -> Document:
        # Only the API's ROTATE_SAMPLE sentinel advances the carousel; everything
        # else (incl. the ground-truth tests) gets the canonical sample.
        if source_path == ROTATE_SAMPLE:
            global _rotate_idx
            builder = _VARIANTS[_rotate_idx % len(_VARIANTS)]
            _rotate_idx += 1
            return builder(None)
        return _build_canonical(source_path)
