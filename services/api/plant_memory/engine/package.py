"""validate_package + save_draft_package.

Validation is deterministic and runs on the server regardless of what the agent claims:
- every finding/work item/checklist/estimate referenced must belong to this run;
- every evidence id must be in the snapshot;
- reuse candidates need evidence and may only be 'candidate' or 'insufficient_evidence';
- expired/unpriced lines force estimate incomplete; incomplete sections force status != review_ready;
- status review_ready requires zero open sections, zero clarifications pending.
"""

from __future__ import annotations

import uuid
from collections import Counter

from pydantic import ValidationError
from sqlalchemy import select

from .. import RULES_VERSION, TEMPLATES_VERSION, TOOLS_VERSION
from ..contracts import DraftPackage, ToolResult
from ..db.models import ChangeRequest, ChecklistItem, Clarification, Estimate, Finding, Report, ReportVersion, Run, WorkItem
from .context import SnapshotContext
from .estimate import finding_out
from .scope import work_item_out


def _uuid_list(xs: list[str]) -> list[uuid.UUID]:
    return [uuid.UUID(x) for x in xs]


def validate_package(ctx: SnapshotContext, run: Run, package: dict) -> tuple[DraftPackage | None, list[str], dict]:
    """Returns (normalized package or None, errors, loaded objects)."""
    errors: list[str] = []
    try:
        pkg = DraftPackage.model_validate(package)
    except ValidationError as exc:
        return None, [f"schema: {e['loc']} {e['msg']}" for e in exc.errors()], {}
    try:
        f_ids, w_ids, c_ids = _uuid_list(pkg.finding_ids), _uuid_list(pkg.work_item_ids), _uuid_list(pkg.checklist_ids)
        e_id = uuid.UUID(pkg.estimate_id) if pkg.estimate_id else None
        aff = _uuid_list(pkg.affected_equipment_ids)
    except ValueError:
        return None, ["ids must be UUIDs"], {}

    findings = ctx.s.execute(select(Finding).where(Finding.run_id == run.id)).scalars().all()
    work_items = ctx.s.execute(select(WorkItem).where(WorkItem.run_id == run.id)).scalars().all()
    checklist = ctx.s.execute(select(ChecklistItem).where(ChecklistItem.run_id == run.id)).scalars().all()
    estimate = ctx.s.execute(select(Estimate).where(Estimate.run_id == run.id)).scalars().first()
    f_map, w_map, c_map = {f.id: f for f in findings}, {w.id: w for w in work_items}, {c.id: c for c in checklist}

    for x in f_ids:
        if x not in f_map:
            errors.append(f"finding {x} does not belong to this run")
    for x in w_ids:
        if x not in w_map:
            errors.append(f"work item {x} does not belong to this run")
    for x in c_ids:
        if x not in c_map:
            errors.append(f"checklist item {x} does not belong to this run")
    if e_id and (estimate is None or estimate.id != e_id):
        errors.append("estimate id does not belong to this run")
    # Findings produced by rules but omitted from the package are an error: nothing may be dropped.
    omitted = [f for f in findings if f.id not in set(f_ids)]
    if omitted:
        errors.append(f"{len(omitted)} findings exist for this run but are not referenced: " + ", ".join(f.title[:40] for f in omitted[:5]))
    eq_map = ctx.equipment_by_id(aff)
    for x in aff:
        if x not in eq_map:
            errors.append(f"affected equipment {x} not in snapshot")
    all_ev = []
    for rc in pkg.reuse_candidates:
        try:
            ids = _uuid_list(rc.evidence_ids)
        except ValueError:
            errors.append("reuse candidate evidence ids must be UUIDs")
            continue
        all_ev.extend(ids)
        try:
            if uuid.UUID(rc.equipment_id) not in ctx.equipment_by_id([uuid.UUID(rc.equipment_id)]):
                errors.append(f"reuse candidate equipment {rc.equipment_id} not in snapshot")
        except ValueError:
            errors.append("reuse candidate equipment id must be UUID")
    present = ctx.evidence_in_snapshot(all_ev)
    for e in all_ev:
        if e not in present:
            errors.append(f"evidence {e} is not in snapshot")

    # Section completeness is recomputed server-side.
    sections = {s.section: s.reason for s in pkg.sections_incomplete}
    if estimate is None:
        sections.setdefault("estimate", "no estimate built")
    elif not estimate.complete:
        sections.setdefault("estimate", "estimate contains unpriced or expired lines")
    if not w_ids:
        sections.setdefault("work_breakdown", "no work items")
    if not c_ids:
        sections.setdefault("checklist", "no checklist items")
    pending = ctx.s.execute(select(Clarification).where(Clarification.run_id == run.id, Clarification.answer.is_(None))).scalars().all()
    open_q = list(pkg.open_questions)
    # Checklist items without an evidenced expected outcome do not block review; the reviewer must
    # supply the outcome, so each becomes an explicit open question instead of a blank.
    no_outcome = [c_map[c] for c in c_ids if c in c_map and c_map[c].payload["expected_outcome_status"] == "missing"]
    if no_outcome:
        q = f"Expected outcome needed for {len(no_outcome)} checklist item(s): " + "; ".join(c.payload["requirement"][:60] for c in no_outcome[:5]) + (" …" if len(no_outcome) > 5 else "")
        if q not in open_q:
            open_q.append(q)
    for f in findings:
        for q in f.open_questions:
            if q not in open_q:
                open_q.append(q)
    status = pkg.status
    if pending:
        status = "needs_clarification"
    elif sections or any(f.severity == "high" and f.review_status == "unreviewed" for f in findings):
        status = "incomplete" if sections else status
    if status == "review_ready" and (sections or pending):
        status = "incomplete"
    normalized = DraftPackage(status=status, scope_summary=pkg.scope_summary, affected_equipment_ids=[str(x) for x in aff], finding_ids=[str(f.id) for f in findings],
                              work_item_ids=[str(x) for x in w_ids], estimate_id=str(estimate.id) if estimate else None, checklist_ids=[str(x) for x in c_ids],
                              reuse_candidates=pkg.reuse_candidates, open_questions=open_q,
                              sections_incomplete=[{"section": k, "reason": v} for k, v in sections.items()])
    return normalized, errors, {"findings": findings, "work_items": [w_map[x] for x in w_ids if x in w_map], "checklist": [c_map[x] for x in c_ids if x in c_map], "estimate": estimate, "equipment": eq_map}


