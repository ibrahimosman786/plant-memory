"""Tool registry: the single place where agent-callable tools are named, validated, limited and
dispatched. Both the eve adapter (via /internal/tools/*) and the deterministic fallback planner
go through `invoke`, so limits and event logging are identical."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..config import get_settings
from ..contracts import ToolResult
from ..db.models import Run
from ..engine.checklist import draft_checklist
from ..engine.context import SnapshotContext
from ..engine.estimate import build_estimate
from ..engine.package import save_draft_package, validate_package
from ..engine.resolve import resolve_equipment
from ..engine.scope import build_work_scope, lookup_catalogue, run_consistency_checks
from ..engine.search import search_evidence
from ..engine.trace import trace_dependencies
from .events import emit


class ToolError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400):
        super().__init__(message)
        self.code = code
        self.http_status = http_status


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResolveIn(_Strict):
    query: str = Field(min_length=1, max_length=200)


class SearchIn(_Strict):
    query: str = Field(min_length=1, max_length=500)
    kinds: list[str] | None = None
    tags: list[str] | None = None
    limit: int | None = Field(default=None, ge=1, le=30)


class TraceIn(_Strict):
    equipment_ids: list[str] = Field(min_length=1, max_length=50)
    depth: int | None = Field(default=None, ge=1, le=6)


class ConsistencyIn(_Strict):
    scope_equipment_ids: list[str] = Field(default_factory=list, max_length=200)


class CatalogueIn(_Strict):
    part_number: str | None = None
    category: str | None = None
    attributes: dict[str, Any] | None = None


class ScopeIn(_Strict):
    target_equipment_ids: list[str] = Field(min_length=1)
    affected_equipment_ids: list[str] = Field(default_factory=list)
    finding_ids: list[str] = Field(default_factory=list)
    template_ids: list[str] | None = None
    change_kind: str | None = None


class EstimateIn(_Strict):
    work_item_ids: list[str] = Field(min_length=1)
    exclusions: list[str] | None = None


class ChecklistIn(_Strict):
    work_item_ids: list[str] = Field(min_length=1)
    finding_ids: list[str] | None = None


class PackageIn(_Strict):
    package: dict[str, Any]


class EvidenceIn(_Strict):
    evidence_ids: list[str] = Field(min_length=1, max_length=50)


def _get_evidence(ctx: SnapshotContext, run: Run, inp: EvidenceIn) -> ToolResult:
    try:
        ids = [uuid.UUID(x) for x in inp.evidence_ids]
    except ValueError:
        return ctx.result({}, status="failed", unresolved=[{"code": "bad_id", "message": "evidence ids must be UUIDs"}])
    views = ctx.evidence(ids)
    found = {v.id for v in views}
    missing = [str(i) for i in ids if str(i) not in found]
    return ctx.result({"evidence": [vars(v) for v in views], "missing": missing}, evidence_ids=[uuid.UUID(v.id) for v in views],
                      status="complete" if not missing else "partial",
                      unresolved=[{"code": "not_in_snapshot", "message": "evidence not in snapshot", "subject": m} for m in missing])


def _validate_package(ctx: SnapshotContext, run: Run, inp: PackageIn) -> ToolResult:
    pkg, errors, _ = validate_package(ctx, run, inp.package)
    if pkg is None:
        return ctx.result({"errors": errors}, status="failed", unresolved=[{"code": "invalid_package", "message": e} for e in errors[:20]])
    return ctx.result({"package": pkg.model_dump(), "errors": errors}, status="complete" if not errors else "partial", warnings=errors)


TOOLS: dict[str, tuple[type[BaseModel], Callable[..., ToolResult], str]] = {
    "resolve_equipment": (ResolveIn, lambda ctx, run, i: resolve_equipment(ctx, i.query), "Resolve a tag or description to equipment records in the snapshot."),
    "search_evidence": (SearchIn, lambda ctx, run, i: search_evidence(ctx, i.query, kinds=i.kinds, tags=i.tags, limit=i.limit), "Hybrid search over evidence passages (tag, lexical, vector)."),
    "get_evidence": (EvidenceIn, _get_evidence, "Fetch evidence spans by id with document, page/cell locators and text."),
    "trace_dependencies": (TraceIn, lambda ctx, run, i: trace_dependencies(ctx, i.equipment_ids, i.depth), "Traverse recorded relationships from equipment, bounded depth."),
    "run_consistency_checks": (ConsistencyIn, lambda ctx, run, i: run_consistency_checks(ctx, run, i.scope_equipment_ids), "Run the deterministic rule catalogue over the affected scope."),
    "lookup_catalogue": (CatalogueIn, lambda ctx, run, i: lookup_catalogue(ctx, part_number=i.part_number, category=i.category, attributes=i.attributes), "Look up parts and prices in the project catalogue."),
    "build_work_scope": (ScopeIn, lambda ctx, run, i: build_work_scope(ctx, run, target_equipment_ids=i.target_equipment_ids, affected_equipment_ids=i.affected_equipment_ids, finding_ids=i.finding_ids, template_ids=i.template_ids, change_kind=i.change_kind), "Create work items from templates for the targets and findings."),
    "build_estimate": (EstimateIn, lambda ctx, run, i: build_estimate(ctx, run, work_item_ids=i.work_item_ids, exclusions=i.exclusions), "Deterministic Decimal estimate from work items, rates and catalogue."),
    "draft_checklist": (ChecklistIn, lambda ctx, run, i: draft_checklist(ctx, run, work_item_ids=i.work_item_ids, finding_ids=i.finding_ids), "Draft verification items with evidenced expected outcomes."),
    "validate_package": (PackageIn, _validate_package, "Validate a draft package against run objects, snapshot evidence and completeness rules."),
    "save_draft_package": (PackageIn, lambda ctx, run, i: save_draft_package(ctx, run, i.package), "Validate and persist the draft package as a report version."),
}


def tool_manifest() -> list[dict]:
    return [{"name": n, "description": d, "input_schema": m.model_json_schema()} for n, (m, _, d) in TOOLS.items()]


def invoke(session: Session, run: Run, name: str, raw_input: dict) -> ToolResult:
    """Validate input, enforce run limits, execute, log events. Raises ToolError on limit/validation."""
    settings = get_settings()
    if name not in TOOLS:
        raise ToolError("unknown_tool", f"unknown tool {name}", 404)
    if run.cancel_requested or run.state in ("cancelled", "failed", "completed", "incomplete"):
        raise ToolError("run_inactive", f"run is {run.state}", 409)
    now = datetime.now(timezone.utc)
    if run.deadline_at and now > run.deadline_at:
        emit(session, run, "limit.reached", {"limit": "deadline", "deadline_at": run.deadline_at.isoformat()})
        raise ToolError("deadline", "run active deadline exceeded", 409)
    if run.tool_invocations >= settings.run_max_tool_invocations:
        emit(session, run, "limit.reached", {"limit": "tool_invocations", "max": settings.run_max_tool_invocations})
        raise ToolError("tool_limit", f"tool invocation limit {settings.run_max_tool_invocations} reached", 409)
    model_cls, fn, _ = TOOLS[name]
    try:
        inp = model_cls.model_validate(raw_input or {})
    except Exception as exc:
        raise ToolError("invalid_input", str(exc), 422) from exc
    run.tool_invocations += 1
    emit(session, run, "tool.started", {"tool": name, "input": inp.model_dump(), "invocation": run.tool_invocations})
    started = time.perf_counter()
    ctx = SnapshotContext(session, run.org_id, run.project_id, run.snapshot_id)
    try:
        result = fn(ctx, run, inp)
    except Exception as exc:
        emit(session, run, "tool.failed", {"tool": name, "error": str(exc)[:500], "ms": int((time.perf_counter() - started) * 1000)})
        session.flush()
        return ctx.result({"error": str(exc)[:500]}, status="failed", unresolved=[{"code": "tool_exception", "message": str(exc)[:500]}])
    ms = int((time.perf_counter() - started) * 1000)
    summary = {"tool": name, "status": result.status, "ms": ms, "evidence_count": len(result.evidence_ids), "warnings": result.warnings[:5], "unresolved": len(result.unresolved)}
    if name == "run_consistency_checks":
        for f in result.data.get("findings", []):
            emit(session, run, "finding.added", {"finding_id": f["id"], "type": f["type"], "severity": f["severity"], "title": f["title"], "rule_id": f.get("rule_id")})
    if name == "build_estimate":
        for f in result.data.get("findings", []):
            emit(session, run, "finding.added", {"finding_id": f["id"], "type": f["type"], "severity": f["severity"], "title": f["title"], "rule_id": f.get("rule_id")})
        summary["complete"] = result.data.get("estimate", {}).get("complete")
    if name == "save_draft_package" and result.status != "failed":
        emit(session, run, "package.saved", {"report_version_id": result.data.get("report_version_id"), "version_no": result.data.get("version_no"), "status": result.data.get("status")})
    emit(session, run, "tool.completed", summary)
    session.flush()
    return result
