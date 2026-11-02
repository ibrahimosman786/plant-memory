"""Base plant model: one fictional pumping station with two pumps, a tank, valves,
instruments, and one control panel. ~80 tags. Deterministic given a seed."""

from __future__ import annotations

import random
from dataclasses import dataclass, field, asdict
from decimal import Decimal


@dataclass
class Equipment:
    tag: str
    type: str
    description: str
    location: str
    manufacturer: str | None = None
    model: str | None = None
    service: str | None = None
    attributes: dict = field(default_factory=dict)


@dataclass
class IOPoint:
    tag: str
    signal: str  # AI, AO, DI, DO
    panel: str
    card: str
    channel: int
    range_lo: Decimal | None
    range_hi: Decimal | None
    unit: str | None
    wire: str
    terminal: str


@dataclass
class Relationship:
    source: str
    target: str
    type: str  # measures, signals_to, wired_to, controls, powers, installed_in, part_of


@dataclass
class Plant:
    name: str
    equipment: list[Equipment]
    io: list[IOPoint]
    relationships: list[Relationship]
    narrative_sections: list[tuple[str, str]]
    pid_layout: dict  # tag -> (x, y, symbol)
    pid_lines: list[tuple[str, str]]

    def by_tag(self) -> dict[str, Equipment]:
        return {e.tag: e for e in self.equipment}

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "equipment": [asdict(e) for e in self.equipment],
            "io": [
                {**asdict(p), "range_lo": _s(p.range_lo), "range_hi": _s(p.range_hi)}
                for p in self.io
            ],
            "relationships": [asdict(r) for r in self.relationships],
            "pid_lines": self.pid_lines,
        }


def _s(d: Decimal | None) -> str | None:
    return None if d is None else str(d)


VENDORS = ["Northfield Instruments", "Kesler Controls", "Albion Valve Co.", "Brightwater Pumps", "Orrin Automation"]


