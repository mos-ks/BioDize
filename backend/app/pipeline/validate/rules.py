"""Validation rules. Each binds to field ROLES (never labels) and yields Flags.

See docs/VALIDATION_RULES.md. Two severities only: error | warning. Clean
fields produce no flag. This scaffold implements the high-value classes
(format, four-eyes, calculation, range, temporal); applicability / cross-
reference / outlier are wired as TODOs for Day 2.
"""
from __future__ import annotations

import ast
import operator
import re
import statistics
from datetime import date, datetime, time, timedelta

from app.core.config import settings
from app.domain.roles import NUMERIC_ROLES, Role
from app.domain.severity import Category, Severity
from app.pipeline.model import Block, Document, Field, Flag
from app.pipeline.normalize import is_zero_padded_date, parse_date, parse_soll


def _err(cat, code, msg, expected=None, actual=None) -> Flag:
    return Flag(Severity.ERROR, cat, code, msg, str(expected) if expected is not None else None,
                str(actual) if actual is not None else None)


def _warn(cat, code, msg, expected=None, actual=None) -> Flag:
    return Flag(Severity.WARNING, cat, code, msg, str(expected) if expected is not None else None,
                str(actual) if actual is not None else None)


def parse_signature(raw: str) -> tuple[date | None, str, str | None]:
    """'10.06.2026 / ohe' -> (date, '10.06.2026', 'ohe')."""
    parts = (raw or "").split("/")
    date_str = parts[0].strip()
    kuerzel = parts[1].strip() if len(parts) > 1 else None
    return parse_date(date_str), date_str, kuerzel


def _calc_tol(expected: float) -> float:
    return max(0.5, abs(expected) * 0.01)


# --- field-level rules ------------------------------------------------------

def rule_date_format(field: Field) -> list[Flag]:
    if field.role in (Role.SIGNATURE_PROCESSED, Role.SIGNATURE_CHECKED):
        _, date_str, _ = parse_signature(field.value_raw)
        # Only flag if it's actually a date attempt (has digits) — a mislabeled
        # "Ja"/text signature isn't a malformed date.
        if date_str and re.search(r"\d", date_str) and not is_zero_padded_date(date_str):
            return [_err(Category.FORMAT, "FMT_DATE_PADDING",
                         f"Date '{date_str}' is not zero-padded DD.MM.YYYY",
                         expected="DD.MM.YYYY", actual=date_str)]
    elif field.value_type in ("date", "datetime"):
        date_str = field.value_raw.split()[0]
        if not is_zero_padded_date(date_str):
            return [_err(Category.FORMAT, "FMT_DATE_PADDING",
                         f"Date '{date_str}' is not zero-padded DD.MM.YYYY",
                         expected="DD.MM.YYYY", actual=date_str)]
    return []


def rule_time_format(field: Field) -> list[Flag]:
    """FMT_TIME_RANGE: times must be within 00:00-23:59."""
    from datetime import time as _time
    if field.value_type != "time" or not isinstance(field.value, _time):
        return []
    h, m = field.value.hour, field.value.minute
    if h > 23 or m > 59:
        raw = field.value_raw or ""
        return [_err(Category.FORMAT, "FMT_TIME_RANGE",
                     f"Time '{raw}' is outside 00:00-23:59",
                     expected="00:00-23:59", actual=raw)]
    return []


def rule_nks(field: Field) -> list[Flag]:
    """Nachkommastellen: when the form states a required number of decimal places
    (field.nks), the WRITTEN value must carry exactly that many — '20,20' is right
    for 2, '20,2' is wrong. Trailing zeros count, so this catches dropped precision
    on both plain entries and calculated results (25 * 23,4 must read '585,0')."""
    if field.nks is None:
        return []
    got = field.decimals if field.decimals is not None else _written_decimals(field.value_raw)
    if got is not None and got != field.nks:
        return [_warn(Category.FORMAT, "FMT_NKS",
                      f"{field.value_raw}: {got} Nachkommastelle(n), but {field.nks} required",
                      expected=field.nks, actual=got)]
    return []


def rule_range(field: Field) -> list[Flag]:
    spec = parse_soll(field.soll)
    # bool is a subclass of int — exclude checkbox values from numeric range checks.
    if not spec or not isinstance(field.value, (int, float)) or isinstance(field.value, bool):
        return []
    v = float(field.value)
    lo, hi, target = spec.get("min"), spec.get("max"), spec.get("target")
    # TODO: downgrade to WARNING when a matching Abweichung exists for this page.
    if lo is not None and v < lo:
        return [_err(Category.RANGE, "RANGE_SOLL", f"{v} below Soll min {lo}", expected=f">= {lo}", actual=v)]
    if hi is not None and v > hi:
        return [_err(Category.RANGE, "RANGE_SOLL", f"{v} above Soll max {hi}", expected=f"<= {hi}", actual=v)]
    # Only treat a bare single number as a setpoint when the Soll text is a clean
    # numeric spec — not a formula/density blob the model may have dropped in soll
    # (e.g. "V = m / rho, rho = 1,81 kg/L"), which would be a false positive.
    if target is not None and lo is None and hi is None and v != target:
        if re.fullmatch(r"[\s\d.,]+", (field.soll or "").strip()):
            return [_err(Category.RANGE, "RANGE_SETPOINT", f"{v} != Soll {target}", expected=target, actual=v)]
    return []


_AROPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
          ast.Div: operator.truediv, ast.USub: operator.neg, ast.UAdd: operator.pos}


def safe_arith(expr_de: str | None) -> float | None:
    """Evaluate a simple German arithmetic expression ('6,6 * 45 - 4,3 * 0,75').

    Only +-*/ and parentheses; anything else -> None. Decimal comma is converted
    to a dot. The result/right-hand side is taken if an '=' is present.
    """
    if not expr_de:
        return None
    s = expr_de.split("=")[-1] if expr_de.count("=") == 1 else expr_de.split("=")[0]
    s = s.replace(",", ".")
    s = re.sub(r"[^0-9.+\-*/() ]", "", s).strip()   # strip: ast eval-mode rejects leading space
    if not s:
        return None
    try:
        return _eval_arith(ast.parse(s, mode="eval").body)
    except (SyntaxError, KeyError, ValueError, ZeroDivisionError, RecursionError):
        return None


def _eval_arith(node):
    if isinstance(node, ast.BinOp):
        return _AROPS[type(node.op)](_eval_arith(node.left), _eval_arith(node.right))
    if isinstance(node, ast.UnaryOp):
        return _AROPS[type(node.op)](_eval_arith(node.operand))
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    raise ValueError("unsupported expression")


def _kfm_round(x: float, n: int) -> float:
    """Kaufmännische Rundung (round half AWAY from zero) to n decimal places —
    the convention these forms use, unlike Python's round() (half-to-even)."""
    from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
    try:
        return float(Decimal(str(x)).quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return round(x, n)


def _written_decimals(raw: str | None) -> int | None:
    """Count the decimal places actually WRITTEN in a raw numeric string, keeping
    trailing zeros: '20,20'->2, '20,2'->1, '585'->0, '4,50 kg'->2. None if no number."""
    if not raw:
        return None
    m = re.search(r"\d+[.,](\d+)", raw)
    if m:
        return len(m.group(1))
    return 0 if re.search(r"\d", raw) else None


def rule_formula(field: Field) -> list[Flag]:
    """Re-evaluate a printed formula and compare to the written result.

    Printed formulas are evaluated exactly as represented by ``calc_expr``.  The
    generic mass-balance volume rule lives in ``rule_volume`` below.
    """
    if not field.calc_expr or not isinstance(field.value, (int, float)) or isinstance(field.value, bool):
        return []
    expr     = field.calc_expr.strip()
    computed = safe_arith(expr)
    if computed is None:
        return []
    diff = abs(computed - float(field.value))
    nks = field.nks if field.nks is not None else 0
    place = 10 ** (-nks)
    correct = _kfm_round(computed, nks)        # kaufmännisch-correct rounding
    if diff <= 0.5 * place:
        # within one rounding step: clean only if it IS the exact value or the
        # kaufmännisch-correct rounding; a wrong-direction round is a Rundungsfehler.
        if diff < 1e-9 or abs(float(field.value) - correct) < 0.5 * place:
            return []
        return [_warn(Category.CALCULATION, "CALC_ROUNDING",
                      f"{field.value}: Rundungsfehler — kaufmännisch gerundet wäre {correct} ({round(computed, 3)})",
                      expected=correct, actual=field.value)]
    if diff <= 1.5 * place:
        return [_warn(Category.CALCULATION, "CALC_ROUNDING",
                      f"result {field.value} vs formula {round(computed, 3)} — Rundungsfehler (korrekt {correct})",
                      expected=correct, actual=field.value)]
    return [_err(Category.CALCULATION, "CALC_FORMULA",
                 f"{field.calc_expr.strip()} = {round(computed, 3)}, but {field.value} was recorded",
                 expected=round(computed, 3), actual=field.value)]


# --- block-level rules ------------------------------------------------------


# A blank field "expects a value" (-> Suspect/missing when empty) when it carries a
# Soll target or its label names a concrete required entry. This keeps the blank-value
# check from firing on every optional free-text line. Tunable: widen/narrow this set
# against the real document to balance FP vs FN (we err toward FP — better than FN).
_EXPECTS_VALUE_KW = re.compile(
    r"\b(nummer|nr\.?|anlagen|datum|uhrzeit|menge|gewicht|masse|volumen|temperatur|"
    r"charge|seite|wert|konzentration|dichte|zeit)\b", re.I)


def _expects_value(f: Field) -> bool:
    if (f.value_raw or "").strip():
        return False                      # not blank -> nothing to flag
    if f.soll:
        return True                       # has a Soll/Richtwert -> an entry is expected
    return bool(_EXPECTS_VALUE_KW.search(f.label_raw or ""))


# A checkbox carrying only a void mark (a slash/dash through an empty box, etc.) is
# NOT a real answer — the host reads these as "not checked". Treat them as unmarked.
_VOID_MARKS = {"", "/", "\\", "-", "–", "—", ".", "·", "n/a", "-/-", "()", "[]"}

# An EMPTY box/circle glyph the reader transcribed in front of the option label
# ("O Ja", "○ 931", "□ Nein") means the option is shown but NOT ticked — the host
# reads it as "not checked". Filled marks (●, ☑, ⊠, ✓, x) are deliberately excluded.
_EMPTY_BOX_OPTION = re.compile(r"^[oO0○◯Ｏ□☐]\s+\S")


def _checkbox_unmarked(value_raw: str | None) -> bool:
    v = (value_raw or "").strip()
    if v.lower() in _VOID_MARKS:
        return True
    return bool(_EMPTY_BOX_OPTION.match(v))


def rule_presence(block: Block) -> list[Flag]:
    """Presence is a first-class rule: signature present, checkmark present.
    A blank Bearbeitet/Geprüft = a missing required signature; a date without a
    Kürzel (or vice versa) = incomplete; a checkbox/selection with nothing marked
    = an unanswered question (missing data). Use-case, not OCR — the exact
    initials are irrelevant (4-eyes handles same-vs-different). Skipped when the
    chapter is marked 'findet keine Anwendung' (N/A), where blanks are expected."""
    # Deviation table: each "Weitere Abweichungen" row must carry an answer. When the
    # table has ACTIVE deviations (some row = "Ja"), a blank row checkbox is a real
    # missing answer the host marks Suspect/missing — flag it even though another row
    # says "...keine Anwendung" (that phrase only N/As its OWN row, not the table).
    dev = [f for f in block.fields
           if f.value_type == "checkbox" and "abweichung" in (f.label_raw or "").lower()]
    if any((f.value_raw or "").strip().lower().startswith("ja") for f in dev):
        for f in dev:
            if not (f.value_raw or "").strip():
                f.add_flag(_err(Category.MISSING, "MISSING_CHECKMARK",
                                "Deviation row left unanswered (no option marked)",
                                expected="a marked option", actual="none"))
    # "...findet keine Anwendung" marks a section N/A only as a NEGATIVE answer
    # ("Nein, ... keine Anwendung"). The same phrase inside a "Ja, ..." option or a
    # broken cross-reference must NOT N/A an otherwise-active page, or blank required
    # boxes (e.g. an unmarked confirmation checkbox) get silently suppressed.
    def _is_na(v: str | None) -> bool:
        v = (v or "").strip().lower()
        return "keine anwendung" in v and not v.startswith("ja")
    if any(_is_na(f.value_raw) for f in block.fields):
        return []
    # Roles already satisfied by a SIGNED signature in this block, and how many of each
    # role the block carries. When an equipment table holds ONE section signature but
    # extraction splits it into a per-row column (one blank "X - Bearbeitet" per
    # machine), those blanks are artifacts — suppress them. But only for a LARGE group
    # (>=3 same-role sigs): a lone signed+blank pair is a genuinely separate, missing
    # signature the host expects flagged, so we must not swallow it.
    signed_roles: set = set()
    sig_role_count: dict = {}
    for f in block.fields:
        if f.role in (Role.SIGNATURE_PROCESSED, Role.SIGNATURE_CHECKED):
            sig_role_count[f.role] = sig_role_count.get(f.role, 0) + 1
            _, ds, kz = parse_signature(f.value_raw)
            if (ds and re.search(r"\d", ds)) or (kz and re.search(r"[A-Za-zÄÖÜäöüß]", kz)):
                signed_roles.add(f.role)
    for f in block.fields:
        if f.role in (Role.SIGNATURE_PROCESSED, Role.SIGNATURE_CHECKED):
            # A checkbox whose label happens to contain 'geprüft' (e.g. "BK-SOP-xyz
            # geprüft" -> Ja) gets a signature role by keyword, but an answered
            # 'Ja'/'Nein' is NOT a blank signature — don't fire MISSING_SIGNATURE.
            if (f.value_raw or "").strip().lower() in {"ja", "nein", "x", "✓", "n/a"}:
                continue
            _, date_str, kz = parse_signature(f.value_raw)
            has_date = bool(date_str and re.search(r"\d", date_str))
            has_kz = bool(kz and re.search(r"[A-Za-zÄÖÜäöüß]", kz))
            if not has_date and not has_kz:
                # Suppress ONLY a per-row split of one section signature: a large group
                # (>=3) of same-role signatures where one is signed (the p18 equipment
                # table). A lone signed+blank pair (e.g. a separate "Geräte" / "Floor
                # Scale" signature) is a genuinely missing signature — flag it.
                if f.role in signed_roles and sig_role_count.get(f.role, 0) >= 3:
                    continue
                f.add_flag(_err(Category.MISSING, "MISSING_SIGNATURE",
                                "Required signature is blank (no date or Kürzel)",
                                expected="signed", actual="blank"))
            elif has_date != has_kz:
                msg = "Signature has a date but no Kürzel" if has_date else "Signature has a Kürzel but no date"
                f.add_flag(_warn(Category.MISSING, "SIG_INCOMPLETE", msg,
                                 expected="date + Kürzel", actual=(f.value_raw or "").strip() or "(blank)"))
        elif f.value_type == "checkbox" and _checkbox_unmarked(f.value_raw):
            f.add_flag(_err(Category.MISSING, "MISSING_CHECKMARK",
                            "Checkbox/selection has nothing marked (unanswered)",
                            expected="a marked option", actual=(f.value_raw or "").strip() or "none"))
        elif _expects_value(f):
            # A blank field that clearly expects an entry (Anlagennummer, Datum,
            # a Soll-bearing value, ...) — the host marks these "Suspect / missing".
            f.add_flag(_err(Category.MISSING, "MISSING_VALUE",
                            "Required value is blank (no entry)",
                            expected="a value", actual="blank"))
    return []

def rule_net_mass(block: Block) -> list[Flag]:
    """net = gross - tare, for EVERY mass group in the block. A page often carries
    two groups (vPz and nPZ) plus a single shared tare; the old single-group check
    only validated the first, so the second group's net (e.g. nPZ 395 vs 527-127
    = 400) slipped through. Pair gross/net in order; reuse the shared tare."""
    def nums(role):
        return [f for f in block.roles(role)
                if isinstance(f.value, (int, float)) and not isinstance(f.value, bool)]
    tares, grosses, nets = nums(Role.TARE_MASS), nums(Role.GROSS_MASS), nums(Role.NET_MASS)
    if not grosses or not nets:
        return []
    for i, (g, n) in enumerate(zip(grosses, nets)):
        t = tares[i] if i < len(tares) else (tares[0] if tares else None)
        if t is None:
            continue
        expected = g.value - t.value
        if abs(n.value - expected) > _calc_tol(expected):
            n.add_flag(_err(Category.CALCULATION, "CALC_NET_MASS",
                            f"net should equal gross - tare = {g.value} - {t.value} = {expected}",
                            expected=expected, actual=n.value))
    return []


_RHO_IN_LABEL = re.compile(r"[ρr]\s*=\s*([\d,.]+)\s*kg/L", re.IGNORECASE)


def _rho_from_label(label: str) -> float | None:
    """Extract density from a label like 'V Netto (V = m / ρ; ρ = 1,100 kg/L)'."""
    from app.pipeline.normalize import parse_german_number
    m = _RHO_IN_LABEL.search(label or "")
    if m:
        val, _ = parse_german_number(m.group(1))
        return val
    return None


def rule_volume(block: Block) -> list[Flag]:
    """V = m * rho for the mass-balance volume fields.

    Two paths:
    (a) A dedicated density field exists in the block → standard path.
    (b) Density is embedded in the volume field's label text (e.g. 'ρ = 1,100 kg/L')
        → parse from label so the rule fires even without an explicit rho field.
    """
    net = block.role(Role.NET_MASS)
    vol = block.role(Role.VOLUME)
    if not (net and vol):
        return []
    if not isinstance(vol.value, (int, float)) or not isinstance(net.value, (int, float)):
        return []

    # Path (a): explicit density field
    rho_f = block.role(Role.DENSITY)
    if rho_f and isinstance(rho_f.value, (int, float)) and rho_f.value != 0:
        rho_val = rho_f.value
    else:
        # Path (b): density in label text
        rho_val = _rho_from_label(vol.label_raw)

    if rho_val is None or rho_val == 0:
        return []

    expected = net.value * rho_val
    if abs(vol.value - expected) > _calc_tol(expected):
        vol.add_flag(_err(Category.CALCULATION, "CALC_VOLUME",
                          f"V = m * rho = {net.value} * {rho_val} = {round(expected, 3)}, "
                          f"recorded {vol.value}",
                          expected=round(expected, 3), actual=vol.value))
    return []


# Below this recognition confidence a 2-3 letter Kürzel is considered illegible:
# two such reads matching is more likely an OCR collision than a real same-signer
# violation, so route to review instead of asserting an error.
_SIG_LEGIBLE_MIN = 0.40


def _recog_conf(f: Field) -> float | None:
    """Legibility of the recognized value (reader self-confidence), preferred over
    the resolve-inflated registry-match confidence so an illegible Kürzel stays low."""
    if f.reads:
        return min(r.confidence for r in f.reads)
    return f.ocr_confidence


_FORMULA_UNIT = re.compile(r"\[[^\]]*\]|(?<![A-Za-z])(kg/L|g/L|mg/L|kg|mg|g|mL|L|min|h|°C|%)(?![A-Za-z])")


def _resolve_label_formula(field: Field, siblings: list[Field]) -> float | None:
    """If the field's label is 'RESULT = EXPR' and EXPR names other fields on the
    page, substitute each named field's value and evaluate. Returns None (never a
    flag) unless EVERY variable resolves — conservative on purpose."""
    label = field.label_raw or ""
    if "=" not in label:
        return None
    rhs = label.split("=", 1)[1]
    # substitute the longest sibling names first so 'm B10-PP Netto nPZ Z1' is
    # replaced before the shorter 'm B10-PP Z1'.
    subs = sorted(
        (s for s in siblings if isinstance(s.value, (int, float)) and not isinstance(s.value, bool)),
        key=lambda s: -len(re.sub(r"\[.*?\]", "", s.label_raw or "")))
    for s in subs:
        var = re.sub(r"\[.*?\]", "", s.label_raw or "").strip()
        if len(var) >= 3 and var.lower() in rhs.lower():
            rhs = re.sub(re.escape(var), f" {s.value} ", rhs, flags=re.I)
    rhs = _FORMULA_UNIT.sub(" ", rhs)                      # strip units ([kg], g/L, ...)
    rhs = rhs.replace("×", "*").replace("·", "*").replace("÷", "/")
    if re.search(r"[A-Za-zÄÖÜäöüß]", rhs):                 # an unresolved variable -> don't guess
        return None
    return safe_arith(rhs)


def rule_cross_formula(block: Block) -> list[Flag]:
    """Validate a result whose formula is printed IN ITS LABEL and references other
    fields on the page (e.g. 'm Z1 [g] = m Netto Z1 [kg] / 1,31 kg/L x c Z1 [g/L]').
    Skips fields already calc-checked via calc_expr, and only fires when the whole
    formula resolves to numbers — so it never invents a false positive."""
    _CALC = {"CALC_FORMULA", "CALC_ROUNDING", "CALC_NET_MASS", "CALC_VOLUME"}
    for f in block.fields:
        if not isinstance(f.value, (int, float)) or isinstance(f.value, bool):
            continue
        if any(fl.code in _CALC for fl in f.flags):
            continue
        computed = _resolve_label_formula(f, [s for s in block.fields if s is not f])
        if computed is None:
            continue
        place = 10 ** (-(f.nks if f.nks is not None else 0))
        diff = abs(computed - float(f.value))
        if diff <= 0.5 * place:
            continue
        if diff <= 1.5 * place:
            f.add_flag(_warn(Category.CALCULATION, "CALC_ROUNDING",
                             f"label formula = {round(computed, 3)} vs recorded {f.value} (rounding)",
                             expected=round(computed, 3), actual=f.value))
        else:
            f.add_flag(_err(Category.CALCULATION, "CALC_FORMULA",
                            f"label formula = {round(computed, 3)}, but {f.value} was recorded",
                            expected=round(computed, 3), actual=f.value))
    return []


def rule_four_eyes(block: Block) -> list[Flag]:
    # A page can carry several Bearbeitet/Gepruft pairs; pair them in field order
    # (the OpenAI reader puts all of a page's fields in one block).
    for proc, chk in zip(block.roles(Role.SIGNATURE_PROCESSED), block.roles(Role.SIGNATURE_CHECKED)):
        d_proc, _, k_proc = parse_signature(proc.value_raw)
        d_chk, _, k_chk = parse_signature(chk.value_raw)
        cp, cc = _recog_conf(proc), _recog_conf(chk)
        dates_legible = (cp is None or cp >= _SIG_LEGIBLE_MIN) and (cc is None or cc >= _SIG_LEGIBLE_MIN)
        if dates_legible and d_proc and d_chk and d_chk < d_proc:
            chk.add_flag(_err(Category.FOUR_EYES, "4EYES_ORDER",
                              "Gepruft date is before Bearbeitet date (review must follow processing)",
                              expected=f">= {d_proc.isoformat()}", actual=d_chk.isoformat()))
        if k_proc and k_chk and k_proc.lower() == k_chk.lower():
            # Only a HARD violation when both signatures are legibly read. When either
            # is low-confidence the equality is likely the reader collapsing two
            # different scrawls (e.g. Hans's 'hm' misread as 'ohe') onto one Kürzel —
            # that field is already routed to review by its low confidence; don't
            # stack a false "same person" error on top.
            legible = dates_legible
            if legible:
                chk.add_flag(_err(Category.FOUR_EYES, "4EYES_DISTINCT",
                                  "Bearbeitet and Gepruft signed by the same person",
                                  expected="two different Kurzel", actual=k_chk))
    return []


def rule_end_after_start(block: Block) -> list[Flag]:
    start, end = block.role(Role.HOLD_START), block.role(Role.HOLD_END)
    # Only compare when both parsed to the same comparable temporal type
    # (a partial read may leave one as a raw string — don't crash on it).
    if (start and end and type(start.value) is type(end.value)
            and isinstance(start.value, (datetime, date, time)) and end.value <= start.value):
        end.add_flag(_err(Category.TEMPORAL, "TIME_END_AFTER_START",
                          "End timestamp is not after start", expected=f"> {start.value}", actual=str(end.value)))
    return []


def _clock_minutes(f: "Field") -> int | None:
    """Minutes-since-midnight for a parsed clock time, else None."""
    return f.value.hour * 60 + f.value.minute if isinstance(f.value, time) else None


def rule_duration(block: Block) -> list[Flag]:
    """A recorded elapsed time must equal Ende - Start. Forms log a Start time, an
    Ende time and the 'tatsächliche' (or 'Dauer') elapsed time — e.g. a
    Prozessverzögerung of 11:27 -> 12:27 is 1:00, so a recorded 2:00 is a
    calculation error the host marks 'value does not fit calculation'. Only fires
    when all three clock times are present, so a blank/NA section is untouched."""
    def pick(*keys):
        for f in block.fields:
            lab = (f.label_raw or "").lower()
            if isinstance(f.value, time) and any(k in lab for k in keys):
                return f
        return None
    start, end = pick("start"), pick("ende", "end")
    dur = pick("tatsächlich", "tatsachlich", "dauer", "verzögerung gesamt")
    if not (start and end and dur) or dur in (start, end):
        return []
    expected = _clock_minutes(end) - _clock_minutes(start)
    if expected < 0:
        expected += 24 * 60                     # crossed midnight
    actual = _clock_minutes(dur)
    if abs(actual - expected) > 1:              # 1-min tolerance for rounding
        eh, em = divmod(expected, 60)
        dur.add_flag(_err(Category.CALCULATION, "CALC_DURATION",
                          f"recorded {dur.value_raw} but Ende - Start = "
                          f"{end.value_raw} - {start.value_raw} = {eh}:{em:02d}",
                          expected=f"{eh}:{em:02d}", actual=dur.value_raw))
    return []


# --- document-level rules (need cross-field / print-date context) -----------

_BATCH_DATE_ROLES = {Role.SIGNATURE_PROCESSED, Role.SIGNATURE_CHECKED, Role.HOLD_START, Role.HOLD_END}


def print_date(doc: Document) -> date | None:
    """The record's generation/print date — the lower bound for batch-execution
    dates. Prefer an explicit 'generiert am' field; fall back to doc.generated_at."""
    for f in doc.all_fields():
        low = (f.label_raw or "").lower()
        if "generiert" in low or "production record" in low:
            d, _, _ = parse_signature(f.value_raw)
            if d:
                return d
    return doc.generated_at


def _field_date(field: Field) -> date | None:
    if field.role in (Role.SIGNATURE_PROCESSED, Role.SIGNATURE_CHECKED):
        d, _, _ = parse_signature(field.value_raw)
        return d
    v = field.value
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return None


def rule_dates_document(doc: Document, ref: date | None) -> None:
    """Flag batch-execution dates that fall before the record's print date or far
    in the future — typically year misreads (e.g. p38 2026->2016, p17 ->2028).

    The YEAR check works even without an explicit print date: the batch year is the
    document's own modal year, so a lone '2025' among '2026' dates is caught. The
    before-print / far-future checks still need an actual print DATE."""
    from app.pipeline.normalize import _doc_reference_year
    batch_year = ref.year if ref else _doc_reference_year(doc)
    horizon = ref + timedelta(days=180) if ref else None
    for f in doc.all_fields():
        if f.role not in _BATCH_DATE_ROLES:
            continue
        # GxP: surface the RAW recorded year (e.g. 2025/2028/2016) whenever it
        # differs from the document's batch year, so a human verifies the original.
        rawm = re.search(r"\b\d{1,2}\.\d{1,2}\.(\d{4})\b", f.value_raw or "")
        if batch_year and rawm and int(rawm.group(1)) != batch_year:
            f.add_flag(_err(Category.TEMPORAL, "DATE_YEAR_SUSPECT",
                            f"recorded year {rawm.group(1)} != batch year {batch_year}; "
                            f"verify the original",
                            expected=str(batch_year), actual=rawm.group(1)))
        if not ref:
            continue                      # the remaining checks need an actual print DATE
        d = _field_date(f)
        if d is None:
            continue
        if d < ref:
            f.add_flag(_warn(Category.TEMPORAL, "DATE_BEFORE_PRINT",
                             f"date {d.isoformat()} is before the record date {ref.isoformat()}",
                             expected=f">= {ref.isoformat()}", actual=d.isoformat()))
        elif d > horizon:
            f.add_flag(_warn(Category.TEMPORAL, "DATE_FAR_FUTURE",
                             f"date {d.isoformat()} is implausibly far after the record date",
                             expected=f"<= {horizon.isoformat()}", actual=d.isoformat()))


def _within_edits(a: str, b: str, max_edits: int) -> bool:
    """True if the Levenshtein distance(a, b) <= max_edits (tolerates OCR noise)."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > max_edits:
        return False
    prev = list(range(lb + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > max_edits:
            return False
        prev = cur
    return prev[lb] <= max_edits


def _registry_kuerzel(doc: Document) -> set[str]:
    """Kuerzel registered in the personnel table (Beteiligte Personen, p4).
    Matches label 'Kürzel' / 'Kuerzel' / 'kurzel' case-insensitively."""
    reg: set[str] = set()
    for f in doc.all_fields():
        lbl = (f.label_raw or "").strip().lower()
        lbl_norm = lbl.replace("ü", "u").replace("ue", "u")
        if lbl_norm in ("kurzel", "kuerzel") and f.value_raw:
            reg.add(f.value_raw.strip().lower())
    return reg


def rule_kuerzel_document(doc: Document) -> None:
    """Flag a signature Kürzel that isn't in the personnel list (Beteiligte Personen).
    Edit-distance-2 tolerance + a registry of >=2 entries keeps OCR noise from
    drowning the queue — only clearly-unregistered initials flag (warning — a human
    checks the original)."""
    registry = _registry_kuerzel(doc)
    if len(registry) < 2:
        return
    for f in doc.all_fields():
        if f.role not in (Role.SIGNATURE_PROCESSED, Role.SIGNATURE_CHECKED):
            continue
        _, _, k = parse_signature(f.value_raw)
        if not k or len(k) < 2:
            continue
        if not any(_within_edits(k.lower(), r, 2) for r in registry):
            f.add_flag(_warn(Category.FOUR_EYES, "KUERZEL_UNKNOWN",
                             f"Kuerzel '{k}' is not in the personnel list (Beteiligte Personen)",
                             expected="a registered Kuerzel", actual=k))


_XREF_RE = re.compile(r"kapitel\s*([0-9]+(?:\.[0-9]+)*)", re.I)


def _xref_compare(a, b) -> str:
    """Compare carried value to source. Returns 'match', 'near_miss', or 'mismatch'."""
    if a is None or b is None:
        return "match"
    if isinstance(a, bool) or isinstance(b, bool):
        return "match" if a == b else "mismatch"
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        diff = abs(a - b)
        tol  = max(0.5, abs(b) * 0.01)
        if diff <= 0:
            return "match"
        if diff <= tol:
            return "near_miss"
        return "mismatch"
    # Non-numeric: exact string comparison after normalisation
    return "match" if str(a).strip() == str(b).strip() else "mismatch"


def rule_xref_document(doc: Document) -> None:
    """Cross-reference (Übertrag): a carried value must equal its source field.

    Per VALIDATION_RULES.md:
      full mismatch  -> XREF_CARRIED_MATCH error
      rounding delta -> XREF_NEAR_MISS warning
    Conservative: only fires on explicit 'Übertrag … Kapitel X' labels.
    """
    index: dict[tuple[str, str], Field] = {}
    for f in doc.all_fields():
        if f.chapter and f.role and (f.chapter, f.role) not in index:
            index[(f.chapter, f.role)] = f
    for f in doc.all_fields():
        low = (f.label_raw or "").lower()
        if "übertrag" not in low and "ubertrag" not in low:
            continue
        m = _XREF_RE.search(f.label_raw or "")
        if not m or not f.role:
            continue
        src = index.get((m.group(1), f.role))
        if src is None or src is f:
            continue
        verdict = _xref_compare(f.value, src.value)
        if verdict == "mismatch":
            f.add_flag(_err(Category.CROSS_REFERENCE, "XREF_CARRIED_MATCH",
                            f"carried value '{f.value}' != source (Kapitel {m.group(1)}) '{src.value}'",
                            expected=str(src.value), actual=str(f.value)))
        elif verdict == "near_miss":
            f.add_flag(_warn(Category.CROSS_REFERENCE, "XREF_NEAR_MISS",
                             f"carried value '{f.value}' ~= source (Kapitel {m.group(1)}) '{src.value}' (rounding)",
                             expected=str(src.value), actual=str(f.value)))


def rule_stat_outlier(doc: Document) -> None:
    """Anomaly detection: a numeric value sitting beyond k standard deviations of
    its role-peers (the other masses / volumes / concentrations… recorded in this
    document) is flagged as a STAT_OUTLIER warning. Catches transcription anomalies
    that pass the per-field rules. Skips values already flagged by a hard rule
    (no double-noise) and needs a minimum number of peers for a meaningful std."""
    k = settings.outlier_std_k
    min_n = settings.outlier_min_samples
    by_role: dict[str, list[Field]] = {}
    for f in doc.all_fields():
        if (f.role in NUMERIC_ROLES and isinstance(f.value, (int, float))
                and not isinstance(f.value, bool) and not f.has_error):  # known-bad excluded
            by_role.setdefault(f.role, []).append(f)
    for role, fields in by_role.items():
        vals = [float(f.value) for f in fields]
        n = len(vals)
        if n < min_n:
            continue
        total, total_sq = sum(vals), sum(v * v for v in vals)
        label = str(getattr(role, "value", role)).replace("_", " ")
        for f in fields:
            # LEAVE-ONE-OUT z-score: compare this value to its PEERS (everyone else),
            # so a lone outlier can't inflate the mean/std and mask itself.
            v = float(f.value)
            pn = n - 1
            pmean = (total - v) / pn
            pvar = max(0.0, (total_sq - v * v) / pn - pmean * pmean)
            psd = pvar ** 0.5
            if psd == 0:
                continue
            z = (v - pmean) / psd
            if abs(z) > k:
                f.add_flag(_warn(Category.OUTLIER, "STAT_OUTLIER",
                                 f"{f.value} is {abs(z):.1f}σ from its {label} peers "
                                 f"(mean {round(pmean, 2)}, n={pn}) — possible anomaly",
                                 expected=f"{round(pmean, 2)} ± {round(psd, 2)}", actual=f.value))


def _identifier_key(label: str | None) -> str | None:
    """Map a label to a doc-CONSTANT identifier class (these must read the same
    everywhere in one batch record). Excludes Production Code — it varies per step."""
    l = (label or "").lower()
    if re.search(r"\bbatch\s*(no|nr)\b", l) or "chargennummer" in l or re.fullmatch(r"\s*batch\s*", l):
        return "Batch No."
    if re.search(r"\bdok[\s.\-]?nr\b", l):
        return "Dok-Nr."
    if "projektcode" in l:
        return "Projektcode"
    return None


def rule_identifier_consistency(doc: Document) -> None:
    """Cross-check that a parameter which must be CONSTANT across the whole record
    (Batch No., Dok-Nr, Projektcode) reads the same everywhere — if one occurrence
    suddenly differs, flag it (the foundation for the value-history database check)."""
    from collections import Counter

    def _norm(v: str | None) -> str:
        return re.sub(r"\s+", "", (v or "").upper())

    groups: dict[str, list[Field]] = {}
    for f in doc.all_fields():
        key = _identifier_key(f.label_raw)
        if key and (f.value_raw or "").strip():
            groups.setdefault(key, []).append(f)

    for key, flds in groups.items():
        counts = Counter(_norm(f.value_raw) for f in flds)
        if len(counts) < 2:
            continue
        majority = counts.most_common(1)[0][0]
        for f in flds:
            if _norm(f.value_raw) != majority:
                f.add_flag(_warn(Category.CROSS_REFERENCE, "CONSISTENCY_MISMATCH",
                                 f"{key} '{f.value_raw}' differs from '{majority}' used elsewhere in this batch record",
                                 expected=majority, actual=f.value_raw))


def rule_crossed_out(field: Field) -> list[Flag]:
    """A struck-through / durchgestrichen entry is a correction — surface it so the
    reviewer confirms the intended value rather than trusting the crossed text."""
    if getattr(field, "is_crossed_out", False):
        return [_warn(Category.EXTRACTION, "CROSSED_OUT",
                      "Entry appears struck through (durchgestrichen) — verify the intended value",
                      actual=field.value_raw)]
    return []


# --- registries -------------------------------------------------------------

FIELD_RULES = [rule_date_format, rule_time_format, rule_nks, rule_range, rule_formula, rule_crossed_out]
BLOCK_RULES = [rule_net_mass, rule_volume, rule_cross_formula, rule_four_eyes, rule_end_after_start, rule_duration, rule_presence]
