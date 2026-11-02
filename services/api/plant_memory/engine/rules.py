"""Versioned deterministic rule catalogue (section 12).

Each rule is a pure function over a SnapshotContext and an affected-scope list and returns
FindingDrafts. No rule asserts compatibility or safety; those remain engineer decisions.
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from .. import RULES_VERSION
from ..config import get_settings
from ..db.models import DocumentVersion, EvidenceSpan
from ..ingestion.normalize import units_compatible, LOOSE_TAG_RE, find_tags
from .context import SnapshotContext


@dataclass
class FindingDraft:
    type: str
    severity: str
    title: str
    summary: str
    affected_equipment_ids: list[uuid.UUID]
    evidence_ids: list[uuid.UUID]
    rule_id: str
    basis: str = "rule"
    open_questions: list[str] = field(default_factory=list)
    dedupe_key: str = ""

    def __post_init__(self):
        if not self.dedupe_key:
            self.dedupe_key = f"{self.rule_id}:{','.join(sorted(str(e) for e in self.affected_equipment_ids))}:{self.title[:80]}"


RULES: dict[str, dict] = {}


def rule(rule_id: str, title: str):
    def deco(fn):
        RULES[rule_id] = {"id": rule_id, "title": title, "fn": fn, "version": RULES_VERSION}
        return fn

    return deco


def _in_scope(eq_id: uuid.UUID, scope: set[uuid.UUID] | None) -> bool:
    return scope is None or eq_id in scope


def fmt(d: Decimal | None) -> str:
    """Human-readable Decimal: 1600.00000000 → 1600, 0.40000000 → 0.4."""
    if d is None:
        return "?"
    s = format(d.normalize(), "f")
    return s if s != "-0" else "0"


@rule("R001", "Duplicate tag within the equipment namespace")
def duplicate_tag(ctx: SnapshotContext, scope: set[uuid.UUID] | None) -> list[FindingDraft]:
    groups: dict[str, list] = defaultdict(list)
    for e in ctx.equipment():
        groups[e.normalized_tag].append(e)
    out = []
    for tag, eqs in groups.items():
        if len(eqs) > 1 and (scope is None or any(e.id in scope for e in eqs)):
            out.append(FindingDraft("duplicate_tag", "medium", f"Tag {tag} appears {len(eqs)} times",
                                    f"The equipment namespace contains {len(eqs)} entries for {tag}: " + "; ".join(f"'{e.description}' ({e.location or 'no location'})" for e in eqs) +
                                    ". Downstream references cannot be attributed unambiguously until one entry is confirmed.",
                                    [e.id for e in eqs], [ev for e in eqs for ev in e.evidence_ids], "R001",
                                    open_questions=[f"Which {tag} entry is the installed equipment? Should the other be retagged or removed?"]))
    return out


@rule("R002", "Duplicate channel assignment")
def duplicate_channel(ctx: SnapshotContext, scope: set[uuid.UUID] | None) -> list[FindingDraft]:
    cards: dict[uuid.UUID, dict[str, str]] = defaultdict(dict)
    chans: dict[uuid.UUID, dict[str, str]] = defaultdict(dict)
    ev: dict[tuple[uuid.UUID, uuid.UUID], list[uuid.UUID]] = defaultdict(list)
    for a in ctx.assertions(attributes=["card", "channel"]):
        (cards if a.attribute == "card" else chans)[a.equipment_id][str(a.document_version_id)] = a.value
        ev[(a.equipment_id, a.document_version_id)].extend(a.evidence_ids)
    slots: dict[tuple[str, str, str], list[tuple[uuid.UUID, uuid.UUID]]] = defaultdict(list)
    for eq_id, by_ver in cards.items():
        for ver, card in by_ver.items():
            ch = chans.get(eq_id, {}).get(ver)
            if ch:
                slots[(ver, card.strip().upper(), ch.strip())].append((eq_id, uuid.UUID(ver)))
    out = []
    eq_map = ctx.equipment_by_id(list({e for lst in slots.values() for e, _ in lst}))
    for (ver, card, ch), members in slots.items():
        ids = sorted({e for e, _ in members}, key=str)
        if len(ids) > 1 and (scope is None or any(i in scope for i in ids)):
            tags = ", ".join(eq_map[i].normalized_tag for i in ids if i in eq_map)
            out.append(FindingDraft("duplicate_channel", "high", f"{card} channel {ch} assigned to {len(ids)} points",
                                    f"In {ctx.source_label(uuid.UUID(ver))}, {tags} are all assigned to {card} channel {ch}. One channel cannot carry two signals; the I/O allocation must be corrected before migration.",
                                    ids, [x for m in members for x in ev[m]], "R002", open_questions=[f"Which point is actually landed on {card} ch {ch}?"]))
    return out


@rule("R003", "Missing referenced equipment")
def missing_equipment(ctx: SnapshotContext, scope: set[uuid.UUID] | None) -> list[FindingDraft]:
    known = {e.normalized_tag for e in ctx.equipment()}
    groups: dict[str, list] = defaultdict(list)
    for u in ctx.unresolved_references():
        if u.normalized_tag not in known:
            groups[u.normalized_tag].append(u)
    out = []
    for tag, refs in groups.items():
        srcs = sorted({ctx.source_label(r.document_version_id) for r in refs})
        out.append(FindingDraft("missing_equipment", "medium", f"{tag} is referenced but not in the equipment list",
                                f"{tag} is mentioned in {', '.join(srcs)} but no equipment record exists in this snapshot. Work that depends on it cannot be scoped until the record is added or the reference corrected.",
                                [], [e for r in refs for e in r.evidence_ids], "R003", open_questions=[f"Is {tag} planned, removed, or a typo?"], dedupe_key=f"R003:{tag}"))
    return out


def _range_groups(ctx: SnapshotContext, scope: set[uuid.UUID] | None):
    """equipment -> attribute -> list of assertions (range_lo/range_hi/unit)."""
    grouped: dict[uuid.UUID, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    eq_ids = list(scope) if scope is not None else None
    for a in ctx.assertions(eq_ids, attributes=["range_lo", "range_hi", "unit"]):
        grouped[a.equipment_id][a.attribute].append(a)
    return grouped


@rule("R004", "Incompatible recorded units")
def incompatible_units(ctx: SnapshotContext, scope: set[uuid.UUID] | None) -> list[FindingDraft]:
    out = []
    eq_map = ctx.equipment_by_id(list(scope) if scope else [e.id for e in ctx.equipment()])
    for eq_id, attrs in _range_groups(ctx, scope).items():
        units = {}
        for a in attrs.get("unit", []):
            units.setdefault(a.unit_canonical or a.value, []).append(a)
        if len(units) < 2:
            continue
        keys = list(units.keys())
        pairs = [(keys[i], keys[j]) for i in range(len(keys)) for j in range(i + 1, len(keys))]
        bad = [(u1, u2) for u1, u2 in pairs if units_compatible(u1, u2) is False]
        if bad:
            tag = eq_map[eq_id].normalized_tag if eq_id in eq_map else str(eq_id)
            detail = "; ".join(f"{u}: {', '.join(ctx.source_label(a.document_version_id) for a in units[u])}" for u in keys)
            out.append(FindingDraft("incompatible_units", "high", f"{tag} recorded in incompatible units",
                                    f"{tag} has engineering units that do not describe the same quantity: {detail}. Scaling cannot be migrated until the correct unit is confirmed.",
                                    [eq_id], [e for lst in units.values() for a in lst for e in a.evidence_ids], "R004", open_questions=[f"Which unit is correct for {tag}?"]))
    return out


@rule("R005", "Conflicting recorded measurement ranges")
def conflicting_ranges(ctx: SnapshotContext, scope: set[uuid.UUID] | None) -> list[FindingDraft]:
    out = []
    eq_map = ctx.equipment_by_id(list(scope) if scope else [e.id for e in ctx.equipment()])
    decisions = {d.subject_key: d for d in ctx.decisions("assertion_conflict")}
    for eq_id, attrs in _range_groups(ctx, scope).items():
        for attr in ("range_hi", "range_lo"):
            rows = [a for a in attrs.get(attr, []) if a.value_canonical is not None]
            if len(rows) < 2:
                continue
            units = {a.unit_canonical for a in rows if a.unit_canonical}
            if len(units) > 1 and any(units_compatible(u1, u2) is False for u1 in units for u2 in units if u1 != u2):
                continue  # R004 owns this
            values = sorted({(a.value_canonical, a.unit_canonical) for a in rows}, key=lambda t: t[0])
            if len(values) < 2:
                continue
            lo, hi = values[0][0], values[-1][0]
            if hi == 0 or abs(hi - lo) / max(abs(hi), Decimal("0.000001")) <= Decimal("0.005"):
                continue
            tag = eq_map[eq_id].normalized_tag if eq_id in eq_map else str(eq_id)
            detail = "; ".join(f"{a.value} {a.unit or ''} ({ctx.source_label(a.document_version_id)})" for a in rows)
            key = f"assertion_conflict:{eq_id}:{attr}"
            ev = [e for a in rows for e in a.evidence_ids]
            if key in decisions:
                d = decisions[key]
                out.append(FindingDraft("conflicting_ranges", "info", f"{tag} {attr} conflict resolved by engineer decision",
                                        f"Records disagree ({detail}). Engineer decision: {d.decision}. Rationale: {d.rationale or 'none given'}. Both records remain on file.",
                                        [eq_id], ev + list(d.evidence_ids), "R005", basis="engineer_decision", dedupe_key=f"R005:{eq_id}:{attr}"))
            else:
                out.append(FindingDraft("conflicting_ranges", "medium", f"{tag} {attr.replace('_', ' ')} differs between records",
                                        f"{tag} has conflicting {attr.replace('_', ' ')} values: {detail}. The system preserves both; an engineer must decide which governs the new configuration.",
                                        [eq_id], ev, "R005", open_questions=[f"Which {attr.replace('_', ' ')} is correct for {tag}: {' or '.join(fmt(v[0]) for v in values)} {values[0][1] or ''}?"],
                                        dedupe_key=f"R005:{eq_id}:{attr}"))
    return out


@rule("R006", "Missing required evidence")
def missing_required_evidence(ctx: SnapshotContext, scope: set[uuid.UUID] | None) -> list[FindingDraft]:
    """Two sources: (a) datasheets whose range could not be read; (b) cards in scope with no
    recorded spare-channel capacity when the scope touches the panel/cards."""
    out = []
    equipment = {e.normalized_tag: e for e in ctx.equipment()}
    # (a) unreadable datasheets
    for vid, v in ctx.versions.items():
        d = ctx.documents.get(v.document_id)
        if not d or d.kind != "datasheet":
            continue
        for w in (v.status_detail or {}).get("warnings", []):
            m = re.match(r"([A-Z]{1,4}-\d{2,4}[A-Z0-9]*): calibrated range not found", w)
            if m:
                tag = m.group(1)
                eq = equipment.get(tag)
                if eq and _in_scope(eq.id, scope):
                    title_ev = [sp.id for sp in ctx.s.query(EvidenceSpan).filter_by(document_version_id=vid).order_by(EvidenceSpan.seq).limit(1)]
                    out.append(FindingDraft("missing_evidence", "low", f"{tag} datasheet range unreadable",
                                            f"The datasheet {ctx.source_label(vid)} did not yield a calibrated range ({w.split(':', 1)[1].strip()}). The range cannot be confirmed from this document; other records may exist but the datasheet itself needs a legible copy.",
                                            [eq.id], title_ev, "R006", open_questions=[f"Can a legible datasheet for {tag} be obtained?"], dedupe_key=f"R006:datasheet:{tag}"))
    # (b) spare capacity
    scope_eqs = ctx.equipment_by_id(list(scope)) if scope else {}
    cards = [e for e in scope_eqs.values() if e.equipment_type.endswith("_card") or e.normalized_tag.split("-")[0] in ("AI", "AO", "DI", "DO")]
    if cards:
        spare = {a.equipment_id for a in ctx.assertions([c.id for c in cards], attributes=["channels_spare"])}
        missing = [c for c in cards if c.id not in spare]
        if missing:
            tags = ", ".join(c.normalized_tag for c in missing)
            out.append(FindingDraft("missing_evidence", "medium", "Spare I/O capacity not recorded",
                                    f"No spare-channel count is recorded for {tags} in this snapshot. Reuse or expansion of these cards cannot assume free channels; the count must be confirmed from the panel schedule or on site.",
                                    [c.id for c in missing], [e for c in missing for e in c.evidence_ids], "R006", open_questions=["How many spare channels exist per card?"], dedupe_key="R006:spare"))
    return out


@rule("R009", "Superseded evidence in snapshot")
def superseded_evidence(ctx: SnapshotContext, scope: set[uuid.UUID] | None) -> list[FindingDraft]:
    out = []
    for vid, v in ctx.versions.items():
        newer = ctx.s.execute(select(DocumentVersion).where(DocumentVersion.document_id == v.document_id, DocumentVersion.version_no > v.version_no)).scalars().first()
        if newer:
            out.append(FindingDraft("superseded_evidence", "medium", f"{ctx.source_label(vid)} has a newer revision",
                                    f"The snapshot uses {ctx.source_label(vid)}, but version {newer.version_no} ({newer.revision_label or 'unlabelled'}) was uploaded later. Findings based on this document may be stale; re-run against an updated snapshot to confirm.",
                                    [], [], "R009", dedupe_key=f"R009:{vid}"))
    return out


CLAIM_PATTERNS = [
    re.compile(r"\bfully compatible\b", re.I),
    re.compile(r"\brequires? no (program|programme|software|logic) changes?\b", re.I),
    re.compile(r"\bno (program|configuration|wiring) changes? (are |is )?(required|needed)\b", re.I),
    re.compile(r"\bcertified compatible\b", re.I),
    re.compile(r"\b(all )?tests? (have )?(passed|completed successfully)\b", re.I),
    re.compile(r"\bdrop-in replacement\b", re.I),
]


@rule("R010", "Unsupported assertion presented as confirmed")
def unsupported_assertion(ctx: SnapshotContext, scope: set[uuid.UUID] | None) -> list[FindingDraft]:
    out = []
    spans = ctx.s.execute(select(EvidenceSpan).where(EvidenceSpan.document_version_id.in_(ctx.version_ids), EvidenceSpan.kind.in_(["text", "row"]))).scalars().all()
    equipment = {e.normalized_tag: e for e in ctx.equipment()}
    for sp in spans:
        hits = [p.pattern for p in CLAIM_PATTERNS if p.search(sp.text)]
        if not hits:
            continue
        has_support = bool(re.search(r"\b(test (record|report|certificate)|FAT report|attached|see appendix|per IEC|per ISA)\b", sp.text, re.I)) and not re.search(r"\bno .*attached\b", sp.text, re.I)
        if has_support:
            continue
        tags = [equipment[n].id for _, n in find_tags(sp.text) if n in equipment]
        if scope is not None and tags and not any(t in scope for t in tags):
            continue
        out.append(FindingDraft("unsupported_assertion", "high", f"Compatibility/test claim without evidence in {ctx.source_label(sp.document_version_id)}",
                                f"The passage states: \"{sp.text[:240]}\". No test record, report, or standard reference accompanies the claim. It is recorded as a vendor/author statement, not as a verified fact; compatibility must be confirmed by a drafted verification item.",
                                tags, [sp.id], "R010", open_questions=["What evidence supports this claim?"], dedupe_key=f"R010:{sp.id}"))
    return out


@rule("R011", "Ambiguous identifier")
def ambiguous_identifier(ctx: SnapshotContext, scope: set[uuid.UUID] | None) -> list[FindingDraft]:
    out = []
    equipment = ctx.equipment()
    by_eq = {e.id: e for e in equipment}
    for a in ctx.assertions(attributes=["mentioned_as"]):
        m = LOOSE_TAG_RE.fullmatch(a.value or "")
        if not m:
            continue
        stem = f"{m.group(1).upper()}-{m.group(2)}"
        matches = [e for e in equipment if e.normalized_tag.startswith(stem)]
        if len(matches) > 1 and (scope is None or any(e.id in scope for e in matches)):
            tags = ", ".join(e.normalized_tag for e in matches)
            out.append(FindingDraft("ambiguous_identifier", "medium", f"'{a.value}' could refer to {len(matches)} items",
                                    f"The mention '{a.value}' in {ctx.source_label(a.document_version_id)} normalizes to {stem} and matches {tags}. The record is attached to {by_eq[a.equipment_id].normalized_tag} as a candidate only.",
                                    [e.id for e in matches], list(a.evidence_ids), "R011", open_questions=[f"Which of {tags} does '{a.value}' refer to?"], dedupe_key=f"R011:{a.value}"))
    return out


# R007 (unpriced line) and R008 (expired price) run inside the estimator where lines exist.

def price_expired(effective: date, today: date | None = None) -> bool:
    today = today or date.today()
    return effective < today - timedelta(days=get_settings().price_max_age_days)


def run_rules(ctx: SnapshotContext, scope: list[uuid.UUID] | None, rule_ids: list[str] | None = None) -> tuple[list[FindingDraft], list[str]]:
    scope_set = set(scope) if scope is not None else None
    findings: list[FindingDraft] = []
    errors: list[str] = []
    for rid, spec in RULES.items():
        if rule_ids and rid not in rule_ids:
            continue
        try:
            findings.extend(spec["fn"](ctx, scope_set))
        except Exception as exc:  # a failing rule is reported, never swallowed as "no issue"
            errors.append(f"{rid} failed: {exc}")
    return findings, errors
