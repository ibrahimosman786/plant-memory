"""Document kind classification from filename, headers, and first text spans."""

from __future__ import annotations

from .parsers import ParsedDocument, EQUIPMENT_HEADERS, IO_HEADERS, CATALOGUE_HEADERS, RATES_HEADERS, map_headers

KINDS = ("equipment_list", "io_list", "narrative", "datasheet", "pid", "config_export", "catalogue", "rates", "note", "other")


def classify(filename: str, parsed: ParsedDocument, declared: str | None = None) -> str:
    if declared and declared in KINDS:
        return declared
    name = filename.lower()
    if parsed.format == "config_csv":
        return "config_export"
    if parsed.format == "pid":
        return "pid"
    if parsed.format in ("csv", "xlsx"):
        headers = parsed.meta.get("headers") or []
        if parsed.format == "xlsx":
            sheets = parsed.meta.get("sheets", {})
            headers = [h for s in sheets.values() for h in s["headers"]]
        if map_headers(headers, CATALOGUE_HEADERS).values() and "part_number" in [h.lower() for h in headers]:
            return "catalogue"
        if "rate_code" in [h.lower() for h in headers]:
            return "rates"
        io_fields = set(map_headers(headers, IO_HEADERS).values())
        eq_fields = set(map_headers(headers, EQUIPMENT_HEADERS).values())
        if {"card", "channel"} & io_fields or {"range_lo", "range_hi"} <= io_fields:
            return "io_list"
        if "tag" in eq_fields and ({"type", "description"} & eq_fields):
            return "equipment_list"
        return "other"
    if parsed.format == "pdf":
        head = " ".join(sp.text for sp in parsed.spans[:5]).upper()
        if "DATASHEET" in head or "datasheet" in name:
            return "datasheet"
        if "P&ID" in head or "pid" in name:
            return "pid"
        if "NARRATIVE" in head:
            return "narrative"
        return "other"
    if parsed.format == "docx":
        head = " ".join(sp.text for sp in parsed.spans[:3]).upper()
        return "narrative" if "NARRATIVE" in head or "narrative" in name else "other"
    if parsed.format == "text":
        return "note"
    return "other"