def build_plant(seed: int, unit_system: str = "metric") -> Plant:
    """Return the canonical pumping station. `unit_system` affects instrument units only."""
    rnd = random.Random(seed)
    eq: list[Equipment] = []
    io: list[IOPoint] = []
    rel: list[Relationship] = []

    pressure_unit = "kPa" if unit_system == "metric" else "psi"
    pressure_hi = Decimal("1600") if unit_system == "metric" else Decimal("232")
    level_unit = "m"
    flow_unit = "m3/h"
    temp_unit = "degC"

    # Panel and PLC
    eq.append(Equipment("CP-101", "control_panel", "Pump station control panel", "Electrical room", "Kesler Controls", "KC-ENC-2000", attributes={"enclosure": "NEMA 12", "supply": "120 VAC"}))
    eq.append(Equipment("PLC-101", "plc", "Station PLC, rack 0", "CP-101", "Kesler Controls", "KC-CPU-540", attributes={"firmware": "4.12", "memory_kb": "2048"}))
    cards = [
        ("AI-01", "analog_input_card", "KC-AI-8", 8, "AI"),
        ("AI-02", "analog_input_card", "KC-AI-8", 8, "AI"),
        ("AO-01", "analog_output_card", "KC-AO-4", 4, "AO"),
        ("DI-01", "digital_input_card", "KC-DI-16", 16, "DI"),
        ("DI-02", "digital_input_card", "KC-DI-16", 16, "DI"),
        ("DO-01", "digital_output_card", "KC-DO-16", 16, "DO"),
    ]
    for ctag, ctype, model, chans, _sig in cards:
        eq.append(Equipment(ctag, ctype, f"{model} I/O card", "CP-101 / rack 0", "Kesler Controls", model, attributes={"channels": str(chans)}))
        rel.append(Relationship(ctag, "PLC-101", "part_of"))
        rel.append(Relationship(ctag, "CP-101", "installed_in"))
    eq.append(Equipment("PS-101", "power_supply", "24 VDC panel power supply", "CP-101", "Kesler Controls", "KC-PS-240", attributes={"output": "24 VDC 10 A"}))
    rel.append(Relationship("PS-101", "CP-101", "installed_in"))
    eq.append(Equipment("HMI-101", "hmi", "Panel-mounted operator interface", "CP-101 door", "Kesler Controls", "KC-HMI-10"))
    rel.append(Relationship("HMI-101", "PLC-101", "signals_to"))
    eq.append(Equipment("UPS-101", "ups", "Panel UPS", "Electrical room", "Orrin Automation", "OA-UPS-1500"))
    rel.append(Relationship("UPS-101", "CP-101", "powers"))

    # Process equipment
    eq.append(Equipment("T-101", "tank", "Raw water supply tank", "Tank farm", "Albion Valve Co.", None, service="Raw water", attributes={"volume_m3": "250"}))
    for suffix in ("A", "B"):
        eq.append(Equipment(f"P-101{suffix}", "pump", f"Transfer pump {suffix} (centrifugal)", "Pump house", "Brightwater Pumps", "BW-CX-150", service="Raw water transfer", attributes={"rated_flow_m3h": "120", "rated_head_m": "45"}))
        eq.append(Equipment(f"M-101{suffix}", "motor", f"Pump {suffix} motor", "Pump house", "Brightwater Pumps", "BW-M-37", attributes={"power_kw": "37", "voltage": "480 VAC"}))
        eq.append(Equipment(f"VFD-101{suffix}", "vfd", f"Pump {suffix} variable frequency drive", "MCC room", "Orrin Automation", "OA-VFD-45", attributes={"rating_kw": "45", "comm": "Modbus TCP"}))
        rel.append(Relationship(f"M-101{suffix}", f"P-101{suffix}", "powers"))
        rel.append(Relationship(f"VFD-101{suffix}", f"M-101{suffix}", "controls"))
        rel.append(Relationship("PLC-101", f"VFD-101{suffix}", "controls"))

    valves = [
        ("XV-101", "on_off_valve", "Tank outlet isolation valve", "Tank farm"),
        ("XV-102A", "on_off_valve", "Pump A suction valve", "Pump house"),
        ("XV-102B", "on_off_valve", "Pump B suction valve", "Pump house"),
        ("XV-103A", "on_off_valve", "Pump A discharge valve", "Pump house"),
        ("XV-103B", "on_off_valve", "Pump B discharge valve", "Pump house"),
        ("FCV-104", "control_valve", "Discharge flow control valve", "Pump house"),
        ("PSV-105", "relief_valve", "Discharge header relief valve", "Pump house"),
        ("HV-106", "manual_valve", "Header drain valve", "Pump house"),
    ]
    for tag, t, d, loc in valves:
        eq.append(Equipment(tag, t, d, loc, "Albion Valve Co.", "AV-" + tag.split("-")[1]))

    # Instruments: (tag, type, description, location, signal, card, lo, hi, unit, measured_equipment)
    instruments = [
        ("LT-101", "level_transmitter", "Tank T-101 level", "Tank farm", "AI", "AI-01", Decimal("0"), Decimal("8"), level_unit, "T-101"),
        ("LSH-101", "level_switch", "Tank T-101 high level switch", "Tank farm", "DI", "DI-01", None, None, None, "T-101"),
        ("LSL-101", "level_switch", "Tank T-101 low level switch", "Tank farm", "DI", "DI-01", None, None, None, "T-101"),
        ("PT-102A", "pressure_transmitter", "Pump A suction pressure", "Pump house", "AI", "AI-01", Decimal("0"), pressure_hi / 4, pressure_unit, "P-101A"),
        ("PT-102B", "pressure_transmitter", "Pump B suction pressure", "Pump house", "AI", "AI-01", Decimal("0"), pressure_hi / 4, pressure_unit, "P-101B"),
        ("PT-103A", "pressure_transmitter", "Pump A discharge pressure", "Pump house", "AI", "AI-01", Decimal("0"), pressure_hi, pressure_unit, "P-101A"),
        ("PT-103B", "pressure_transmitter", "Pump B discharge pressure", "Pump house", "AI", "AI-01", Decimal("0"), pressure_hi, pressure_unit, "P-101B"),
        ("PT-104", "pressure_transmitter", "Discharge header pressure", "Pump house", "AI", "AI-01", Decimal("0"), pressure_hi, pressure_unit, "FCV-104"),
        ("FT-104", "flow_transmitter", "Discharge header flow", "Pump house", "AI", "AI-01", Decimal("0"), Decimal("300"), flow_unit, "FCV-104"),
        ("TT-101A", "temperature_transmitter", "Pump A bearing temperature", "Pump house", "AI", "AI-02", Decimal("0"), Decimal("150"), temp_unit, "P-101A"),
        ("TT-101B", "temperature_transmitter", "Pump B bearing temperature", "Pump house", "AI", "AI-02", Decimal("0"), Decimal("150"), temp_unit, "P-101B"),
        ("VT-101A", "vibration_transmitter", "Pump A vibration", "Pump house", "AI", "AI-02", Decimal("0"), Decimal("25"), "mm/s", "P-101A"),
        ("VT-101B", "vibration_transmitter", "Pump B vibration", "Pump house", "AI", "AI-02", Decimal("0"), Decimal("25"), "mm/s", "P-101B"),
        ("TT-102", "temperature_transmitter", "Raw water temperature", "Tank farm", "AI", "AI-02", Decimal("-20"), Decimal("60"), temp_unit, "T-101"),
        ("AT-105", "analyzer", "Header turbidity analyzer", "Pump house", "AI", "AI-02", Decimal("0"), Decimal("100"), "NTU", "FCV-104"),
    ]
    ai_counter: dict[str, int] = {}
    di_counter: dict[str, int] = {}
    do_counter: dict[str, int] = {}
    ao_counter: dict[str, int] = {}

    def next_ch(counter: dict[str, int], card: str) -> int:
        counter[card] = counter.get(card, 0) + 1
        return counter[card]

    for tag, t, d, loc, sig, card, lo, hi, unit, measures in instruments:
        attrs = {}
        if lo is not None:
            attrs = {"range_lo": str(lo), "range_hi": str(hi), "unit": unit, "signal": "4-20 mA", "power": "24 VDC loop"}
        eq.append(Equipment(tag, t, d, loc, "Northfield Instruments", "NI-" + t.split("_")[0].upper()[:3] + "-" + str(rnd.randint(100, 999)), attributes=attrs))
        rel.append(Relationship(tag, measures, "measures"))
        rel.append(Relationship(tag, card, "wired_to"))
        counter = ai_counter if sig == "AI" else di_counter
        ch = next_ch(counter, card)
        io.append(IOPoint(tag, sig, "CP-101", card, ch, lo, hi, unit, f"W-{card}-{ch:02d}", f"TB{card[-1]}-{ch*2-1}/{ch*2}"))

    # Valve I/O: position switches and solenoids
    for tag, t, _d, _loc in valves:
        if t == "on_off_valve":
            for pos in ("ZSO", "ZSC"):
                num = tag.split("-")[1]
                stag = f"{pos}-{num}"
                eq.append(Equipment(stag, "position_switch", f"{tag} {'open' if pos=='ZSO' else 'closed'} limit switch", "Pump house" if "102" in num or "103" in num else "Tank farm", "Albion Valve Co.", "AV-LS-2"))
                rel.append(Relationship(stag, tag, "measures"))
                card = "DI-02"
                ch = next_ch(di_counter, card)
                rel.append(Relationship(stag, card, "wired_to"))
                io.append(IOPoint(stag, "DI", "CP-101", card, ch, None, None, None, f"W-{card}-{ch:02d}", f"TB2-{ch}"))
            num = tag.split("-")[1]
            ytag = f"XY-{num}"
            eq.append(Equipment(ytag, "solenoid", f"{tag} solenoid", "Pump house", "Albion Valve Co.", "AV-SOV-24"))
            rel.append(Relationship(ytag, tag, "controls"))
            card = "DO-01"
            ch = next_ch(do_counter, card)
            rel.append(Relationship(ytag, card, "wired_to"))
            io.append(IOPoint(ytag, "DO", "CP-101", card, ch, None, None, None, f"W-{card}-{ch:02d}", f"TB3-{ch}"))
        elif t == "control_valve":
            ztag = "ZT-104"
            eq.append(Equipment(ztag, "position_transmitter", "FCV-104 position feedback", "Pump house", "Albion Valve Co.", "AV-ZT-1", attributes={"range_lo": "0", "range_hi": "100", "unit": "%", "signal": "4-20 mA"}))
            rel.append(Relationship(ztag, tag, "measures"))
            ch = next_ch(ai_counter, "AI-02")
            rel.append(Relationship(ztag, "AI-02", "wired_to"))
            io.append(IOPoint(ztag, "AI", "CP-101", "AI-02", ch, Decimal("0"), Decimal("100"), "%", f"W-AI-02-{ch:02d}", f"TB2-{ch}"))
            ytag = "FY-104"
            eq.append(Equipment(ytag, "i_p_positioner", "FCV-104 positioner", "Pump house", "Albion Valve Co.", "AV-POS-4"))
            rel.append(Relationship(ytag, tag, "controls"))
            ch = next_ch(ao_counter, "AO-01")
            rel.append(Relationship(ytag, "AO-01", "wired_to"))
            io.append(IOPoint(ytag, "AO", "CP-101", "AO-01", ch, Decimal("0"), Decimal("100"), "%", f"W-AO-01-{ch:02d}", f"TB4-{ch}"))

    # Pump run/fault/speed signals
    for suffix in ("A", "B"):
        for sig, pfx, desc, card, counter in (
            ("DI", "YS", "run status", "DI-01", di_counter),
            ("DI", "YA", "drive fault", "DI-01", di_counter),
            ("DO", "HS", "start command", "DO-01", do_counter),
            ("AO", "SC", "speed reference", "AO-01", ao_counter),
        ):
            stag = f"{pfx}-101{suffix}"
            eq.append(Equipment(stag, "signal_point", f"Pump {suffix} {desc}", "MCC room", "Orrin Automation", None))
            rel.append(Relationship(stag, f"VFD-101{suffix}", "signals_to" if sig in ("DO", "AO") else "measures"))
            ch = next_ch(counter, card)
            rel.append(Relationship(stag, card, "wired_to"))
            lo, hi, unit = (Decimal("0"), Decimal("100"), "%") if sig == "AO" else (None, None, None)
            io.append(IOPoint(stag, sig, "CP-101", card, ch, lo, hi, unit, f"W-{card}-{ch:02d}", f"TB5-{ch}"))

    # Process lines for P&ID
    pid_lines = [
        ("T-101", "XV-101"), ("XV-101", "XV-102A"), ("XV-101", "XV-102B"),
        ("XV-102A", "P-101A"), ("XV-102B", "P-101B"),
        ("P-101A", "XV-103A"), ("P-101B", "XV-103B"),
        ("XV-103A", "FCV-104"), ("XV-103B", "FCV-104"), ("FCV-104", "PSV-105"), ("FCV-104", "HV-106"),
    ]
    pid_layout = {
        "T-101": (80, 300, "tank"), "XV-101": (180, 300, "valve"),
        "XV-102A": (260, 360, "valve"), "XV-102B": (260, 240, "valve"),
        "P-101A": (340, 360, "pump"), "P-101B": (340, 240, "pump"),
        "XV-103A": (420, 360, "valve"), "XV-103B": (420, 240, "valve"),
        "FCV-104": (520, 300, "cvalve"), "PSV-105": (600, 360, "psv"), "HV-106": (600, 240, "valve"),
        "LT-101": (80, 380, "inst"), "PT-102A": (300, 400, "inst"), "PT-102B": (300, 200, "inst"),
        "PT-103A": (380, 400, "inst"), "PT-103B": (380, 200, "inst"), "PT-104": (480, 340, "inst"),
        "FT-104": (480, 260, "inst"), "TT-102": (120, 380, "inst"), "AT-105": (560, 260, "inst"),
    }

    narrative = [
        ("1. Purpose", "This narrative describes the control of raw water transfer from tank T-101 through pumps P-101A and P-101B to the discharge header. Control is executed in PLC-101 located in control panel CP-101."),
        ("2. Level control", f"Tank level LT-101 ({level_unit}) is the primary permissive. Pumps shall stop when LT-101 falls below the low-low setpoint or when LSL-101 is active. LSH-101 raises a high-level alarm on HMI-101."),
        ("3. Pump sequencing", "Pumps operate in duty/standby. The duty pump is selected on HMI-101. Start permissives: suction valve XV-102A/XV-102B open (ZSO-102A/ZSO-102B), suction pressure PT-102A/PT-102B above the minimum, and no drive fault YA-101A/YA-101B. The PLC issues HS-101A/HS-101B to the drive and modulates speed via SC-101A/SC-101B."),
        ("4. Discharge pressure control", f"Header pressure PT-104 ({pressure_unit}) is controlled by modulating pump speed. FCV-104 trims flow measured by FT-104 ({flow_unit}); position feedback is ZT-104 and the positioner is FY-104. PSV-105 provides overpressure protection and is not controlled."),
        ("5. Protection", "Bearing temperature TT-101A/TT-101B above the high-high setpoint or vibration VT-101A/VT-101B above the trip setpoint trips the corresponding pump. The discharge valve XV-103A/XV-103B closes on pump stop."),
        ("6. Instrument ranges", f"Pressure transmitters PT-103A, PT-103B, and PT-104 are ranged 0 to {pressure_hi} {pressure_unit}. Suction transmitters PT-102A/PT-102B are ranged 0 to {pressure_hi/4} {pressure_unit}. Flow FT-104 is ranged 0 to 300 {flow_unit}. Bearing temperatures are ranged 0 to 150 {temp_unit}."),
        ("7. Power and panel", "CP-101 is supplied at 120 VAC from UPS-101. PS-101 provides 24 VDC loop power. The I/O is housed in rack 0 of PLC-101: AI-01, AI-02, AO-01, DI-01, DI-02, DO-01."),
    ]

    return Plant("Fictional Raw Water Pumping Station", eq, io, rel, narrative, pid_layout, pid_lines)
