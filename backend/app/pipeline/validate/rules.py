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
from datetime import date, datetime, timedelta

from app.domain.roles import Role
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


def rule_nks(field: Field) -> list[Flag]:
    if field.nks is not None and field.decimals is not None and field.decimals != field.nks:
        return [_warn(Category.FORMAT, "FMT_NKS",
                      f"Expected {field.nks} decimal places, got {field.decimals}",
                      expected=field.nks, actual=field.decimals)]
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
    s = re.sub(r"[^0-9.+\-*/() ]", "", s)
    if not s.strip():
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


def rule_formula(field: Field) -> list[Flag]:
    """Re-evaluate a printed formula (with the handwritten numbers) and compare
    to the written result. Catches arithmetic/unit mistakes (e.g. p36 Load Volumen)."""
    if not field.calc_expr or not isinstance(field.value, (int, float)) or isinstance(field.value, bool):
        return []
    expr = field.calc_expr.strip()
    # The form prints "V = m / rho", but the domain physics is V = m x rho. For a
    # volume written as a simple division, verify the multiplication instead.
    if field.role == Role.VOLUME and re.fullmatch(r"[\d.,]+\s*/\s*[\d.,]+", expr):
        a, b = expr.split("/", 1)
        computed = safe_arith(f"{a} * {b}")
    else:
        computed = safe_arith(expr)
    if computed is None:
        return []
    diff = abs(computed - float(field.value))
    # NKS-aware tolerance: a correctly-rounded result is within half the last place.
    place = 10 ** (-(field.nks if field.nks is not None else 0))
    if diff <= 0.5 * place:
        return []
    if diff <= 1.5 * place:
        return [_warn(Category.CALCULATION, "CALC_ROUNDING",
                      f"result {field.value} vs formula {round(computed, 3)} (rounding)",
                      expected=round(computed, 3), actual=field.value)]
    return [_err(Category.CALCULATION, "CALC_FORMULA",
                 f"{field.calc_expr.strip()} = {round(computed, 3)}, but {field.value} was recorded",
                 expected=round(computed, 3), actual=field.value)]


# --- block-level rules ------------------------------------------------------

def rule_net_mass(block: Block) -> list[Flag]:
    tare, gross, net = block.role(Role.TARE_MASS), block.role(Role.GROSS_MASS), block.role(Role.NET_MASS)
    if not (tare and gross and net) or not all(isinstance(f.value, (int, float)) for f in (tare, gross, net)):
        return []
    expected = gross.value - tare.value
    if abs(net.value - expected) > _calc_tol(expected):
        net.add_flag(_err(Category.CALCULATION, "CALC_NET_MASS",
                          f"net_mass should equal gross - tare = {gross.value} - {tare.value} = {expected}",
                          expected=expected, actual=net.value))
    return []


def rule_volume(block: Block) -> list[Flag]:
    net, rho, vol = block.role(Role.NET_MASS), block.role(Role.DENSITY), block.role(Role.VOLUME)
    if not (net and rho and vol) or not all(isinstance(f.value, (int, float)) for f in (net, rho, vol)):
        return []
    expected = net.value * rho.value  # physics-based per host (V = m x rho with given rho)
    if abs(vol.value - expected) > _calc_tol(expected):
        vol.add_flag(_err(Category.CALCULATION, "CALC_VOLUME",
                          f"volume should equal net x rho = {net.value} x {rho.value} = {round(expected, 3)}",
                          expected=round(expected, 3), actual=vol.value))
    return []


def rule_four_eyes(block: Block) -> list[Flag]:
    # A page can carry several Bearbeitet/Gepruft pairs; pair them in field order
    # (the OpenAI reader puts all of a page's fields in one block).
    for proc, chk in zip(block.roles(Role.SIGNATURE_PROCESSED), block.roles(Role.SIGNATURE_CHECKED)):
        d_proc, _, k_proc = parse_signature(proc.value_raw)
        d_chk, _, k_chk = parse_signature(chk.value_raw)
        if d_proc and d_chk and d_chk < d_proc:
            chk.add_flag(_err(Category.FOUR_EYES, "4EYES_ORDER",
                              "Gepruft date is before Bearbeitet date (review must follow processing)",
                              expected=f">= {d_proc.isoformat()}", actual=d_chk.isoformat()))
        if k_proc and k_chk and k_proc.lower() == k_chk.lower():
            chk.add_flag(_err(Category.FOUR_EYES, "4EYES_DISTINCT",
                              "Bearbeitet and Gepruft signed by the same person",
                              expected="two different Kurzel", actual=k_chk))
    return []


