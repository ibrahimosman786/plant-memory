"""Tag and unit normalization.

Tags: ISA-style `PT-103A` is canonical. `pt 103 a`, `PT_103A`, `PT103A` normalize to `PT-103A`.
Loose spellings are recorded as such; ambiguity (one loose mention matching several tags) is a
finding, never a silent pick.

Units: Pint converts to a canonical unit per quantity family so ranges can be compared.
Unknown units pass through unchanged and comparisons on them are reported as `unresolved`.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from functools import lru_cache

TAG_RE = re.compile(r"(?<![A-Z0-9])([A-Z]{1,4})[\s\-_]?(\d{2,4})\s?([A-Z]{0,2}\d?)(?![A-Z0-9])")
LOOSE_TAG_RE = re.compile(r"\b([A-Za-z]{1,4})[\s\-_]*(\d{2,4})[\s\-_]*([A-Za-z]{0,2}\d?)\b")

# Prefixes that look like tags but are not equipment (dates, part numbers, revisions, sizes).
NON_TAG_PREFIXES = {"REV", "NEMA", "ISO", "IEC", "NPT", "VAC", "VDC", "KPA", "PSI", "HART", "MA", "TB", "W", "KC", "NI", "AV", "BW", "OA", "NTU", "CAD", "USD", "MM", "CH", "SLOT"}


def normalize_tag(raw: str) -> str | None:
    if not raw:
        return None
    m = LOOSE_TAG_RE.fullmatch(raw.strip())
    if not m:
        return None
    prefix, num, suffix = m.group(1).upper(), m.group(2), m.group(3).upper()
    if prefix in NON_TAG_PREFIXES:
        return None
    return f"{prefix}-{num}{suffix}"


def find_tags(text: str) -> list[tuple[str, str]]:
    """Return (raw_mention, normalized_tag) pairs found in prose."""
    out: list[tuple[str, str]] = []
    for m in TAG_RE.finditer(text):
        prefix = m.group(1)
        if prefix in NON_TAG_PREFIXES:
            continue
        raw = m.group(0)
        norm = f"{prefix}-{m.group(2)}{m.group(3)}"
        out.append((raw, norm))
    return out


def is_loose_mention(raw: str, normalized: str) -> bool:
    return raw.strip().upper() != normalized


# ----------------------------------------------------------------------------- units

CANONICAL_BY_DIMENSION = {
    "[mass] / [length] / [time] ** 2": "kPa",  # pressure
    "[temperature]": "degC",
    "[length] ** 3 / [time]": "m**3/h",  # volumetric flow
    "[length]": "m",
    "[length] / [time]": "mm/s",  # vibration velocity
    "[mass] * [length] ** 2 / [time] ** 3": "kW",
    "[mass] * [length] ** 2 / [current] / [time] ** 3": "V",
    "[current]": "mA",
    "dimensionless": "%",
}

UNIT_ALIASES = {
    "degc": "degC", "°c": "degC", "c": "degC", "deg c": "degC",
    "degf": "degF", "°f": "degF", "f": "degF",
    "m3/h": "m**3/h", "m³/h": "m**3/h", "m3/hr": "m**3/h",
    "kpa": "kPa", "kpag": "kPa", "psig": "psi", "psi": "psi", "bar": "bar", "barg": "bar", "mbar": "mbar", "inh2o": "inH2O",
    "%": "percent", "pct": "percent",
    "ma": "mA", "vdc": "V", "vac": "V",
    "ntu": "NTU", "ph": "pH",
    "mm/s": "mm/s", "m": "m", "mm": "mm", "kw": "kW", "hp": "hp",
}


@lru_cache
def _ureg():
    import pint

    ureg = pint.UnitRegistry()
    ureg.define("NTU = [turbidity]")
    ureg.define("pH = [acidity]")
    ureg.define("percent = 0.01 * count = %")
    return ureg


def canonicalize(value: str | Decimal | None, unit: str | None) -> tuple[Decimal | None, str | None, bool]:
    """Return (canonical_value, canonical_unit, converted?). Unknown units return the input unchanged."""
    if value is None or value == "":
        return None, unit, False
    try:
        dec = Decimal(str(value))
    except InvalidOperation:
        return None, unit, False
    if not unit:
        return dec, None, False
    key = unit.strip().lower()
    alias = UNIT_ALIASES.get(key, unit.strip())
    try:
        ureg = _ureg()
        q = ureg.Quantity(float(dec), alias)
        dim = str(q.dimensionality)
        if dim == "[turbidity]" or dim == "[acidity]":
            return dec, alias, False
        target = CANONICAL_BY_DIMENSION.get(dim)
        if target is None:
            return dec, alias, False
        if target == "%":
            return dec, "%", False
        if target == "degC" and alias != "degC":
            converted = q.to("degC").magnitude
        else:
            converted = q.to(target).magnitude
        out_unit = "m3/h" if target == "m**3/h" else target
        return Decimal(str(round(converted, 6))), out_unit, alias != target
    except Exception:
        return dec, unit, False


def units_compatible(unit_a: str | None, unit_b: str | None) -> bool | None:
    """True/False when both units are known; None when either is unknown."""
    if not unit_a or not unit_b:
        return None
    try:
        ureg = _ureg()
        a = ureg.Unit(UNIT_ALIASES.get(unit_a.strip().lower(), unit_a.strip()))
        b = ureg.Unit(UNIT_ALIASES.get(unit_b.strip().lower(), unit_b.strip()))
        return a.dimensionality == b.dimensionality
    except Exception:
        return None


def to_decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except InvalidOperation:
        return None