def render_package(ctx: SnapshotContext, run: Run, pkg: DraftPackage, loaded: dict) -> dict:
    """Full report body persisted with the version: package + resolved objects + evidence index."""
    findings = loaded["findings"]
    ev_ids = set()
    for f in findings:
        ev_ids.update(f.evidence_ids)
    for c in loaded["checklist"]:
        ev_ids.update(uuid.UUID(e) for e in c.payload["evidence_ids"])
    for rc in pkg.reuse_candidates:
        ev_ids.update(uuid.UUID(e) for e in rc.evidence_ids)
    if loaded["estimate"]:
        for l in loaded["estimate"].payload["lines"] + loaded["estimate"].payload["unpriced"]:
            ev_ids.update(uuid.UUID(e) for e in l.get("evidence_ids", []))
    evidence = ctx.evidence(list(ev_ids))
    cr = ctx.s.get(ChangeRequest, run.change_request_id)
    return {
        "package": pkg.model_dump(),
        "change_request": {"id": str(cr.id), "title": cr.title, "request_text": cr.request_text} if cr else None,
        "snapshot": {"id": str(ctx.snapshot_id), "name": ctx.snapshot.name, "documents": [{"version_id": str(vid), "label": ctx.source_label(vid)} for vid in ctx.version_ids]},
        "equipment": [{"id": str(e.id), "tag": e.normalized_tag, "type": e.equipment_type, "description": e.description, "location": e.location} for e in loaded["equipment"].values()],
        "findings": [finding_out(f) for f in findings],
        "finding_counts": dict(Counter(f.severity for f in findings)),
        "work_items": [work_item_out(w) for w in loaded["work_items"]],
        "estimate": loaded["estimate"].payload if loaded["estimate"] else None,
        "checklist": [c.payload for c in loaded["checklist"]],
        "evidence": [vars(e) for e in evidence],
        "versions": {"rules": RULES_VERSION, "templates": TEMPLATES_VERSION, "tools": TOOLS_VERSION},
        "disclaimer": "Draft generated from recorded documents and deterministic rules. Nothing here is verified until an engineer reviews and accepts it.",
    }


def save_draft_package(ctx: SnapshotContext, run: Run, package: dict) -> ToolResult:
    pkg, errors, loaded = validate_package(ctx, run, package)
    if pkg is None or errors:
        return ctx.result({"errors": errors}, status="failed", unresolved=[{"code": "invalid_package", "message": e} for e in errors[:20]])
    existing = ctx.s.execute(select(ReportVersion).where(ReportVersion.run_id == run.id)).scalars().first()
    body = render_package(ctx, run, pkg, loaded)
    if existing:
        existing.package = body
        existing.status = pkg.status
        rv = existing
    else:
        report = ctx.s.execute(select(Report).where(Report.change_request_id == run.change_request_id)).scalars().first()
        if report is None:
            report = Report(org_id=ctx.org_id, project_id=ctx.project_id, change_request_id=run.change_request_id)
            ctx.s.add(report)
            ctx.s.flush()
        last = ctx.s.execute(select(ReportVersion.version_no).where(ReportVersion.report_id == report.id).order_by(ReportVersion.version_no.desc())).scalars().first() or 0
        rv = ReportVersion(org_id=ctx.org_id, project_id=ctx.project_id, report_id=report.id, run_id=run.id, snapshot_id=ctx.snapshot_id, version_no=last + 1, package=body, status=pkg.status)
        ctx.s.add(rv)
    ctx.s.flush()
    return ctx.result({"report_version_id": str(rv.id), "report_id": str(rv.report_id), "version_no": rv.version_no, "status": pkg.status,
                       "sections_incomplete": [s.model_dump() for s in pkg.sections_incomplete], "open_questions": pkg.open_questions},
                      status="complete" if pkg.status == "review_ready" else "partial")
