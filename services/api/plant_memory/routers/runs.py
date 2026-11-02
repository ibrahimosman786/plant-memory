"""Change requests, investigation runs, SSE progress, clarifications, findings, report versions."""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..auth.deps import DbDep, require_project_role
from ..auth.principal import Principal
from ..cache import LimitExceeded
from ..db.models import ChangeRequest, ChecklistItem, Clarification, Estimate, Finding, Report, ReportVersion, Run, WorkItem
from ..db.session import TenantScope, scoped_session
from ..engine.scope import finding_out, work_item_out
from ..model_gateway import BudgetExhausted, approved_models
from ..runs.events import event_out, events_after
from ..runs.service import ACTIVE_STATES, answer_clarification, cancel_run, start_run

router = APIRouter(prefix="/v1/projects/{project_id}", tags=["runs"])


class ChangeRequestIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    request_text: str = Field(min_length=1, max_length=8000)
    target_tags: list[str] = Field(default_factory=list, max_length=20)
    assumptions: list[str] = Field(default_factory=list, max_length=20)


def cr_out(cr: ChangeRequest) -> dict:
    return {"id": str(cr.id), "title": cr.title, "request_text": cr.request_text, "target_tags": cr.target_tags, "assumptions": cr.assumptions, "created_at": cr.created_at.isoformat()}


def run_out(r: Run) -> dict:
    return {"id": str(r.id), "change_request_id": str(r.change_request_id), "snapshot_id": str(r.snapshot_id), "state": r.state, "backend": r.model_config_.get("backend"), "model": r.model_config_.get("reasoning"), "model_connected": r.model_config_.get("model_connected", False), "fallback_reason": r.model_config_.get("fallback_reason"),
            "tool_invocations": r.tool_invocations, "clarification_cycles": r.clarification_cycles, "input_tokens": r.input_tokens, "output_tokens": r.output_tokens,
            "cost_usd": str(r.cost_usd), "deadline_at": r.deadline_at.isoformat() if r.deadline_at else None, "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None, "error": r.error, "cancel_requested": r.cancel_requested, "created_at": r.created_at.isoformat()}


@router.post("/change-requests", status_code=201)
def create_change_request(project_id: uuid.UUID, body: ChangeRequestIn, principal: Annotated[Principal, Depends(require_project_role("analyst"))], s: DbDep) -> dict:
    cr = ChangeRequest(org_id=principal.org_id, project_id=project_id, title=body.title, request_text=body.request_text, target_tags=body.target_tags, assumptions=body.assumptions, created_by=principal.user_id)
    s.add(cr)
    s.commit()
    return cr_out(cr)


@router.get("/change-requests")
def list_change_requests(project_id: uuid.UUID, principal: Annotated[Principal, Depends(require_project_role("viewer"))], s: DbDep) -> list[dict]:
    crs = s.execute(select(ChangeRequest).where(ChangeRequest.project_id == project_id).order_by(ChangeRequest.created_at.desc())).scalars().all()
    runs = s.execute(select(Run).where(Run.project_id == project_id).order_by(Run.created_at.desc())).scalars().all()
    by_cr: dict[uuid.UUID, list] = {}
    for r in runs:
        by_cr.setdefault(r.change_request_id, []).append(run_out(r))
    return [{**cr_out(c), "runs": by_cr.get(c.id, [])} for c in crs]


class StartRunIn(BaseModel):
    snapshot_id: uuid.UUID
    backend: str | None = Field(default=None, pattern="^(eve|local|gateway)$")
    model: str | None = Field(default=None, max_length=150)


@router.post("/change-requests/{change_request_id}/runs", status_code=202)
def start(project_id: uuid.UUID, change_request_id: uuid.UUID, body: StartRunIn, principal: Annotated[Principal, Depends(require_project_role("analyst"))], s: DbDep) -> dict:
    if body.model and body.model not in approved_models():
        raise HTTPException(422, "model is not in the approved set")
    try:
        run = start_run(s, principal, project_id, change_request_id, body.snapshot_id, backend=body.backend, model=body.model)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except LimitExceeded as exc:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from exc
    except BudgetExhausted as exc:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, str(exc)) from exc
    return run_out(run)


def _run(s, project_id: uuid.UUID, run_id: uuid.UUID) -> Run:
    r = s.get(Run, run_id)
    if r is None or r.project_id != project_id:
        raise HTTPException(404, "run not found")
    return r


@router.get("/runs/{run_id}")
def get_run(project_id: uuid.UUID, run_id: uuid.UUID, principal: Annotated[Principal, Depends(require_project_role("viewer"))], s: DbDep) -> dict:
    r = _run(s, project_id, run_id)
    out = run_out(r)
    out["clarifications"] = [{"id": str(c.id), "question": c.question, "options": c.options, "answer": c.answer, "asked_at": c.asked_at.isoformat()} for c in s.execute(select(Clarification).where(Clarification.run_id == r.id).order_by(Clarification.asked_at)).scalars().all()]
    rv = s.execute(select(ReportVersion).where(ReportVersion.run_id == r.id)).scalars().first()
    out["report_version_id"] = str(rv.id) if rv else None
    return out


@router.get("/runs/{run_id}/events")
def list_events(project_id: uuid.UUID, run_id: uuid.UUID, principal: Annotated[Principal, Depends(require_project_role("viewer"))], s: DbDep, after: int = -1) -> list[dict]:
    r = _run(s, project_id, run_id)
    return [event_out(e) for e in events_after(s, r.id, after)]


