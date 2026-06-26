"""Validation rules. Each binds to field ROLES (never labels) and yields Flags.

See docs/VALIDATION_RULES.md. Two severities only: error | warning. Clean
fields produce no flag. This scaffold implements the high-value classes
(format, four-eyes, calculation, range, temporal); applicability / cross-
reference / outlier are wired as TODOs for Day 2.
"""
from __future__ import annotations

import re
from datetime import date

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


# --- registries -------------------------------------------------------------

FIELD_RULES = [rule_date_format, rule_nks, rule_range]
BLOCK_RULES = [rule_net_mass, rule_volume, rule_four_eyes, rule_end_after_start]
