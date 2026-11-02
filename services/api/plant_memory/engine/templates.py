"""Versioned work-scope and checklist templates.

Labour hours are editable, versioned ASSUMPTIONS (assumption_status="assumed") until calibrated
against actual projects. Each labour line carries low/base/high hours so the estimator can
produce scenario totals from stated input ranges — not statistical confidence intervals.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import TEMPLATES_VERSION


@dataclass
class LabourSpec:
    rate_code: str
    description: str
    hours_low: float
    hours_base: float
    hours_high: float
    per: str = "job"  # job | io_point | instrument | card
    unit: str = "hour"


@dataclass
class PartSpec:
    description: str
    quantity_per: str = "job"  # job | io_point | card | instrument
    quantity: float = 1
    part_number: str | None = None
    category: str | None = None
    match_attributes: dict = field(default_factory=dict)
    reuse_candidate: bool = False  # existing equipment may be reused; shown as candidate, not assumed
    optional: bool = False  # priced if possible but never summed into the base subtotal


@dataclass
class WorkTemplate:
    id: str
    title: str
    description: str
    applies_to_types: tuple[str, ...]
    labour: list[LabourSpec]
    parts: list[PartSpec]
    checklist_templates: tuple[str, ...]
    version: str = TEMPLATES_VERSION


@dataclass
class ChecklistTemplate:
    id: str
    requirement_pattern: str  # text describing the requirement source
    proposed_verification: str
    expected_outcome_from: str  # "requirement" (needs cited evidence) | "none"
    per: str = "job"  # job | io_point | instrument | finding


WORK_TEMPLATES: dict[str, WorkTemplate] = {
    "WT-PANEL-REPLACE": WorkTemplate(
        "WT-PANEL-REPLACE", "Control panel / PLC replacement",
        "Replace the panel processor and migrate I/O, program, and documentation. Existing I/O cards, enclosure, and wiring are reuse candidates pending verification.",
        ("control_panel", "plc"),
        labour=[
            LabourSpec("ENG-SR", "Engineering assessment and migration plan", 12, 16, 24),
            LabourSpec("ENG-INT", "Program migration and configuration", 16, 24, 40),
            LabourSpec("TECH", "I/O verification and loop checks", 0.4, 0.5, 0.75, per="io_point"),
            LabourSpec("DOC", "Documentation update (drawings, I/O list, narrative)", 6, 8, 12),
            LabourSpec("DOC", "Per-point documentation", 0.15, 0.25, 0.35, per="io_point"),
            LabourSpec("SIM", "Simulator factory acceptance test bench", 1, 2, 3, unit="day"),
            LabourSpec("ENG-INT", "Simulator FAT execution", 12, 16, 24),
            LabourSpec("TECH", "Site cut-over and commissioning", 16, 24, 32),
            LabourSpec("ENG-INT", "Site commissioning support", 12, 16, 24),
        ],
        parts=[
            PartSpec("Replacement processor", part_number="KC-CPU-740", category="plc"),
            PartSpec("Rack backplane", part_number="KC-RACK-0", category="plc", reuse_candidate=True),
            PartSpec("24 VDC power supply", part_number="KC-PS-240", category="power_supply", reuse_candidate=True),
            PartSpec("Existing I/O cards", quantity_per="card", category="io_card", reuse_candidate=True),
            PartSpec("Enclosure", part_number="KC-ENC-2000", category="enclosure", reuse_candidate=True),
            PartSpec("Terminal blocks (re-landing allowance)", quantity_per="io_point", quantity=2, part_number="GEN-TERM-BLK", category="wiring"),
            PartSpec("Panel UPS", part_number="OA-UPS-1500", category="ups", reuse_candidate=True),
            PartSpec("Operator interface upgrade (optional, commonly bundled with processor replacement)", part_number="KC-HMI-15", category="hmi", optional=True),
        ],
        checklist_templates=("CL-LOOP-CHECK", "CL-NARRATIVE-SIM", "CL-COMPAT", "CL-RANGE-VERIFY", "CL-SPARE-CAPACITY"),
    ),
    "WT-CARD-REPLACE": WorkTemplate(
        "WT-CARD-REPLACE", "I/O card replacement",
        "Replace one I/O card and re-verify every point wired to it.",
        ("analog_input_card", "analog_output_card", "digital_input_card", "digital_output_card"),
        labour=[
            LabourSpec("ENG-INT", "Configuration and address mapping", 2, 4, 6),
            LabourSpec("TECH", "Loop check per point", 0.5, 0.75, 1.0, per="io_point"),
            LabourSpec("DOC", "I/O list and drawing update", 1, 2, 3),
        ],
        parts=[PartSpec("Replacement I/O card", quantity_per="card", category="io_card")],
        checklist_templates=("CL-LOOP-CHECK", "CL-RANGE-VERIFY"),
    ),
    "WT-INSTRUMENT-REPLACE": WorkTemplate(
        "WT-INSTRUMENT-REPLACE", "Instrument replacement",
        "Replace a transmitter/analyzer like-for-range, reconfigure the input, and verify the loop.",
        ("pressure_transmitter", "level_transmitter", "flow_transmitter", "temperature_transmitter", "vibration_transmitter", "analyzer", "position_transmitter"),
        labour=[
            LabourSpec("TECH", "Remove, install, and calibrate", 3, 4, 6, per="instrument"),
            LabourSpec("ENG-INT", "Configure input scaling and alarms", 1, 2, 3, per="instrument"),
            LabourSpec("DOC", "Datasheet and loop drawing update", 0.5, 1, 1.5, per="instrument"),
        ],
        parts=[PartSpec("Replacement instrument", quantity_per="instrument", category="instrument")],
        checklist_templates=("CL-LOOP-CHECK", "CL-RANGE-VERIFY"),
    ),
    "WT-RERANGE": WorkTemplate(
        "WT-RERANGE", "Transmitter re-range",
        "Re-range an existing transmitter and update scaling, alarms, and records.",
        ("pressure_transmitter", "level_transmitter", "flow_transmitter", "temperature_transmitter"),
        labour=[
            LabourSpec("TECH", "Bench/field re-range and calibration", 1.5, 2, 3, per="instrument"),
            LabourSpec("ENG-INT", "Update scaling and alarm limits", 0.5, 1, 2, per="instrument"),
            LabourSpec("DOC", "Update datasheet, I/O list, config record", 0.5, 0.5, 1, per="instrument"),
        ],
        parts=[],
        checklist_templates=("CL-RANGE-VERIFY", "CL-LOOP-CHECK"),
    ),
    "WT-VFD-REPLACE": WorkTemplate(
        "WT-VFD-REPLACE", "Variable frequency drive replacement",
        "Replace a VFD, restore control/status signals, and verify the pump sequence.",
        ("vfd",),
        labour=[
            LabourSpec("TECH", "Remove/install drive and reconnect signals", 6, 8, 12),
            LabourSpec("ENG-INT", "Drive parameters and PLC interface", 6, 8, 12),
            LabourSpec("DOC", "Drawings and parameter record", 1, 2, 3),
        ],
        parts=[PartSpec("Replacement VFD", category="vfd")],
        checklist_templates=("CL-LOOP-CHECK", "CL-NARRATIVE-SIM"),
    ),
    "WT-VALVE-LIKE-FOR-LIKE": WorkTemplate(
        "WT-VALVE-LIKE-FOR-LIKE", "Like-for-like valve replacement",
        "Replace a valve with an identical unit; no control changes expected.",
        ("manual_valve", "on_off_valve", "control_valve", "relief_valve"),
        labour=[
            LabourSpec("TECH", "Mechanical replacement and leak check", 3, 4, 6),
            LabourSpec("DOC", "Record update", 0.25, 0.5, 1),
        ],
        parts=[PartSpec("Replacement valve", category="valve")],
        checklist_templates=("CL-LIKE-FOR-LIKE",),
    ),
    "WT-HMI-REPLACE": WorkTemplate(
        "WT-HMI-REPLACE", "Operator interface replacement",
        "Replace the panel HMI and migrate screens and alarm lists.",
        ("hmi",),
        labour=[
            LabourSpec("ENG-INT", "Screen and alarm migration", 8, 12, 20),
            LabourSpec("TECH", "Install and connect", 2, 4, 6),
            LabourSpec("DOC", "Operator documentation", 1, 2, 4),
        ],
        parts=[PartSpec("Replacement HMI", part_number="KC-HMI-15", category="hmi")],
        checklist_templates=("CL-NARRATIVE-SIM",),
    ),
    "WT-RECORD-CONFLICT": WorkTemplate(
        "WT-RECORD-CONFLICT", "Resolve record conflict",
        "Engineering effort to resolve a conflicting or missing record before design can proceed.",
        (),
        labour=[LabourSpec("ENG-INT", "Investigate and resolve record discrepancy", 0.5, 1, 2, per="finding")],
        parts=[],
        checklist_templates=("CL-RECORD-RESOLVED",),
    ),
    "WT-GENERIC": WorkTemplate(
        "WT-GENERIC", "Unclassified change",
        "The request did not map to a template; an engineering allowance is shown and must be replaced by a scoped estimate.",
        (),
        labour=[LabourSpec("ENG-SR", "Scoping allowance (to be replaced)", 4, 8, 16)],
        parts=[],
        checklist_templates=(),
    ),
}


CHECKLIST_TEMPLATES: dict[str, ChecklistTemplate] = {
    "CL-LOOP-CHECK": ChecklistTemplate("CL-LOOP-CHECK", "I/O point wired to affected hardware", "Loop check {tag}: inject/simulate at field end, confirm PLC value, alarm, and HMI indication.", "requirement", per="io_point"),
    "CL-RANGE-VERIFY": ChecklistTemplate("CL-RANGE-VERIFY", "Recorded instrument range", "Verify {tag} configured scaling equals the governing datasheet range at 0/50/100 %.", "requirement", per="instrument"),
    "CL-NARRATIVE-SIM": ChecklistTemplate("CL-NARRATIVE-SIM", "Control narrative section", "Simulate '{section}' on the test bench and confirm behaviour matches the narrative.", "requirement", per="narrative_section"),
    "CL-COMPAT": ChecklistTemplate("CL-COMPAT", "Compatibility claim", "Verify backplane/firmware compatibility of {subject} with existing I/O cards using vendor matrix and bench test; record firmware versions.", "none", per="finding"),
    "CL-SPARE-CAPACITY": ChecklistTemplate("CL-SPARE-CAPACITY", "Spare I/O capacity", "Count spare channels per card on site and update the panel schedule.", "none", per="job"),
    "CL-LIKE-FOR-LIKE": ChecklistTemplate("CL-LIKE-FOR-LIKE", "Like-for-like replacement", "Confirm replacement {tag} nameplate matches the recorded model and service; leak test after install.", "requirement", per="job"),
    "CL-RECORD-RESOLVED": ChecklistTemplate("CL-RECORD-RESOLVED", "Record discrepancy", "Confirm the engineer decision for '{title}' is reflected in all affected records.", "none", per="finding"),
}


def templates_for_types(types: set[str]) -> list[WorkTemplate]:
    out = []
    for t in WORK_TEMPLATES.values():
        if t.applies_to_types and set(t.applies_to_types) & types:
            out.append(t)
    return out