def rule_end_after_start(block: Block) -> list[Flag]:
    start, end = block.role(Role.HOLD_START), block.role(Role.HOLD_END)
    if start and end and start.value and end.value and end.value <= start.value:
        end.add_flag(_err(Category.TEMPORAL, "TIME_END_AFTER_START",
                          "End timestamp is not after start", expected=f"> {start.value}", actual=str(end.value)))
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
    in the future — typically year misreads (e.g. p38 2026->2016, p17 ->2028)."""
    if not ref:
        return
    horizon = ref + timedelta(days=180)
    for f in doc.all_fields():
        if f.role not in _BATCH_DATE_ROLES:
            continue
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


def _within_one_edit(a: str, b: str) -> bool:
    """True if a and b are within Levenshtein distance 1 (tolerates OCR noise)."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        return sum(c1 != c2 for c1, c2 in zip(a, b)) <= 1
    short, long = (a, b) if la < lb else (b, a)
    i = j = edits = 0
    while i < len(short) and j < len(long):
        if short[i] == long[j]:
            i, j = i + 1, j + 1
        else:
            edits += 1
            if edits > 1:
                return False
            j += 1
    return True


def _registry_kuerzel(doc: Document) -> set[str]:
    """Kürzel registered in the personnel table (a field labelled 'Kürzel')."""
    reg: set[str] = set()
    for f in doc.all_fields():
        if (f.label_raw or "").strip().lower() == "kürzel" and f.value_raw:
            reg.add(f.value_raw.strip().lower())
    return reg


def rule_kuerzel_document(doc: Document) -> None:
    """Flag a signature Kürzel that isn't in the personnel list (Beteiligte Personen).
    Edit-distance-1 tolerance absorbs OCR noise, so only clearly-unregistered initials
    flag (warning — a human checks the original)."""
    registry = _registry_kuerzel(doc)
    if not registry:
        return
    for f in doc.all_fields():
        if f.role not in (Role.SIGNATURE_PROCESSED, Role.SIGNATURE_CHECKED):
            continue
        _, _, k = parse_signature(f.value_raw)
        if not k:
            continue
        if not any(_within_one_edit(k.lower(), r) for r in registry):
            f.add_flag(_warn(Category.FOUR_EYES, "KUERZEL_UNKNOWN",
                             f"Kuerzel '{k}' is not in the personnel list (Beteiligte Personen)",
                             expected="a registered Kuerzel", actual=k))


_XREF_RE = re.compile(r"kapitel\s*([0-9]+(?:\.[0-9]+)*)", re.I)


def _xref_differ(a, b) -> bool:
    if a is None or b is None:
        return False
    if isinstance(a, bool) or isinstance(b, bool):
        return a != b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) > max(0.5, abs(b) * 0.01)
    return a != b


def rule_xref_document(doc: Document) -> None:
    """Cross-reference (Übertrag): a field whose label carries a value from
    'Kapitel X' must equal the source field (same role) tagged with chapter X.
    Conservative — only fires on explicit 'Übertrag … Kapitel X' labels."""
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
        if _xref_differ(f.value, src.value):
            f.add_flag(_warn(Category.CROSS_REFERENCE, "XREF_MISMATCH",
                             f"carried value '{f.value}' != source (Kapitel {m.group(1)}) '{src.value}'",
                             expected=str(src.value), actual=str(f.value)))


# --- registries -------------------------------------------------------------

FIELD_RULES = [rule_date_format, rule_nks, rule_range, rule_formula]
BLOCK_RULES = [rule_net_mass, rule_volume, rule_four_eyes, rule_end_after_start]
