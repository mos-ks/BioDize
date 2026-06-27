"""Box placement: vlm_ypos disambiguates repeated-value rows and narrows the
whole-table block down to the field's actual row."""
from app.pipeline.localize import localize
from app.pipeline.model import BBox, Block, Document, Field
from app.pipeline.ocr.base import OcrResult, OcrWord


def _fld(label: str, value: str, ypos: float | None = None, xpos: float | None = None) -> Field:
    f = Field(page_no=1, chapter="", role=None, label_raw=label, value_raw=value)
    f.vlm_ypos = ypos
    f.vlm_xpos = xpos
    return f


def _doc(fields: list[Field]) -> Document:
    b = Block(chapter="", page_no=1, template="page")
    b.fields = fields
    d = Document(doc_no="d", title="t")
    d.blocks = [b]
    return d


def test_repeated_value_lands_on_the_right_row_via_ypos():
    # The same date appears on two rows; each field must land on ITS row, not both
    # on the topmost block (the old behaviour).
    blocks = [
        OcrWord("10.06.2026", BBox(0.40, 0.40, 0.70, 0.43)),
        OcrWord("10.06.2026", BBox(0.40, 0.60, 0.70, 0.63)),
    ]
    doc = _doc([
        _fld("Bearbeitet", "10.06.2026", ypos=0.41),
        _fld("Geprüft", "10.06.2026", ypos=0.61),
    ])
    localize(doc, {1: OcrResult(page_no=1, words=blocks)})
    f0, f1 = doc.all_fields()
    assert f0.bbox is not None and abs(f0.bbox.y0 - 0.40) < 1e-6
    assert f1.bbox is not None and abs(f1.bbox.y0 - 0.60) < 1e-6


def test_tall_table_block_is_narrowed_to_a_row_band():
    # A whole table comes back as ONE tall block; the field's box must be a thin
    # band at its row, not the page-tall block.
    table = OcrWord("Haltetemperatur Soll 2-8 Ja c ABC-DE 4,5", BBox(0.10, 0.30, 0.90, 0.70))
    doc = _doc([_fld("Haltetemperatur", "Ja", ypos=0.55)])
    localize(doc, {1: OcrResult(page_no=1, words=[table])})
    f = doc.all_fields()[0]
    assert f.bbox is not None
    assert (f.bbox.y1 - f.bbox.y0) < 0.05, "tall block should be narrowed to a row"
    cy = (f.bbox.y0 + f.bbox.y1) / 2
    assert abs(cy - 0.55) < 0.02, "row band should be centered on the field's ypos"
    # x extent is preserved from the block (reliable horizontally)
    assert abs(f.bbox.x0 - 0.10) < 1e-6 and abs(f.bbox.x1 - 0.90) < 1e-6


def test_full_width_table_row_is_split_into_columns_via_xpos():
    # Mistral returns a whole table ROW as one full-width block; the three cells
    # that land on it must each be narrowed to their column, not span the row.
    row = OcrWord("1720 0724228 5142", BBox(0.10, 0.60, 0.90, 0.62))
    f_a = _fld("Pos", "1720", ypos=0.61, xpos=0.20)
    f_b = _fld("Charge", "0724228", ypos=0.61, xpos=0.50)
    f_c = _fld("Menge", "5142", ypos=0.61, xpos=0.80)
    doc = _doc([f_a, f_b, f_c])
    localize(doc, {1: OcrResult(page_no=1, words=[row])})
    for f, xp in [(f_a, 0.20), (f_b, 0.50), (f_c, 0.80)]:
        assert f.bbox is not None
        assert (f.bbox.x1 - f.bbox.x0) < 0.79, "cell should be narrower than the full row"
        cx = (f.bbox.x0 + f.bbox.x1) / 2
        assert abs(cx - xp) < 0.06, "cell box should be centered on the value's column"
    # left-to-right column order preserved
    assert f_a.bbox.x0 < f_b.bbox.x0 < f_c.bbox.x0


def test_tight_cell_beats_whole_table_and_is_kept():
    table = OcrWord("m Netto 200 V Netto 220 rho 1,10", BBox(0.10, 0.30, 0.90, 0.70))
    cell = OcrWord("220", BBox(0.60, 0.45, 0.78, 0.48))
    doc = _doc([_fld("V Netto", "220", ypos=0.46)])
    localize(doc, {1: OcrResult(page_no=1, words=[table, cell])})
    f = doc.all_fields()[0]
    # Picks the tight cell and keeps it as-is (already a single row).
    assert f.bbox is not None
    assert abs(f.bbox.x0 - 0.60) < 1e-6 and abs(f.bbox.y0 - 0.45) < 1e-6
