"""Intermediate representation of one project variant before serialization."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from datetime import date

from .plant import Plant, build_plant


@dataclass
class Datasheet:
    tag: str
    manufacturer: str
    model: str
    attributes: dict[str, str]  # attribute -> "value unit" style strings kept separate below
    range_lo: str | None
    range_hi: str | None
    unit: str | None
    notes: list[str] = field(default_factory=list)
    scanned: bool = False  # render as image-only PDF
    scan_damage: float = 0.0  # fraction of lines dropped from the image


@dataclass
class ConfigRow:
    tag: str
    address: str
    card: str
    channel: int
    scale_lo: str | None
    scale_hi: str | None
    eng_unit: str | None
    alarm_lo: str | None
    alarm_hi: str | None
    description: str


@dataclass
class CataloguePart:
    part_number: str
    description: str
    category: str
    attributes: dict[str, str]
    unit_price: str | None
    currency: str
    effective_date: str
    source: str


@dataclass
class Rate:
    rate_code: str
    description: str
    unit: str
    rate: str
    currency: str
    effective_date: str


@dataclass
class SeededFault:
    kind: str
    subject: list[str]
    detail: str
    expected_finding_type: str | None
    expected_severity: str | None


@dataclass
class Bundle:
    variant_id: str
    family: str  # "dev" or "heldout"
    template: str  # column naming style: "standard" or "legacy"
    plant: Plant
    equipment_rows: list[dict]
    io_rows: list[dict]
    narrative: list[tuple[str, str]]
    datasheets: list[Datasheet]
    config_rows: list[ConfigRow]
    catalogue: list[CataloguePart]
    rates: list[Rate]
    faults: list[SeededFault] = field(default_factory=list)
    revision_label: str = "A"
    extra_documents: list[tuple[str, str]] = field(default_factory=list)  # (filename, text) for odd docs
    pid_extra_tags: list[tuple[str, int, int]] = field(default_factory=list)


def base_bundle(variant_id: str, family: str, template: str, seed: int, unit_system: str) -> Bundle:
    plant = build_plant(seed, unit_system)
    eq_rows = []
    for e in plant.equipment:
        eq_rows.append({
            "tag": e.tag, "type": e.type, "description": e.description, "location": e.location,
            "manufacturer": e.manufacturer or "", "model": e.model or "", "service": e.service or "",
        })
    io_rows = []
    for p in plant.io:
        io_rows.append({
            "tag": p.tag, "signal": p.signal, "panel": p.panel, "card": p.card, "channel": p.channel,
            "range_lo": "" if p.range_lo is None else str(p.range_lo),
            "range_hi": "" if p.range_hi is None else str(p.range_hi),
            "unit": p.unit or "", "wire": p.wire, "terminal": p.terminal,
        })
    sheets = []
    for e in plant.equipment:
        if "range_lo" in e.attributes:
            sheets.append(Datasheet(
                e.tag, e.manufacturer or "", e.model or "", dict(e.attributes),
                e.attributes["range_lo"], e.attributes["range_hi"], e.attributes["unit"],
                notes=["Loop powered 24 VDC, 4-20 mA HART output."],
            ))
    cfg = []
    for p in plant.io:
        addr = f"{p.card}:{p.channel}"
        lo = None if p.range_lo is None else str(p.range_lo)
        hi = None if p.range_hi is None else str(p.range_hi)
        alo = None
        ahi = None
        if p.signal == "AI" and p.range_hi is not None:
            ahi = str((p.range_hi * Decimal("0.9")).quantize(Decimal("0.1")))
            alo = str((p.range_hi * Decimal("0.05")).quantize(Decimal("0.1")))
        desc = next((e.description for e in plant.equipment if e.tag == p.tag), "")
        cfg.append(ConfigRow(p.tag, addr, p.card, p.channel, lo, hi, p.unit, alo, ahi, desc))

    eff = date(2026, 6, 1).isoformat()
    catalogue = [
        CataloguePart("KC-CPU-740", "Kesler KC-CPU-740 processor (replacement for KC-CPU-540)", "plc", {"memory_kb": "8192", "firmware": "7.1", "backplane": "KC rack 0 compatible"}, "6850.00", "CAD", eff, "Fictional vendor price list 2026-06"),
        CataloguePart("KC-AI-8H", "Kesler 8-channel analog input card, HART", "io_card", {"channels": "8", "signal": "4-20 mA"}, "1420.00", "CAD", eff, "Fictional vendor price list 2026-06"),
        CataloguePart("KC-AO-4", "Kesler 4-channel analog output card", "io_card", {"channels": "4"}, "1190.00", "CAD", eff, "Fictional vendor price list 2026-06"),
        CataloguePart("KC-DI-16", "Kesler 16-channel digital input card", "io_card", {"channels": "16"}, "640.00", "CAD", eff, "Fictional vendor price list 2026-06"),
        CataloguePart("KC-DO-16", "Kesler 16-channel digital output card", "io_card", {"channels": "16"}, "690.00", "CAD", eff, "Fictional vendor price list 2026-06"),
        CataloguePart("KC-PS-240", "Kesler 24 VDC 10 A power supply", "power_supply", {"output": "24 VDC 10 A"}, "410.00", "CAD", eff, "Fictional vendor price list 2026-06"),
        CataloguePart("KC-HMI-15", "Kesler 15-inch operator interface", "hmi", {"size_in": "15"}, "3250.00", "CAD", eff, "Fictional vendor price list 2026-06"),
        CataloguePart("KC-ENC-2000", "Kesler NEMA 12 enclosure 2000x800x500", "enclosure", {"enclosure": "NEMA 12"}, "2980.00", "CAD", eff, "Fictional vendor price list 2026-06"),
        CataloguePart("KC-RACK-0", "Kesler rack 0 backplane, 8 slot", "plc", {"slots": "8"}, "880.00", "CAD", eff, "Fictional vendor price list 2026-06"),
        CataloguePart("NI-PT-500", "Northfield pressure transmitter, 0-1600 kPa", "instrument", {"range_hi": "1600", "unit": "kPa"}, "1875.00", "CAD", eff, "Fictional vendor price list 2026-06"),
        CataloguePart("GEN-TERM-BLK", "Terminal block, 2-level", "wiring", {}, "4.20", "CAD", eff, "Fictional distributor list 2026-06"),
        CataloguePart("GEN-CABLE-PAIR", "Instrument cable, 1 pair shielded, per metre", "wiring", {}, "2.35", "CAD", eff, "Fictional distributor list 2026-06"),
        CataloguePart("OA-UPS-1500", "Orrin 1500 VA UPS", "ups", {}, None, "CAD", eff, "Fictional vendor list 2026-06 (price on request)"),
    ]
    rates = [
        Rate("ENG-SR", "Senior controls engineer", "hour", "185.00", "CAD", eff),
        Rate("ENG-INT", "Intermediate controls engineer", "hour", "145.00", "CAD", eff),
        Rate("TECH", "Instrumentation technician", "hour", "115.00", "CAD", eff),
        Rate("DOC", "Documentation specialist", "hour", "95.00", "CAD", eff),
        Rate("SIM", "Simulator test bench", "day", "900.00", "CAD", eff),
    ]
    return Bundle(variant_id, family, template, plant, eq_rows, io_rows, list(plant.narrative_sections), sheets, cfg, catalogue, rates)
