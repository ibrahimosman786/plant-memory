"""Snapshot-scoped read access to engineering records.

Everything an investigation reads goes through a SnapshotContext so results are reproducible
against the frozen set of document versions and so that evidence from outside the snapshot
can never leak into a report.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from functools import cached_property

from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from .. import TOOLS_VERSION
from ..contracts import ToolResult, Unresolved
from ..db.models import Assertion, Document, DocumentVersion, EngineerDecision, Equipment, EvidenceSpan, Relationship, Snapshot, UnresolvedReference


@dataclass
class EvidenceView:
    id: str
    document_version_id: str
    document_id: str
    filename: str
    kind: str
    revision_label: str | None
    locator: dict
    text: str
    span_kind: str


class SnapshotContext:
    def __init__(self, session: Session, org_id: uuid.UUID, project_id: uuid.UUID, snapshot_id: uuid.UUID):
        self.s = session
        self.org_id = org_id
        self.project_id = project_id
        self.snapshot_id = snapshot_id
        snap = session.get(Snapshot, snapshot_id)
        if snap is None or snap.project_id != project_id:
            raise ValueError("snapshot not found in project")
        self.snapshot = snap
        self.version_ids: list[uuid.UUID] = list(snap.document_version_ids)

    # ---------------------------------------------------------------- envelopes

    def result(self, data: dict, *, status: str = "complete", evidence_ids=(), warnings=(), unresolved=()) -> ToolResult:
        return ToolResult(status=status, snapshot_id=str(self.snapshot_id), data=data, evidence_ids=[str(e) for e in evidence_ids],
                          warnings=list(warnings), unresolved=[u if isinstance(u, Unresolved) else Unresolved(**u) for u in unresolved], tool_version=TOOLS_VERSION)

    # ---------------------------------------------------------------- lookups

    @cached_property
    def versions(self) -> dict[uuid.UUID, DocumentVersion]:
        rows = self.s.execute(select(DocumentVersion).where(DocumentVersion.id.in_(self.version_ids))).scalars().all()
        return {v.id: v for v in rows}

    @cached_property
    def documents(self) -> dict[uuid.UUID, Document]:
        doc_ids = {v.document_id for v in self.versions.values()}
        rows = self.s.execute(select(Document).where(Document.id.in_(doc_ids))).scalars().all() if doc_ids else []
        return {d.id: d for d in rows}

    def equipment(self) -> list[Equipment]:
        return self.s.execute(
            select(Equipment).where(Equipment.project_id == self.project_id,
                                    or_(Equipment.document_version_id.in_(self.version_ids), Equipment.document_version_id.is_(None)))
            .order_by(Equipment.normalized_tag, Equipment.created_at)
        ).scalars().all()

    def equipment_by_id(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, Equipment]:
        if not ids:
            return {}
        rows = self.s.execute(select(Equipment).where(Equipment.id.in_(ids), Equipment.project_id == self.project_id)).scalars().all()
        return {e.id: e for e in rows}

    def assertions(self, equipment_ids: list[uuid.UUID] | None = None, attributes: list[str] | None = None) -> list[Assertion]:
        q = select(Assertion).where(Assertion.project_id == self.project_id, Assertion.document_version_id.in_(self.version_ids), Assertion.review_status != "rejected")
        if equipment_ids is not None:
            if not equipment_ids:
                return []
            q = q.where(Assertion.equipment_id.in_(equipment_ids))
        if attributes:
            q = q.where(Assertion.attribute.in_(attributes))
        return self.s.execute(q.order_by(Assertion.created_at)).scalars().all()

    def relationships(self) -> list[Relationship]:
        return self.s.execute(
            select(Relationship).where(Relationship.project_id == self.project_id,
                                       or_(Relationship.document_version_id.in_(self.version_ids), Relationship.document_version_id.is_(None)),
                                       Relationship.status != "disputed")
        ).scalars().all()

    def unresolved_references(self) -> list[UnresolvedReference]:
        return self.s.execute(select(UnresolvedReference).where(UnresolvedReference.project_id == self.project_id,
                                                                UnresolvedReference.document_version_id.in_(self.version_ids))).scalars().all()

    def decisions(self, subject_type: str | None = None) -> list[EngineerDecision]:
        q = select(EngineerDecision).where(EngineerDecision.project_id == self.project_id)
        if subject_type:
            q = q.where(EngineerDecision.subject_type == subject_type)
        return self.s.execute(q).scalars().all()

    def evidence(self, ids: list[uuid.UUID]) -> list[EvidenceView]:
        if not ids:
            return []
        rows = self.s.execute(select(EvidenceSpan).where(EvidenceSpan.id.in_(ids), EvidenceSpan.document_version_id.in_(self.version_ids))).scalars().all()
        return [self.evidence_view(r) for r in rows]

    def evidence_view(self, sp: EvidenceSpan) -> EvidenceView:
        v = self.versions.get(sp.document_version_id)
        d = self.documents.get(v.document_id) if v else None
        return EvidenceView(str(sp.id), str(sp.document_version_id), str(v.document_id) if v else "", d.original_filename if d else "", d.kind if d else "",
                            v.revision_label if v else None, sp.locator, sp.text, sp.kind)

    def evidence_in_snapshot(self, ids: list[uuid.UUID]) -> set[uuid.UUID]:
        if not ids:
            return set()
        rows = self.s.execute(select(EvidenceSpan.id).where(EvidenceSpan.id.in_(ids), EvidenceSpan.document_version_id.in_(self.version_ids))).all()
        return {r[0] for r in rows}

    def source_label(self, version_id: uuid.UUID) -> str:
        v = self.versions.get(version_id)
        d = self.documents.get(v.document_id) if v else None
        if not v or not d:
            return str(version_id)
        rev = f" rev {v.revision_label}" if v.revision_label else f" v{v.version_no}"
        return f"{d.original_filename}{rev}"
