"""In-process investigation agent.

When AI_GATEWAY_API_KEY is set, a model chooses tools and explains each step in one plain sentence.
The server still closes the package: missing checklist steps are run here, and findings only come
from tools. When the key is absent, the run says so and continues with the fixed checklist.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..config import get_settings
from ..db.models import ChangeRequest, Clarification, Equipment, Run, Snapshot
from ..db.session import TenantScope, scoped_session
from ..ingestion.normalize import find_tags
from ..model_gateway import BudgetExhausted, ModelGateway, ModelUnavailable
from .events import emit
from .local_planner import _infer_change_kind, run_local_plan
from .tools import ToolError, invoke, tool_manifest

_HIDDEN = {"save_draft_package", "validate_package"}
_MAX_TURNS = 8


@dataclass
class Trail:
    targets: list[str] = field(default_factory=list)
    affected: list[str] = field(default_factory=list)
    finding_ids: list[str] = field(default_factory=list)
    work_ids: list[str] = field(default_factory=list)
    estimate_id: str | None = None
    estimate_complete: bool = False
    checklist_ids: list[str] = field(default_factory=list)
    reuse: list = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    nodes: dict[str, str] = field(default_factory=dict)
    traced: bool = False
    truncated: bool = False
    depth: int | None = None
    checked: bool = False
    scoped: bool = False
    estimated: bool = False
    checklist_done: bool = False
    failed_tools: set[str] = field(default_factory=set)


def run_gateway_agent(run_id: uuid.UUID, scope: TenantScope, *, resume: bool = False) -> None:
    del resume  # a resumed run starts a new turn list and reads stored clarification answers
    gateway = ModelGateway()
    if not gateway.available():
        with scoped_session(scope) as s:
            run = s.get(Run, run_id)
            if run is None:
                return
            run.model_config_ = {**run.model_config_, "backend": "guided", "model_connected": False}
            emit(
                s,
                run,
                "agent.said",
                {
                    "text": (
                        "A language model is not connected, so I cannot choose my own steps or read unmarked prose. "
                        "I will still investigate by following the engineering checklist, and I will say what each step is for."
                    )
                },
            )
            s.commit()
        run_local_plan(run_id, scope)
        return

    with scoped_session(scope) as s:
        run = s.get(Run, run_id)
        cr = s.get(ChangeRequest, run.change_request_id)
        snap = s.get(Snapshot, run.snapshot_id)
        if run.state == "queued":
            run.state = "running"
            run.started_at = datetime.now(timezone.utc)
            emit(s, run, "run.started", {"backend": "gateway", "model": run.model_config_.get("reasoning")})
        answered = {c.question: c.answer for c in s.query(Clarification).filter_by(run_id=run.id).all() if c.answer}
        emit(
            s,
            run,
            "agent.said",
            {"text": "I am reading the change request and I will use the project tools. I will not invent tags, prices, or test results."},
        )
        s.commit()
        try:
            _loop(s, run, cr, snap, gateway, answered)
        except ToolError as exc:
            run.state = "cancelled" if exc.code == "cancelled" else ("incomplete" if exc.code in ("tool_limit", "deadline", "budget", "tokens") else "failed")
            run.error = f"{exc.code}: {exc}"
            run.finished_at = datetime.now(timezone.utc)
            emit(s, run, "run.failed", {"error": run.error})
            s.commit()
        except (ModelUnavailable, BudgetExhausted) as exc:
            if isinstance(exc, ModelUnavailable) and get_settings().agent_fallback_to_local and run.tool_invocations == 0 and run.state in ("queued", "running"):
                emit(s, run, "agent.said", {"text": f"The model could not be reached ({exc}). I will continue with the engineering checklist."})
                run.model_config_ = {**run.model_config_, "backend": "guided", "model_connected": False, "fallback_reason": str(exc)[:300]}
                s.commit()
                run_local_plan(run_id, scope)
            else:
                run.state = "incomplete"
                run.error = str(exc)[:1000]
                run.finished_at = datetime.now(timezone.utc)
                emit(s, run, "run.failed", {"error": run.error})
                s.commit()


def _loop(s, run: Run, cr: ChangeRequest, snap: Snapshot, gateway: ModelGateway, answered: dict[str, str]) -> None:
    from .service import finalize_from_package

    settings = get_settings()
    trail = Trail()
    queries = list(cr.target_tags) or [n for _, n in find_tags(cr.request_text)] or [cr.request_text[:120]]
    messages = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": _task(run, cr, snap, queries, answered)},
    ]
    tools = _openai_tools()
    for _turn in range(_MAX_TURNS):
        s.refresh(run, attribute_names=["cancel_requested"])
        if run.cancel_requested:
            run.state = "cancelled"
            run.finished_at = datetime.now(timezone.utc)
            emit(s, run, "run.cancelled", {})
            s.commit()
            return
        remaining = (run.deadline_at - datetime.now(timezone.utc)).total_seconds() if run.deadline_at else 90
        if remaining <= 0:
            raise ToolError("deadline", "Run deadline reached before the next model call", 409)
        if run.cost_usd >= settings.run_max_cost_usd:
            raise ToolError("budget", "Run model budget reached", 409)
        remaining_tokens = settings.run_max_output_tokens - run.output_tokens
        if remaining_tokens <= 0:
            raise ToolError("tokens", "Run output token limit reached", 409)
        turn = gateway.complete_chat(
            model=run.model_config_.get("reasoning", settings.model_reasoning),
            messages=messages,
            tools=tools,
            purpose="agent",
            org_id=run.org_id,
            project_id=run.project_id,
            run_id=run.id,
            max_tokens=min(2000, remaining_tokens),
            timeout=min(90, remaining),
        )
        run.input_tokens += turn.input_tokens
        run.output_tokens += turn.output_tokens
        run.cost_usd += turn.cost_usd
        run.model_config_ = {**run.model_config_, "model_connected": True}
        s.refresh(run, attribute_names=["cancel_requested"])
        if run.cancel_requested:
            raise ToolError("cancelled", "Investigation cancelled", 409)
        said = _plain(turn.content)
        if said:
            emit(s, run, "agent.said", {"text": said[:500]})
        calls = turn.tool_calls or []
        if not calls:
            s.commit()
            break
        messages.append({"role": "assistant", "content": turn.content or "", "tool_calls": calls})
        for call in calls:
            fn = (call.get("function") or {})
            name = fn.get("name") or ""
            raw = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw) if isinstance(raw, str) else dict(raw)
            except (json.JSONDecodeError, TypeError, ValueError):
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps({"error": "Arguments must be a JSON object. Correct them and retry."})})
                continue
            if not isinstance(args, dict):
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps({"error": "Arguments must be a JSON object."})})
                continue
            if name not in _tool_names():
                messages.append({"role": "tool", "tool_call_id": call.get("id") or name, "content": json.dumps({"error": f"unknown tool {name}"})})
                continue
            try:
                paused, payload = _invoke_and_maybe_pause(s, run, cr, name, args, trail, answered)
            except ToolError as exc:
                if exc.code != "invalid_input":
                    raise
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps({"error": str(exc)[:1500]})})
                continue
            if paused:
                return
            messages.append({"role": "tool", "tool_call_id": call.get("id") or name, "content": payload})
        s.commit()
    if run.state == "waiting_clarification":
        return
    _close(s, run, cr, trail, finalize_from_package)
    s.commit()


def _invoke_and_maybe_pause(s, run, cr, name: str, args: dict, trail: Trail, answered: dict[str, str]) -> tuple[bool, str]:
    result = invoke(s, run, name, args)
    _absorb(s, run, trail, name, result)
    payload = _compact(name, result)
    if name != "resolve_equipment":
        return False, payload
    data = result.data or {}
    query = str(args.get("query") or "")
    ambiguous = bool(data.get("ambiguous") or (not data.get("exact_matches") and data.get("loose_matches")))
    if result.status == "failed":
        trail.open_questions.append(f"'{query}' could not be resolved")
        return False, payload
    if not ambiguous:
        if data.get("exact_matches"):
            chosen = data["exact_matches"][0]["id"]
            if chosen not in trail.targets:
                trail.targets.append(chosen)
        elif query:
            trail.open_questions.append(f"'{query}' is not in the equipment list for this snapshot")
        return False, payload
    options = [f"{m['tag']} — {m['description']}" for m in (data.get("exact_matches") or []) + (data.get("loose_matches") or [])][:6]
    question = f"'{query}' is ambiguous ({data.get('ambiguity_reason') or 'no exact match'}). Which equipment is meant?"
    if question in answered:
        chosen = next((m for m in (data.get("exact_matches") or []) + (data.get("loose_matches") or []) if answered[question].startswith(m["tag"])), None)
        if chosen and chosen["id"] not in trail.targets:
            trail.targets.append(chosen["id"])
        return False, payload
    if run.clarification_cycles >= get_settings().run_max_clarification_cycles:
        emit(s, run, "limit.reached", {"limit": "clarification_cycles"})
        trail.open_questions.append(question)
        return False, payload
    c = Clarification(org_id=run.org_id, project_id=run.project_id, run_id=run.id, question=question, options=options)
    s.add(c)
    s.flush()
    run.clarification_cycles += 1
    run.state = "waiting_clarification"
    emit(s, run, "agent.said", {"text": "I need you to pick which equipment this request means before I continue."})
    emit(s, run, "clarification.requested", {"clarification_id": str(c.id), "question": question, "options": options, "cycle": run.clarification_cycles})
    s.commit()
    return True, payload


def _close(s, run: Run, cr: ChangeRequest, trail: Trail, finalize_from_package) -> None:
    queries = list(cr.target_tags) or [n for _, n in find_tags(cr.request_text)] or [cr.request_text[:120]]
    if not trail.targets:
        emit(s, run, "agent.said", {"text": "I am matching the words in the request to equipment tags in this snapshot."})
        answered = {c.question: c.answer for c in s.query(Clarification).filter_by(run_id=run.id).all() if c.answer}
        for q in queries:
            paused, _payload = _invoke_and_maybe_pause(s, run, cr, "resolve_equipment", {"query": q}, trail, answered)
            if paused:
                return
    if not trail.targets:
        emit(s, run, "agent.said", {"text": "I could not match this request to one equipment tag, so the package stays incomplete."})
        res = invoke(s, run, "run_consistency_checks", {"scope_equipment_ids": []})
        _absorb(s, run, trail, "run_consistency_checks", res)
        finalize_from_package(
            s,
            run,
            {
                "status": "incomplete",
                "scope_summary": "No target equipment could be resolved from the change request. The package stays incomplete until a tag in this snapshot is named.",
                "affected_equipment_ids": [],
                "finding_ids": trail.finding_ids,
                "work_item_ids": [],
                "estimate_id": None,
                "checklist_ids": [],
                "reuse_candidates": [],
                "open_questions": trail.open_questions,
                "sections_incomplete": [{"section": "scope", "reason": "targets unresolved"}],
            },
        )
        return
    if not trail.traced:
        emit(s, run, "agent.said", {"text": "I am tracing what this equipment connects to, using only recorded relationships."})
        trace = invoke(s, run, "trace_dependencies", {"equipment_ids": trail.targets})
        _absorb(s, run, trail, "trace_dependencies", trace)
    scope_ids = list(dict.fromkeys(trail.targets + trail.affected))
    if not trail.checked:
        emit(s, run, "agent.said", {"text": "I am running the conflict checks. A missing record stays missing. I will not turn it into a fact."})
        cons = invoke(s, run, "run_consistency_checks", {"scope_equipment_ids": scope_ids})
        _absorb(s, run, trail, "run_consistency_checks", cons)
    if not trail.scoped:
        emit(s, run, "agent.said", {"text": "I am drafting the work from the templates and the findings. Reuse stays a candidate until an engineer accepts it."})
        scope_res = invoke(
            s,
            run,
            "build_work_scope",
            {
                "target_equipment_ids": trail.targets,
                "affected_equipment_ids": trail.affected,
                "finding_ids": trail.finding_ids,
                "change_kind": _infer_change_kind(cr.request_text),
            },
        )
        _absorb(s, run, trail, "build_work_scope", scope_res)
    if trail.work_ids and not trail.estimated:
        emit(s, run, "agent.said", {"text": "I am pricing the work from the catalogue. Lines without a current price stay unpriced."})
        est = invoke(s, run, "build_estimate", {"work_item_ids": trail.work_ids})
        _absorb(s, run, trail, "build_estimate", est)
    if trail.work_ids and not trail.checklist_done:
        emit(s, run, "agent.said", {"text": "I am drafting the checks an engineer would verify. These are proposed checks, not completed tests."})
        chk = invoke(s, run, "draft_checklist", {"work_item_ids": trail.work_ids, "finding_ids": trail.finding_ids})
        _absorb(s, run, trail, "draft_checklist", chk)
    reuse_out = []
    for item in trail.reuse:
        eq = s.get(Equipment, uuid.UUID(item["equipment_id"]))
        evidence = [str(e) for e in eq.evidence_ids] if eq and eq.evidence_ids else []
        if evidence:
            reuse_out.append({"equipment_id": item["equipment_id"], "rationale": item["basis"][:1000], "evidence_ids": evidence, "status": "candidate"})
    tags = ", ".join(trail.nodes.get(t, t) for t in trail.targets)
    summary = (
        f"Change request '{cr.title}' targets {tags}. "
        f"Traversal reached {len(trail.affected)} further items. "
        f"{len(trail.finding_ids)} rule findings; {len(trail.work_ids)} work items; "
        f"estimate {'complete' if trail.estimate_complete else 'incomplete'}. "
        "Findings, prices, and checks come from the tools and the recorded documents. An engineer still reviews the draft."
    )
    incomplete = [{"section": "dependencies", "reason": "traversal truncated at depth limit"}] if trail.truncated else []
    incomplete.extend({"section": name, "reason": "tool failed; no verified result"} for name in sorted(trail.failed_tools))
    emit(s, run, "agent.said", {"text": "I am saving the draft package for an engineer to review. This is not an approval."})
    finalize_from_package(
        s,
        run,
        {
            "status": "review_ready",
            "scope_summary": summary[:4000],
            "affected_equipment_ids": scope_ids,
            "finding_ids": trail.finding_ids,
            "work_item_ids": trail.work_ids,
            "estimate_id": trail.estimate_id,
            "checklist_ids": trail.checklist_ids,
            "reuse_candidates": reuse_out,
            "open_questions": trail.open_questions,
            "sections_incomplete": incomplete,
        },
    )


def _absorb(s, run: Run, trail: Trail, name: str, result) -> None:
    if result.status == "failed":
        trail.failed_tools.add(name)
        trail.open_questions.append(f"Tool {name} failed; its result cannot establish completeness.")
        return
    trail.failed_tools.discard(name)
    data = result.data or {}
    if name == "trace_dependencies" and result.status != "failed":
        trail.traced = True
        trail.affected = data.get("affected_equipment_ids") or []
        trail.truncated = bool(data.get("truncated"))
        trail.depth = data.get("depth")
        trail.nodes = {n["id"]: n["tag"] for n in data.get("nodes") or []}
        emit(s, run, "section.completed", {"section": "dependencies", "nodes": len(data.get("nodes") or []), "truncated": trail.truncated})
    if name == "run_consistency_checks":
        trail.checked = True
        for f in data.get("findings") or []:
            if f["id"] not in trail.finding_ids:
                trail.finding_ids.append(f["id"])
    if name == "build_work_scope":
        trail.scoped = True
        trail.work_ids = [w["id"] for w in data.get("work_items") or []]
        trail.reuse = data.get("reuse_candidates") or []
    if name == "build_estimate":
        trail.estimated = True
        trail.estimate_id = data.get("estimate_id")
        trail.estimate_complete = bool((data.get("estimate") or {}).get("complete"))
        for f in data.get("findings") or []:
            if f["id"] not in trail.finding_ids:
                trail.finding_ids.append(f["id"])
    if name == "draft_checklist":
        trail.checklist_done = True
        trail.checklist_ids = [c["id"] for c in data.get("checklist_items") or []]


def _compact(name: str, result) -> str:
    """Keep tool data and source IDs usable; shorten complete values, never JSON bytes."""
    payload = {"tool": name, "status": result.status, "warnings": result.warnings or [],
               "data": result.data or {}, "evidence_ids": getattr(result, "evidence_ids", [])}
    for limit, text_limit in ((50, 3000), (20, 1500), (8, 600), (3, 200)):
        trimmed = [False]
        def bound(value):
            if isinstance(value, str):
                if len(value) > text_limit:
                    trimmed[0] = True
                    return value[:text_limit] + " [excerpt shortened]"
                return value
            if isinstance(value, list):
                if len(value) > limit:
                    trimmed[0] = True
                return [bound(v) for v in value[:limit]]
            if isinstance(value, dict):
                return {k: bound(v) for k, v in value.items()}
            return value
        brief = bound(payload)
        brief["payload_truncated"] = trimmed[0]
        encoded = json.dumps(brief, default=str)
        if len(encoded) <= 20000:
            return encoded
    return json.dumps({"status": "partial", "payload_truncated": True,
                       "warnings": ["Tool result exceeds context budget. Narrow the query or page size."], "tool": name})


def _tool_names() -> set[str]:
    return {spec["name"] for spec in tool_manifest() if spec["name"] not in _HIDDEN}


def _openai_tools() -> list[dict]:
    tools = []
    for spec in tool_manifest():
        if spec["name"] in _HIDDEN:
            continue
        schema = spec["input_schema"]
        schema.pop("title", None)
        tools.append({"type": "function", "function": {"name": spec["name"], "description": spec["description"], "parameters": schema}})
    return tools


def _system_prompt() -> str:
    from pathlib import Path
    return (Path(__file__).resolve().parents[1] / "prompts" / "investigation.txt").read_text()


def _task(run: Run, cr: ChangeRequest, snap: Snapshot, queries: list[str], answered: dict[str, str]) -> str:
    lines = [
        f"Change request: {cr.title}",
        cr.request_text,
        f"Tags to resolve: {', '.join(queries)}",
        f"Snapshot: {snap.name} with {len(snap.document_version_ids)} document versions.",
        f"Run {run.id}.",
    ]
    if cr.assumptions:
        lines.append("Stated assumptions: " + "; ".join(cr.assumptions))
    if answered:
        lines.append("Already answered by the engineer:")
        lines.extend(f"- {q} => {a}" for q, a in answered.items())
    return "\n".join(lines)


def _plain(content: str | None) -> str:
    text = (content or "").strip()
    if not text:
        return ""
    return " ".join(text.split())


