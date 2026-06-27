"""StubExtractor — deterministic, offline fixture modeled on the real sample.

Lets the frontend integrate and the whole pipeline run with NO API calls. The
fixture intentionally includes several of the document's planted errors so that
validation produces a realistic spread of flags out of the box:

  * p11 Bilanzierung (ABCE) — clean: net = gross - tare, V = net x rho.
  * p10 §5.2 signature  — Geprueft (09.06) BEFORE Bearbeitet (10.06)  -> 4-eyes error
                          + same Kuerzel both roles                    -> 4-eyes error.
  * p17 Wippgeschw.      — 32 vs Soll 20-30 (no deviation in stub)     -> range error.
  * p40 Bilanzierung nPZ — net 200 but gross-tare = 0                   -> calc error.
  * a date "10.6.2026"   — not zero-padded                             -> format error.
"""
from __future__ import annotations

from datetime import date

from app.domain.roles import Role
from app.pipeline.model import BBox, Block, Document, Field, Read


def _f(role, label, value, *, unit=None, nks=None, soll=None, calc_expr=None, bbox=None,
       model="stub", conf=0.9, required=True):
    field = Field(
        page_no=0, chapter="", role=role, label_raw=label, value_raw=value,
        unit=unit, nks=nks, soll=soll, calc_expr=calc_expr,
        bbox=BBox(*bbox) if bbox else None, is_required=required,
    )
    field.reads = [Read(model=model, value_raw=value, confidence=conf, bbox=field.bbox)]
    return field


class StubExtractor:
    name = "stub"

    def extract(self, source_path: str | None = None, pages=None) -> Document:
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
        # V = m / rho (physics: density kg/L). 200 / 1,10 = 181.8 -> ~182 is clean.
        b11 = Block(chapter="5.3.1", page_no=11, template="bilanzierung")
        b11.fields = [
            # low-confidence read -> EXTRACT_LOW_CONF warning ("ask when unsure")
            _f(Role.SAMPLE_ID, "Intermediat", "ABCE 12345", conf=0.78, bbox=(0.80, 0.23, 0.95, 0.26)),
            _f(Role.TARE_MASS, "m Tara", "100", unit="kg", bbox=(0.61, 0.27, 0.78, 0.30)),
            _f(Role.GROSS_MASS, "m Brutto", "300", unit="kg", bbox=(0.61, 0.31, 0.78, 0.34)),
            _f(Role.NET_MASS, "m Netto", "200", unit="kg", bbox=(0.61, 0.34, 0.78, 0.37)),
            _f(Role.DENSITY, "rho", "1,10", unit="kg/L", bbox=(0.45, 0.38, 0.55, 0.41)),
            _f(Role.VOLUME, "V Netto", "182", unit="L", calc_expr="200 / 1,10", bbox=(0.61, 0.38, 0.78, 0.41)),
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

        for block in (b11, b10, b17, b40, b36, b4, b38):
            for fld in block.fields:
                fld.page_no = block.page_no
                fld.chapter = block.chapter
                fld.block_key = block.key
            doc.blocks.append(block)

        return doc
