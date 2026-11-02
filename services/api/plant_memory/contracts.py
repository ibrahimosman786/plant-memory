"""Pydantic mirrors of packages/contracts/schemas. The JSON schemas are the source of truth;
tests/test_contracts.py checks these models validate against them."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ToolStatus = Literal["complete", "partial", "blocked", "failed"]


class Unresolved(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str
    subject: str | None = None


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: ToolStatus
    snapshot_id: str
    data: dict[str, Any]
    evidence_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    unresolved: list[Unresolved] = Field(default_factory=list)
    tool_version: str


FindingType = Literal[
    "duplicate_tag",
    "duplicate_channel",
    "missing_equipment",
    "incompatible_units",
    "conflicting_ranges",
    "missing_evidence",
    "unpriced_line",
    "expired_price",
    "superseded_evidence",
    "unsupported_assertion",
    "reuse_candidate",
    "required_work",
    "ambiguous_identifier",
    "no_relevant_finding",
    "other",
]
Severity = Literal["high", "medium", "low", "info"]
FindingBasis = Literal["rule", "recorded_fact", "candidate_interpretation", "engineer_decision"]


class FindingOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str | None = None
    type: FindingType
    severity: Severity
    title: str = Field(max_length=200)
    summary: str = Field(max_length=2000)
    affected_equipment_ids: list[str]
    evidence_ids: list[str]
    basis: FindingBasis
    rule_id: str | None = None
    open_questions: list[str] = Field(default_factory=list)
    review_status: Literal["unreviewed", "accepted", "rejected", "needs_info"] = "unreviewed"


class EstimateLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    kind: Literal["part", "labour", "allowance", "service"]
    description: str
    equipment_ids: list[str] = Field(default_factory=list)
    quantity: str
    unit: str
    unit_price: str | None = None
    extended: str | None = None
    currency: str = "CAD"
    price_source: str | None = None
    price_effective_date: str | None = None
    pricing_status: Literal["priced", "unpriced", "expired", "allowance"]
    assumption_status: Literal["recorded", "assumed", "engineer_confirmed"] = "recorded"
    classification: Literal["included", "excluded", "optional"]
    origin: dict[str, str]
    evidence_ids: list[str] = Field(default_factory=list)


class EstimateScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    total: str
    assumptions: list[str]


class EstimateOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    currency: Literal["CAD"] = "CAD"
    rate_set_version: str
    lines: list[EstimateLine]
    priced_subtotal: str
    allowances: list[EstimateLine]
    unpriced: list[EstimateLine]
    exclusions: list[str]
    scenarios: list[EstimateScenario] = Field(default_factory=list)
    complete: bool


class ChecklistItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    requirement: str
    proposed_verification: str
    expected_outcome: str | None
    expected_outcome_status: Literal["from_requirement", "missing"]
    evidence_ids: list[str]
    finding_ids: list[str] = Field(default_factory=list)
    equipment_ids: list[str] = Field(default_factory=list)
    template_id: str
    reviewer_decision: Literal["pending", "accepted", "modified", "rejected"] = "pending"


class ReuseCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    equipment_id: str
    rationale: str = Field(max_length=1000)
    evidence_ids: list[str] = Field(min_length=1)
    status: Literal["candidate", "insufficient_evidence"]


class SectionIncomplete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    section: Literal["scope", "dependencies", "consistency", "requirements", "work_breakdown", "estimate", "checklist"]
    reason: str


class DraftPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["review_ready", "needs_clarification", "incomplete"]
    scope_summary: str = Field(max_length=4000)
    affected_equipment_ids: list[str]
    finding_ids: list[str]
    work_item_ids: list[str]
    estimate_id: str | None
    checklist_ids: list[str]
    reuse_candidates: list[ReuseCandidate]
    open_questions: list[str]
    sections_incomplete: list[SectionIncomplete]


class ExtractionAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    raw_tag: str
    attribute: str
    value: str | None
    unit: str | None
    evidence_ids: list[str] = Field(min_length=1)


class ExtractionRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_tag: str
    target_tag: str
    relationship_type: Literal["measures", "signals_to", "wired_to", "controls", "powers", "installed_in", "part_of"]
    evidence_ids: list[str] = Field(min_length=1)


class ExtractionAbstention(BaseModel):
    model_config = ConfigDict(extra="forbid")
    raw_tag: str | None = None
    attribute: str | None = None
    reason: str


class ExtractionCandidates(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assertions: list[ExtractionAssertion]
    relationships: list[ExtractionRelationship]
    abstentions: list[ExtractionAbstention]
