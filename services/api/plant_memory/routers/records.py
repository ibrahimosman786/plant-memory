"""Engineering records: snapshots, equipment, assertions, relationships, search, trace, decisions."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ..auth.deps import DbDep, require_project_role
from ..auth.principal import Principal
from ..db.models import Assertion, CataloguePart, DocumentVersion, EngineerDecision, Equipment, Rate, Relationship, Snapshot, UnresolvedReference
from ..engine.context import SnapshotContext
from ..engine.resolve import equipment_summary
from ..engine.search import search_evidence
from ..engine.trace import trace_dependencies

router = APIRouter(prefix="/v1/projects/{project_id}", tags=["records"])


class SnapshotIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    document_version_ids: list[uuid.UUID] | None = None  # default: latest ready/partial version of every document


def snapshot_out(sn: Snapshot) -> dict:
    return {"id": str(sn.id), "name": sn.name, "document_version_ids": [str(v) for v in sn.document_version_ids], "created_at": sn.created_at.isoformat()}


@router.post("/snapshots", status_code=201)
def create_snapshot(project_id: uuid.UUID, body: SnapshotIn, principal: Annotated[Principal, Depends(require_project_role("analyst"))], s: DbDep) -> dict:
    if body.document_version_ids:
        versions = s.execute(select(DocumentVersion).where(DocumentVersion.id.in_(body.document_version_ids), DocumentVersion.project_id == project_id)).scalars().all()
        if len(versions) != len(set(body.document_version_ids)):
            raise HTTPException(404, "some versions not found in project")
    else:
        all_v = s.execute(select(DocumentVersion).where(DocumentVersion.project_id == project_id, DocumentVersion.status.in_(["ready", "partial"])).order_by(DocumentVersion.version_no.desc())).scalars().all()
        latest: dict[uuid.UUID, DocumentVersion] = {}
        for v in all_v:
            latest.setdefault(v.document_id, v)
        versions = list(latest.values())
    not_ready = [str(v.id) for v in versions if v.status not in ("ready", "partial")]
    if not_ready:
        raise HTTPException(409, f"versions not processed yet: {not_ready}")
    if not versions:
        raise HTTPException(409, "no processed documents to snapshot")
    sn = Snapshot(org_id=principal.org_id, project_id=project_id, name=body.name, document_version_ids=[v.id for v in versions], created_by=principal.user_id)
    s.add(sn)
    s.commit()
    return snapshot_out(sn)


@router.get("/snapshots")
def list_snapshots(project_id: uuid.UUID, principal: Annotated[Principal, Depends(require_project_role("viewer"))], s: DbDep) -> list[dict]:
    return [snapshot_out(x) for x in s.execute(select(Snapshot).where(Snapshot.project_id == project_id).order_by(Snapshot.created_at.desc())).scalars().all()]


def _ctx(s, principal: Principal, project_id: uuid.UUID, snapshot_id: uuid.UUID | None) -> SnapshotContext:
    if snapshot_id is None:
        sn = s.execute(select(Snapshot).where(Snapshot.project_id == project_id).order_by(Snapshot.created_at.desc())).scalars().first()
        if sn is None:
            raise HTTPException(409, "no snapshot exists; create one first")
        snapshot_id = sn.id
    try:
        return SnapshotContext(s, principal.org_id, project_id, snapshot_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/equipment")
def list_equipment(project_id: uuid.UUID, principal: Annotated[Principal, Depends(require_project_role("viewer"))], s: DbDep, snapshot_id: uuid.UUID | None = None, q: str | None = None, type: str | None = None) -> dict:
    ctx = _ctx(s, principal, project_id, snapshot_id)
    rows = ctx.equipment()
    if q:
        ql = q.lower()
        rows = [e for e in rows if ql in e.normalized_tag.lower() or ql in (e.description or "").lower()]
    if type:
        rows = [e for e in rows if e.equipment_type == type]
    counts = s.execute(select(Assertion.equipment_id, func.count()).where(Assertion.document_version_id.in_(ctx.version_ids)).group_by(Assertion.equipment_id)).all()
    cmap = {k: v for k, v in counts}
    tag_counts: dict[str, int] = {}
    for e in ctx.equipment():
        tag_counts[e.normalized_tag] = tag_counts.get(e.normalized_tag, 0) + 1
    return {"snapshot_id": str(ctx.snapshot_id), "equipment": [{**equipment_summary(e), "assertion_count": cmap.get(e.id, 0), "duplicate_tag": tag_counts[e.normalized_tag] > 1} for e in rows]}


@router.get("/equipment/{equipment_id}")
def get_equipment(project_id: uuid.UUID, equipment_id: uuid.UUID, principal: Annotated[Principal, Depends(require_project_role("viewer"))], s: DbDep, snapshot_id: uuid.UUID | None = None) -> dict:
    ctx = _ctx(s, principal, project_id, snapshot_id)
    eq = ctx.equipment_by_id([equipment_id]).get(equipment_id)
    if eq is None:
        raise HTTPException(404)
    assertions = ctx.assertions([equipment_id])
    rels = [r for r in ctx.relationships() if r.source_id == equipment_id or r.target_id == equipment_id]
    other_ids = list({r.target_id if r.source_id == equipment_id else r.source_id for r in rels})
    others = ctx.equipment_by_id(other_ids)
    decisions = [d for d in ctx.decisions() if d.subject_key.startswith(f"assertion_conflict:{equipment_id}:")]
    # group assertions per attribute so conflicts are visible side by side
    by_attr: dict[str, list] = {}
    for a in assertions:
        by_attr.setdefault(a.attribute, []).append({"id": str(a.id), "value": a.value, "unit": a.unit, "value_canonical": str(a.value_canonical) if a.value_canonical is not None else None,
                                                   "unit_canonical": a.unit_canonical, "method": a.method, "review_status": a.review_status, "source": ctx.source_label(a.document_version_id),
                                                   "document_version_id": str(a.document_version_id), "evidence_ids": [str(e) for e in a.evidence_ids]})
    conflicts = [attr for attr, vals in by_attr.items() if len({(v["value_canonical"] or v["value"]) for v in vals}) > 1]
    return {**equipment_summary(eq), "snapshot_id": str(ctx.snapshot_id), "assertions": by_attr, "conflicting_attributes": conflicts,
            "relationships": [{"id": str(r.id), "type": r.relationship_type, "status": r.status, "direction": "out" if r.source_id == equipment_id else "in",
                               "other": equipment_summary(others[r.target_id if r.source_id == equipment_id else r.source_id]) if (r.target_id if r.source_id == equipment_id else r.source_id) in others else None,
                               "evidence_ids": [str(e) for e in r.evidence_ids]} for r in rels],
            "decisions": [{"id": str(d.id), "subject_key": d.subject_key, "decision": d.decision, "rationale": d.rationale, "evidence_ids": [str(e) for e in d.evidence_ids], "created_at": d.created_at.isoformat()} for d in decisions],
            "source": ctx.source_label(eq.document_version_id) if eq.document_version_id else "placeholder (referenced, not listed)"}


@router.get("/unresolved")
def unresolved(project_id: uuid.UUID, principal: Annotated[Principal, Depends(require_project_role("viewer"))], s: DbDep, snapshot_id: uuid.UUID | None = None) -> list[dict]:
    ctx = _ctx(s, principal, project_id, snapshot_id)
    return [{"id": str(u.id), "raw_tag": u.raw_tag, "normalized_tag": u.normalized_tag, "source": ctx.source_label(u.document_version_id), "evidence_ids": [str(e) for e in u.evidence_ids]} for u in ctx.unresolved_references()]


@router.get("/search")
def search(project_id: uuid.UUID, principal: Annotated[Principal, Depends(require_project_role("viewer"))], s: DbDep, q: str = Query(min_length=1), snapshot_id: uuid.UUID | None = None,
           kinds: Annotated[list[str] | None, Query()] = None, limit: int = Query(12, ge=1, le=30)) -> dict:
    ctx = _ctx(s, principal, project_id, snapshot_id)
    return search_evidence(ctx, q, kinds=kinds, limit=limit).model_dump()


@router.get("/trace")
def trace(project_id: uuid.UUID, principal: Annotated[Principal, Depends(require_project_role("viewer"))], s: DbDep, equipment_ids: Annotated[list[uuid.UUID], Query()], snapshot_id: uuid.UUID | None = None,
          depth: int | None = Query(None, ge=1, le=6)) -> dict:
    ctx = _ctx(s, principal, project_id, snapshot_id)
    return trace_dependencies(ctx, [str(e) for e in equipment_ids], depth).model_dump()


@router.get("/catalogue")
def catalogue(project_id: uuid.UUID, principal: Annotated[Principal, Depends(require_project_role("viewer"))], s: DbDep) -> dict:
    parts = s.execute(select(CataloguePart).where(CataloguePart.project_id == project_id).order_by(CataloguePart.part_number)).scalars().all()
    rates = s.execute(select(Rate).where(Rate.project_id == project_id).order_by(Rate.rate_code)).scalars().all()
    return {"parts": [{"id": str(p.id), "part_number": p.part_number, "description": p.description, "category": p.category, "attributes": p.attributes, "unit_price": str(p.unit_price) if p.unit_price is not None else None,
                       "currency": p.currency, "effective_date": p.effective_date.isoformat(), "source": p.source, "evidence_ids": [str(e) for e in p.evidence_ids]} for p in parts],
            "rates": [{"id": str(r.id), "rate_code": r.rate_code, "description": r.description, "unit": r.unit, "rate": str(r.rate), "currency": r.currency, "effective_date": r.effective_date.isoformat(), "rate_set_version": r.rate_set_version} for r in rates]}


class DecisionIn(BaseModel):
    subject_type: str = Field(pattern="^(assertion_conflict|relationship|finding|assumption)$")
    subject_key: str = Field(min_length=3, max_length=300)
    decision: str = Field(min_length=1)
    rationale: str = ""
    evidence_ids: list[uuid.UUID] = Field(default_factory=list)


@router.post("/decisions", status_code=201)
def record_decision(project_id: uuid.UUID, body: DecisionIn, principal: Annotated[Principal, Depends(require_project_role("reviewer"))], s: DbDep) -> dict:
    """An engineer resolves a conflict. The original conflicting records remain; the decision is additive and attributable."""
    d = EngineerDecision(org_id=principal.org_id, project_id=project_id, subject_type=body.subject_type, subject_key=body.subject_key, decision=body.decision, rationale=body.rationale,
                         evidence_ids=body.evidence_ids, decided_by=principal.user_id)
    s.add(d)
    if body.subject_type == "assertion_conflict":
        # optionally mark the chosen assertion verified when the decision names an assertion id
        try:
            chosen = uuid.UUID(body.decision.split("assertion:")[1].split()[0]) if "assertion:" in body.decision else None
        except (ValueError, IndexError):
            chosen = None
        if chosen:
            a = s.get(Assertion, chosen)
            if a and a.project_id == project_id:
                a.review_status = "verified"
    s.commit()
    return {"id": str(d.id), "subject_key": d.subject_key, "decision": d.decision, "created_at": d.created_at.isoformat()}


class AssertionReviewIn(BaseModel):
    review_status: str = Field(pattern="^(recorded|candidate|verified|rejected)$")


@router.post("/assertions/{assertion_id}/review")
def review_assertion(project_id: uuid.UUID, assertion_id: uuid.UUID, body: AssertionReviewIn, principal: Annotated[Principal, Depends(require_project_role("reviewer"))], s: DbDep) -> dict:
    a = s.get(Assertion, assertion_id)
    if a is None or a.project_id != project_id:
        raise HTTPException(404)
    a.review_status = body.review_status
    s.commit()
    return {"id": str(a.id), "review_status": a.review_status}


@router.get("/candidates")
def list_candidates(project_id: uuid.UUID, principal: Annotated[Principal, Depends(require_project_role("viewer"))], s: DbDep, snapshot_id: uuid.UUID | None = None) -> list[dict]:
    """Model-extracted or loose-mention candidates awaiting engineer review."""
    ctx = _ctx(s, principal, project_id, snapshot_id)
    rows = [a for a in ctx.assertions() if a.review_status == "candidate"]
    eq = ctx.equipment_by_id(list({a.equipment_id for a in rows}))
    return [{"id": str(a.id), "equipment": equipment_summary(eq[a.equipment_id]) if a.equipment_id in eq else None, "attribute": a.attribute, "value": a.value, "unit": a.unit, "method": a.method,
             "source": ctx.source_label(a.document_version_id), "evidence_ids": [str(e) for e in a.evidence_ids]} for a in rows]
