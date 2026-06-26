"""Semantic field roles.

Validation rules bind to these roles, NEVER to the literal German label — so a
field reading `m_Tara`, `Tara` or `Leergewicht` all resolve to `TARE_MASS` and
the same rules apply. Role assignment happens in `pipeline/normalize.py` using
context (position in block, printed formula, units, neighbours).
"""
from __future__ import annotations


class Role:
    TARE_MASS = "tare_mass"
    GROSS_MASS = "gross_mass"
    NET_MASS = "net_mass"
    VOLUME = "volume"
    DENSITY = "density"                 # ρ, given on the form
    CONCENTRATION = "concentration"     # c, given input (not computed)
    HOLD_START = "hold_start"
    HOLD_END = "hold_end"
    HOLD_DURATION = "hold_duration"
    TEMPERATURE_SETPOINT = "temperature_setpoint"
    CALC_INPUT = "calc_input"
    CALC_RESULT = "calc_result"
    SIGNATURE_PROCESSED = "signature_processed"   # Bearbeitet
    SIGNATURE_CHECKED = "signature_checked"        # Geprüft
    GATE = "gate"
    CHECKBOX_SINGLE = "checkbox_single"
    CHECKBOX_BOOL = "checkbox_bool"
    SAMPLE_ID = "sample_id"
    EQUIPMENT_ID = "equipment_id"
    DEVIATION_REF = "deviation_ref"
    TEXT = "text"


# Roles whose value is numeric (used by stats / outlier scoring).
NUMERIC_ROLES = {
    Role.TARE_MASS, Role.GROSS_MASS, Role.NET_MASS, Role.VOLUME,
    Role.DENSITY, Role.CONCENTRATION, Role.HOLD_DURATION,
    Role.CALC_INPUT, Role.CALC_RESULT,
}
