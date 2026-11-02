"""draft_checklist: verification items derived from requirements with cited evidence.

Expected outcomes are only filled when a requirement with evidence exists; otherwise the item
is marked expected_outcome_status="missing". No item is ever created as passed/verified.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from ..contracts import ToolResult
from ..db.models import ChecklistItem, EvidenceSpan, Finding, Run, WorkItem
from .context import SnapshotContext
from .templates import CHECKLIST_TEMPLATES, WORK_TEMPLATES


def _item(ctx: SnapshotContext, run: Run, existing: dict, key: str, payload: dict) -> ChecklistItem:
    if key in existing:
        return existing[key]
    ci = ChecklistItem(org_id=ctx.org_id, project_id=ctx.project_id, run_id=run.id, payload=payload, dedupe_key=key[:300])
    ctx.s.add(ci)
    ctx.s.flush()
    ci.payload = {**payload, "id": str(ci.id)}
    existing[key] = ci
    return ci


def draft_checklist(ctx: SnapshotContext, run: Run, *, work_item_ids: list[str], finding_ids: list[str] | None = None) -> ToolResult:
    try:
        w_ids = [uuid.UUID(x) for x in work_item_ids]
        f_ids = [uuid.UUID(x) for x in (finding_ids or [])]
    except ValueError:
        return ctx.result({}, status="failed", unresolved=[{"code": "bad_id", "message": "ids must be UUIDs"}])
    items = ctx.s.execute(select(WorkItem).where(WorkItem.run_id == run.id, WorkItem.id.in_(w_ids))).scalars().all() if w_ids else []
    findings = ctx.s.execute(select(Finding).where(Finding.run_id == run.id, Finding.id.in_(f_ids))).scalars().all() if f_ids else []
    if not items:
        return ctx.result({}, status="failed", unresolved=[{"code": "no_work_items", "message": "no work items for this run"}])
    existing = {c.dedupe_key: c for c in ctx.s.execute(select(ChecklistItem).where(ChecklistItem.run_id == run.id)).scalars().all()}
    eq_ids = list({e for wi in items for e in wi.equipment_ids})
    eq_map = ctx.equipment_by_id(eq_ids)
    ranges = {}
    for a in ctx.assertions(eq_ids, attributes=["range_lo", "range_hi", "unit"]):
        ranges.setdefault(a.equipment_id, {}).setdefault(a.attribute, []).append(a)
    channels = {a.equipment_id: a for a in ctx.assertions(eq_ids, attributes=["channel"])}
    cards = {a.equipment_id: a.value for a in ctx.assertions(eq_ids, attributes=["card"])}
    narrative_spans = ctx.s.execute(
        select(EvidenceSpan).where(EvidenceSpan.document_version_id.in_(ctx.version_ids), EvidenceSpan.kind == "text")
    ).scalars().all()
    narrative_versions = {vid for vid, v in ctx.versions.items() if ctx.documents.get(v.document_id) and ctx.documents[v.document_id].kind == "narrative"}
    sections = [sp for sp in narrative_spans if sp.document_version_id in narrative_versions and (sp.locator or {}).get("heading")]

    created: list[ChecklistItem] = []
    warnings: list[str] = []
    for wi in items:
        t = WORK_TEMPLATES.get(wi.template_id)
        if not t:
            continue
        for cl_id in t.checklist_templates:
            cl = CHECKLIST_TEMPLATES[cl_id]
            if cl.per == "io_point":
                for eq_id in wi.equipment_ids:
                    eq = eq_map.get(eq_id)
                    if not eq or eq_id not in channels:
                        continue
                    ch = channels[eq_id]
                    r = ranges.get(eq_id, {})
                    hi = r.get("range_hi", [])
                    lo = r.get("range_lo", [])
                    unit = r.get("unit", [])
                    if hi and lo and len({a.value_canonical for a in hi}) == 1 and len({a.value_canonical for a in lo}) == 1:
                        expected = f"PLC reads {lo[0].value}–{hi[0].value} {unit[0].value if unit else ''} across 0–100 % input; alarm set points as per I/O list"
                        status = "from_requirement"
                        ev = list(ch.evidence_ids) + [e for a in hi + lo for e in a.evidence_ids]
                    else:
                        expected, status, ev = None, "missing", list(ch.evidence_ids)
                    created.append(_item(ctx, run, existing, f"{cl_id}:{eq_id}", {
                        "requirement": f"{eq.normalized_tag} on {cards.get(eq_id, 'card ?')} ch {ch.value} must read correctly after the change",
                        "proposed_verification": cl.proposed_verification.format(tag=eq.normalized_tag), "expected_outcome": expected, "expected_outcome_status": status,
                        "evidence_ids": [str(e) for e in dict.fromkeys(ev)], "finding_ids": [], "equipment_ids": [str(eq_id)], "template_id": cl_id, "reviewer_decision": "pending"}))
            elif cl.per == "instrument":
                for eq_id in wi.equipment_ids:
                    eq = eq_map.get(eq_id)
                    if not eq or not (eq.equipment_type.endswith("_transmitter") or eq.equipment_type == "analyzer"):
                        continue
                    r = ranges.get(eq_id, {})
                    hi, lo, unit = r.get("range_hi", []), r.get("range_lo", []), r.get("unit", [])
                    distinct = {a.value_canonical for a in hi}
                    if hi and len(distinct) == 1:
                        expected = f"Configured range {lo[0].value if lo else '?'} to {hi[0].value} {unit[0].value if unit else ''} matches governing record"
                        status, ev = "from_requirement", [e for a in hi + lo + unit for e in a.evidence_ids]
                    elif len(distinct) > 1:
                        expected, status, ev = None, "missing", [e for a in hi + lo for e in a.evidence_ids]
                        warnings.append(f"{eq.normalized_tag}: conflicting ranges; expected outcome left blank pending engineer decision")
                    else:
                        expected, status, ev = None, "missing", list(eq.evidence_ids)
                    created.append(_item(ctx, run, existing, f"{cl_id}:{eq_id}", {
                        "requirement": f"{eq.normalized_tag} calibrated range as recorded", "proposed_verification": cl.proposed_verification.format(tag=eq.normalized_tag),
                        "expected_outcome": expected, "expected_outcome_status": status, "evidence_ids": [str(e) for e in dict.fromkeys(ev)], "finding_ids": [], "equipment_ids": [str(eq_id)],
                        "template_id": cl_id, "reviewer_decision": "pending"}))
            elif cl.per == "narrative_section":
                if not sections:
                    created.append(_item(ctx, run, existing, f"{cl_id}:none", {
                        "requirement": "Control narrative behaviour", "proposed_verification": "Simulate control sequences on the test bench", "expected_outcome": None,
                        "expected_outcome_status": "missing", "evidence_ids": [], "finding_ids": [], "equipment_ids": [str(e) for e in wi.equipment_ids], "template_id": cl_id, "reviewer_decision": "pending"}))
                    warnings.append("no control narrative in snapshot; simulation item has no expected outcome")
                for sp in sections:
                    heading = sp.locator.get("heading")
                    created.append(_item(ctx, run, existing, f"{cl_id}:{sp.id}", {
                        "requirement": f"Narrative section '{heading}'", "proposed_verification": cl.proposed_verification.format(section=heading),
                        "expected_outcome": sp.text[:600], "expected_outcome_status": "from_requirement", "evidence_ids": [str(sp.id)], "finding_ids": [],
                        "equipment_ids": [str(e) for e in wi.equipment_ids], "template_id": cl_id, "reviewer_decision": "pending"}))
            elif cl.per == "finding":
                relevant = [f for f in findings if (cl_id == "CL-COMPAT" and f.type == "unsupported_assertion") or (cl_id == "CL-RECORD-RESOLVED" and f.type in ("conflicting_ranges", "duplicate_channel", "duplicate_tag", "incompatible_units", "ambiguous_identifier"))]
                for f in relevant:
                    created.append(_item(ctx, run, existing, f"{cl_id}:{f.id}", {
                        "requirement": f.title, "proposed_verification": cl.proposed_verification.format(subject=", ".join(eq_map[e].normalized_tag for e in f.affected_equipment_ids if e in eq_map) or "the replacement hardware", title=f.title),
                        "expected_outcome": None, "expected_outcome_status": "missing", "evidence_ids": [str(e) for e in f.evidence_ids], "finding_ids": [str(f.id)],
                        "equipment_ids": [str(e) for e in f.affected_equipment_ids], "template_id": cl_id, "reviewer_decision": "pending"}))
            else:  # job-level
                created.append(_item(ctx, run, existing, f"{cl_id}:{wi.id}", {
                    "requirement": cl.requirement_pattern, "proposed_verification": cl.proposed_verification.format(tag=", ".join(eq_map[e].normalized_tag for e in wi.equipment_ids if e in eq_map)),
                    "expected_outcome": None, "expected_outcome_status": "missing", "evidence_ids": [str(e) for e in wi.evidence_ids], "finding_ids": [], "equipment_ids": [str(e) for e in wi.equipment_ids],
                    "template_id": cl_id, "reviewer_decision": "pending"}))
    ctx.s.flush()
    uniq = list({c.id: c for c in created}.values())
    missing = sum(1 for c in uniq if c.payload["expected_outcome_status"] == "missing")
    return ctx.result({"checklist_items": [c.payload for c in uniq], "counts": {"total": len(uniq), "missing_expected_outcome": missing}},
                      evidence_ids=[uuid.UUID(e) for c in uniq for e in c.payload["evidence_ids"]], warnings=warnings,
                      status="complete" if missing == 0 else "partial",
                      unresolved=[{"code": "expected_outcome_missing", "message": c.payload["requirement"], "subject": str(c.id)} for c in uniq if c.payload["expected_outcome_status"] == "missing"])
