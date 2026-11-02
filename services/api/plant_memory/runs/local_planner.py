"""Deterministic planner: runs the same tools the agent would, in a fixed order, with no model.

Used for tests, CI, and as an explicit degraded mode when the agent runtime or model budget is
unavailable. It is transparent about what it is: the package carries a scope_summary that says
no model reasoning was applied, and every finding still comes from rules and records only.

Resolution of the change request's target tags is literal: ambiguity raises a clarification
instead of guessing, exactly as the agent instructions require.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from ..db.models import ChangeRequest, Clarification, Run, Snapshot
from ..db.session import TenantScope, scoped_session
from ..ingestion.normalize import find_tags
from .events import emit
from .tools import ToolError, invoke

CHANGE_KIND_HINTS = {
    "rerange": ("re-range", "rerange", "re range", "new range", "change the range"),
    "like_for_like": ("like-for-like", "like for like", "identical replacement"),
}


def _infer_change_kind(text: str) -> str | None:
    t = text.lower()
    for kind, hints in CHANGE_KIND_HINTS.items():
        if any(h in t for h in hints):
            return kind
    return None


def run_local_plan(run_id: uuid.UUID, scope: TenantScope, *, resume: bool = False) -> None:
    with scoped_session(scope) as s:
        run = s.get(Run, run_id)
        cr = s.get(ChangeRequest, run.change_request_id)
        snap = s.get(Snapshot, run.snapshot_id)
        if run.state == "queued":
            run.state = "running"
            run.started_at = datetime.now(timezone.utc)
            emit(s, run, "run.started", {"backend": "local"})
        s.commit()
        try:
            _plan(s, run, cr, snap, resume)
        except ToolError as exc:
            run.state = "cancelled" if exc.code == "cancelled" else ("incomplete" if exc.code in ("tool_limit", "deadline") else "failed")
            run.error = f"{exc.code}: {exc}"
            run.finished_at = datetime.now(timezone.utc)
            emit(s, run, "run.failed", {"error": run.error})
            s.commit()


def _plan(s, run: Run, cr: ChangeRequest, snap: Snapshot, resume: bool) -> None:
    from .service import finalize_from_package

    emit(s, run, "agent.said", {"text": "I am matching the request to equipment tags in the frozen snapshot. I only use tags that are actually recorded."})
    # ---- 1. resolve targets
    queries = list(cr.target_tags) or [n for _, n in find_tags(cr.request_text)]
    if not queries:
        queries = [cr.request_text[:120]]
    emit(s, run, "scope.parsed", {"queries": queries, "change_kind": _infer_change_kind(cr.request_text)})
    answered = {c.question: c.answer for c in s.query(Clarification).filter_by(run_id=run.id).all() if c.answer}
    targets: list[str] = []
    open_questions: list[str] = []
    for q in queries:
        res = invoke(s, run, "resolve_equipment", {"query": q})
        s.commit()
        data = res.data
        if res.status == "failed":
            open_questions.append(f"'{q}' could not be resolved")
            continue
        if data.get("ambiguous") or (not data["exact_matches"] and data["loose_matches"]):
            options = [f"{m['tag']} — {m['description']}" for m in (data["exact_matches"] + data["loose_matches"])[:6]]
            question = f"'{q}' is ambiguous ({data.get('ambiguity_reason') or 'no exact match'}). Which equipment is meant?"
            if question in answered:
                chosen = next((m for m in data["exact_matches"] + data["loose_matches"] if answered[question].startswith(m["tag"])), None)
                if chosen:
                    targets.append(chosen["id"])
                    continue
            if run.clarification_cycles >= _max_cycles():
                emit(s, run, "limit.reached", {"limit": "clarification_cycles"})
                open_questions.append(question)
                continue
            c = Clarification(org_id=run.org_id, project_id=run.project_id, run_id=run.id, question=question, options=options)
            s.add(c)
            s.flush()
            run.clarification_cycles += 1
            run.state = "waiting_clarification"
            emit(s, run, "clarification.requested", {"clarification_id": str(c.id), "question": question, "options": options, "cycle": run.clarification_cycles})
            s.commit()
            return
        if not data["exact_matches"]:
            open_questions.append(f"'{q}' is not in the equipment list for this snapshot")
            continue
        targets.append(data["exact_matches"][0]["id"])

    if not targets:
        pkg = {"status": "incomplete", "scope_summary": "No target equipment could be resolved from the change request. " + _disclaimer(), "affected_equipment_ids": [],
               "finding_ids": [], "work_item_ids": [], "estimate_id": None, "checklist_ids": [], "reuse_candidates": [], "open_questions": open_questions,
               "sections_incomplete": [{"section": "scope", "reason": "targets unresolved"}]}
        # consistency across the whole snapshot still runs so missing-equipment findings surface
        res = invoke(s, run, "run_consistency_checks", {"scope_equipment_ids": []})
        pkg["finding_ids"] = [f["id"] for f in res.data.get("findings", [])]
        finalize_from_package(s, run, pkg)
        s.commit()
        return

    emit(s, run, "agent.said", {"text": "I found the target equipment. Next I trace what it connects to, using recorded relationships only."})
    # ---- 2. trace
    trace = invoke(s, run, "trace_dependencies", {"equipment_ids": targets})
    s.commit()
    affected = trace.data.get("affected_equipment_ids", []) if trace.status != "failed" else []
    all_scope = list(dict.fromkeys(targets + affected))
    emit(s, run, "section.completed", {"section": "dependencies", "nodes": len(trace.data.get("nodes", [])), "truncated": trace.data.get("truncated")})

    emit(s, run, "agent.said", {"text": "I am checking the records for conflicts, missing evidence, and duplicate tags. A gap stays a gap."})
    # ---- 3. consistency
    cons = invoke(s, run, "run_consistency_checks", {"scope_equipment_ids": all_scope})
    s.commit()
    finding_ids = [f["id"] for f in cons.data.get("findings", [])]
    emit(s, run, "section.completed", {"section": "consistency", "findings": len(finding_ids)})

    emit(s, run, "agent.said", {"text": "I am drafting the work, then the cost in CAD, then the proposed checks. Unpriced lines stay unpriced. Checks are not marked passed."})
    # ---- 4. scope, estimate, checklist
    scope_res = invoke(s, run, "build_work_scope", {"target_equipment_ids": targets, "affected_equipment_ids": affected, "finding_ids": finding_ids, "change_kind": _infer_change_kind(cr.request_text)})
    s.commit()
    work_ids = [w["id"] for w in scope_res.data.get("work_items", [])]
    reuse = scope_res.data.get("reuse_candidates", [])
    est = invoke(s, run, "build_estimate", {"work_item_ids": work_ids}) if work_ids else None
    s.commit()
    finding_ids = list(dict.fromkeys(finding_ids + [f["id"] for f in (est.data.get("findings", []) if est else [])]))
    chk = invoke(s, run, "draft_checklist", {"work_item_ids": work_ids, "finding_ids": finding_ids}) if work_ids else None
    s.commit()
    checklist_ids = [c["id"] for c in (chk.data.get("checklist_items", []) if chk else [])]

    emit(s, run, "agent.said", {"text": "I am saving a draft package for an engineer to review. This is not an approval and it does not write to any panel."})
    # ---- 5. package
    eq_tags = {n["id"]: n["tag"] for n in trace.data.get("nodes", [])}
    reuse_out = []
    for r in reuse:
        ev = _equipment_evidence(s, run, r["equipment_id"])
        if ev:
            reuse_out.append({"equipment_id": r["equipment_id"], "rationale": r["basis"][:1000], "evidence_ids": ev, "status": "candidate"})
    summary = (f"Change request '{cr.title}' targets {', '.join(eq_tags.get(t, t) for t in targets)}; traversal (depth {trace.data.get('depth')}) reached {len(affected)} further items. "
               f"{len(finding_ids)} rule findings; {len(work_ids)} work items; estimate {'complete' if est and est.data.get('estimate', {}).get('complete') else 'incomplete'}. "
               + _disclaimer())
    pkg = {"status": "review_ready", "scope_summary": summary[:4000], "affected_equipment_ids": all_scope, "finding_ids": finding_ids, "work_item_ids": work_ids,
           "estimate_id": est.data.get("estimate_id") if est else None, "checklist_ids": checklist_ids, "reuse_candidates": reuse_out, "open_questions": open_questions,
           "sections_incomplete": ([{"section": "dependencies", "reason": "traversal truncated at depth limit"}] if trace.data.get("truncated") else [])}
    finalize_from_package(s, run, pkg)
    s.commit()


def _equipment_evidence(s, run: Run, equipment_id: str) -> list[str]:
    from ..db.models import Equipment
    eq = s.get(Equipment, uuid.UUID(equipment_id))
    return [str(e) for e in eq.evidence_ids] if eq else []


def _max_cycles() -> int:
    from ..config import get_settings
    return get_settings().run_max_clarification_cycles


def _disclaimer() -> str:
    return "Generated by the deterministic planner (fixed tool order, no model reasoning); all findings come from recorded documents and versioned rules."