@router.get("/runs/{run_id}/stream")
async def stream_events(project_id: uuid.UUID, run_id: uuid.UUID, request: Request, principal: Annotated[Principal, Depends(require_project_role("viewer"))], after: int = Query(-1)) -> StreamingResponse:
    """SSE of persisted run events. Polls the DB (events are durable so reconnects resume via Last-Event-ID)."""
    last = request.headers.get("last-event-id")
    cursor = int(last) if last and last.isdigit() else after
    scope = TenantScope(principal.org_id, principal.project_ids)

    def fetch(cur: int):
        with scoped_session(scope) as s:
            r = s.get(Run, run_id)
            if r is None or r.project_id != project_id:
                return None, []
            return r.state, [event_out(e) for e in events_after(s, r.id, cur)]

    async def gen():
        cur = cursor
        idle = 0
        while True:
            if await request.is_disconnected():
                return
            state, evs = await asyncio.to_thread(fetch, cur)
            if state is None:
                yield "event: error\ndata: {\"error\":\"run not found\"}\n\n"
                return
            for e in evs:
                cur = e["sequence"]
                yield f"id: {cur}\nevent: {e['type']}\ndata: {json.dumps(e)}\n\n"
            if state not in ACTIVE_STATES and not evs:
                yield f"event: end\ndata: {json.dumps({'state': state})}\n\n"
                return
            idle += 1
            if idle % 15 == 0:
                yield ": keepalive\n\n"
            await asyncio.sleep(1.0)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class AnswerIn(BaseModel):
    answer: str = Field(min_length=1, max_length=2000)


@router.post("/runs/{run_id}/clarifications/{clarification_id}/answer")
def answer(project_id: uuid.UUID, run_id: uuid.UUID, clarification_id: uuid.UUID, body: AnswerIn, principal: Annotated[Principal, Depends(require_project_role("analyst"))], s: DbDep) -> dict:
    r = _run(s, project_id, run_id)
    c = s.get(Clarification, clarification_id)
    if c is None or c.run_id != r.id:
        raise HTTPException(404, "clarification not found")
    if c.answer is not None:
        raise HTTPException(409, "already answered")
    if r.state != "waiting_clarification":
        raise HTTPException(409, f"run is {r.state}")
    answer_clarification(s, principal, r, c, body.answer)
    return run_out(r)


@router.post("/runs/{run_id}/cancel")
def cancel(project_id: uuid.UUID, run_id: uuid.UUID, principal: Annotated[Principal, Depends(require_project_role("analyst"))], s: DbDep) -> dict:
    r = _run(s, project_id, run_id)
    if r.state not in ACTIVE_STATES:
        raise HTTPException(409, f"run is {r.state}")
    cancel_run(s, r)
    return run_out(r)


@router.get("/runs/{run_id}/findings")
def findings(project_id: uuid.UUID, run_id: uuid.UUID, principal: Annotated[Principal, Depends(require_project_role("viewer"))], s: DbDep) -> list[dict]:
    r = _run(s, project_id, run_id)
    return [finding_out(f) for f in s.execute(select(Finding).where(Finding.run_id == r.id).order_by(Finding.created_at)).scalars().all()]


@router.get("/runs/{run_id}/work")
def work(project_id: uuid.UUID, run_id: uuid.UUID, principal: Annotated[Principal, Depends(require_project_role("viewer"))], s: DbDep) -> dict:
    r = _run(s, project_id, run_id)
    est = s.execute(select(Estimate).where(Estimate.run_id == r.id)).scalars().first()
    return {"work_items": [work_item_out(w) for w in s.execute(select(WorkItem).where(WorkItem.run_id == r.id)).scalars().all()],
            "estimate": est.payload if est else None,
            "checklist": [c.payload for c in s.execute(select(ChecklistItem).where(ChecklistItem.run_id == r.id)).scalars().all()]}


def report_version_out(rv: ReportVersion, full: bool = False) -> dict:
    out = {"id": str(rv.id), "report_id": str(rv.report_id), "run_id": str(rv.run_id), "snapshot_id": str(rv.snapshot_id), "version_no": rv.version_no, "status": rv.status, "stale": rv.stale,
           "stale_reason": rv.stale_reason, "created_at": rv.created_at.isoformat(), "export_key": rv.export_key}
    if full:
        out["package"] = rv.package
    return out


@router.get("/reports")
def list_reports(project_id: uuid.UUID, principal: Annotated[Principal, Depends(require_project_role("viewer"))], s: DbDep) -> list[dict]:
    reports = s.execute(select(Report).where(Report.project_id == project_id)).scalars().all()
    out = []
    for rep in reports:
        cr = s.get(ChangeRequest, rep.change_request_id)
        versions = s.execute(select(ReportVersion).where(ReportVersion.report_id == rep.id).order_by(ReportVersion.version_no)).scalars().all()
        out.append({"id": str(rep.id), "change_request": cr_out(cr) if cr else None, "versions": [report_version_out(v) for v in versions]})
    return out


@router.get("/report-versions/{report_version_id}")
def get_report_version(project_id: uuid.UUID, report_version_id: uuid.UUID, principal: Annotated[Principal, Depends(require_project_role("viewer"))], s: DbDep) -> dict:
    rv = s.get(ReportVersion, report_version_id)
    if rv is None or rv.project_id != project_id:
        raise HTTPException(404)
    return report_version_out(rv, full=True)
