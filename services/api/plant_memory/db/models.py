"""SQLAlchemy models. Every project-owned row carries org_id and project_id for row-level security.

Design rules (section 5 of the plan):
- Conflicting assertions are preserved, never overwritten.
- Document versions are immutable; corrections create new versions.
- Snapshots pin the exact document versions an investigation ran against.
- Report versions are immutable; reviews target a specific version.
"""

from __future__ import annotations

import uuid
from datetime import datetime, date
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ..config import get_settings

EMBEDDING_DIM = get_settings().embedding_dim


class Base(DeclarativeBase):
    pass


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))


def created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TenantMixin:
    """Columns required by RLS. Tables with this mixin get the standard policies."""

    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)


# --------------------------------------------------------------------------- identity

class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = created_at()


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    external_subject: Mapped[str | None] = mapped_column(String(200), unique=True)
    created_at: Mapped[datetime] = created_at()


class Membership(Base):
    """Org-level membership. `role` here is the default role for projects without an explicit grant."""

    __tablename__ = "memberships"
    id: Mapped[uuid.UUID] = uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # viewer|analyst|reviewer|admin
    __table_args__ = (UniqueConstraint("org_id", "user_id"),)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[uuid.UUID] = uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    permissions_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = created_at()


class ProjectMember(Base):
    __tablename__ = "project_members"
    id: Mapped[uuid.UUID] = uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)


# --------------------------------------------------------------------------- documents and evidence

class Document(TenantMixin, Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = uuid_pk()
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)  # equipment_list|io_list|narrative|datasheet|pid|config_export|catalogue|rates|other
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = created_at()


class DocumentVersion(TenantMixin, Base):
    __tablename__ = "document_versions"
    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    revision_label: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="uploaded", nullable=False)  # uploaded|processing|ready|partial|failed
    status_detail: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_type: Mapped[str] = mapped_column(String(200), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    pipeline_version: Mapped[str | None] = mapped_column(String(40))
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = created_at()
    __table_args__ = (UniqueConstraint("document_id", "version_no"),)


class EvidenceSpan(TenantMixin, Base):
    """The smallest citable unit: a page region, a sheet cell/row, a CSV row, a config record."""

    __tablename__ = "evidence_spans"
    id: Mapped[uuid.UUID] = uuid_pk()
    document_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_versions.id"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # text|table|row|cell|record|region
    locator: Mapped[dict] = mapped_column(JSONB, nullable=False)  # {page,bbox} | {sheet,cell_range} | {row,columns} | {record,field}
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = created_at()


class EvidenceChunk(TenantMixin, Base):
    """Retrieval unit: one or more spans with lexical and vector indexes."""

    __tablename__ = "evidence_chunks"
    id: Mapped[uuid.UUID] = uuid_pk()
    document_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("document_versions.id"), nullable=False, index=True)
    span_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    tsv: Mapped[str | None] = mapped_column(TSVECTOR)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    embedding_model: Mapped[str | None] = mapped_column(String(100))
    __table_args__ = (
        Index("ix_evidence_chunks_tsv", "tsv", postgresql_using="gin"),
        Index("ix_evidence_chunks_tags", "tags", postgresql_using="gin"),
    )


# --------------------------------------------------------------------------- engineering records

class Equipment(TenantMixin, Base):
    __tablename__ = "equipment"
    id: Mapped[uuid.UUID] = uuid_pk()
    raw_tag: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_tag: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    equipment_type: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    location: Mapped[str | None] = mapped_column(String(200))
    document_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    evidence_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list, nullable=False)
    created_at: Mapped[datetime] = created_at()
    # Note: no unique constraint on normalized_tag by design — duplicate tags are a finding, not a rejected row.


class Assertion(TenantMixin, Base):
    __tablename__ = "assertions"
    id: Mapped[uuid.UUID] = uuid_pk()
    equipment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("equipment.id"), nullable=False, index=True)
    attribute: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(40))
    value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    unit_canonical: Mapped[str | None] = mapped_column(String(40))
    value_canonical: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    evidence_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(20), nullable=False)  # structured|model|engineer
    review_status: Mapped[str] = mapped_column(String(20), default="recorded", nullable=False)  # recorded|candidate|verified|rejected
    created_at: Mapped[datetime] = created_at()


class Relationship(TenantMixin, Base):
    __tablename__ = "relationships"
    id: Mapped[uuid.UUID] = uuid_pk()
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("equipment.id"), nullable=False, index=True)
    target_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("equipment.id"), nullable=False, index=True)
    relationship_type: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list, nullable=False)
    document_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(20), default="recorded", nullable=False)  # recorded|verified|candidate|disputed
    created_at: Mapped[datetime] = created_at()


class UnresolvedReference(TenantMixin, Base):
    """A tag mentioned in a document that matched no equipment row."""

    __tablename__ = "unresolved_references"
    id: Mapped[uuid.UUID] = uuid_pk()
    raw_tag: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_tag: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    document_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evidence_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list, nullable=False)


class Snapshot(TenantMixin, Base):
    __tablename__ = "snapshots"
    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    document_version_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = created_at()


class CataloguePart(TenantMixin, Base):
    __tablename__ = "catalogue_parts"
    id: Mapped[uuid.UUID] = uuid_pk()
    part_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    document_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    evidence_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list, nullable=False)


class Rate(TenantMixin, Base):
    __tablename__ = "rates"
    id: Mapped[uuid.UUID] = uuid_pk()
    rate_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    rate_set_version: Mapped[str] = mapped_column(String(60), nullable=False)
    document_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    evidence_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list, nullable=False)


class EngineerDecision(TenantMixin, Base):
    """An explicit engineer resolution of a conflict or candidate, with supporting evidence."""

    __tablename__ = "engineer_decisions"
    id: Mapped[uuid.UUID] = uuid_pk()
    subject_type: Mapped[str] = mapped_column(String(30), nullable=False)  # assertion_conflict|relationship|finding|assumption
    subject_key: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, default="", nullable=False)
    evidence_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list, nullable=False)
    decided_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = created_at()


# --------------------------------------------------------------------------- investigations

class ChangeRequest(TenantMixin, Base):
    __tablename__ = "change_requests"
    id: Mapped[uuid.UUID] = uuid_pk()
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    request_text: Mapped[str] = mapped_column(Text, nullable=False)
    target_tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    assumptions: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = created_at()


class Run(TenantMixin, Base):
    __tablename__ = "runs"
    id: Mapped[uuid.UUID] = uuid_pk()
    change_request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("change_requests.id"), nullable=False, index=True)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("snapshots.id"), nullable=False)
    state: Mapped[str] = mapped_column(String(30), default="queued", nullable=False)
    eve_session_id: Mapped[str | None] = mapped_column(String(100), index=True)
    stream_cursor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    model_config_: Mapped[dict] = mapped_column("model_config", JSONB, default=dict, nullable=False)
    tool_invocations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    clarification_cycles: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_tokens: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"), nullable=False)
    active_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = created_at()


class RunEvent(TenantMixin, Base):
    __tablename__ = "run_events"
    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    at: Mapped[datetime] = created_at()
    __table_args__ = (UniqueConstraint("run_id", "sequence"),)


class Clarification(TenantMixin, Base):
    __tablename__ = "clarifications"
    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id"), nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text)
    interaction_id: Mapped[str | None] = mapped_column(String(100))
    asked_at: Mapped[datetime] = created_at()
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    answered_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class Finding(TenantMixin, Base):
    __tablename__ = "findings"
    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id"), nullable=False, index=True)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    affected_equipment_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list, nullable=False)
    evidence_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list, nullable=False)
    basis: Mapped[str] = mapped_column(String(30), nullable=False)
    rule_id: Mapped[str | None] = mapped_column(String(60))
    open_questions: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    review_status: Mapped[str] = mapped_column(String(20), default="unreviewed", nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(300), nullable=False)
    created_at: Mapped[datetime] = created_at()
    __table_args__ = (UniqueConstraint("run_id", "dedupe_key"),)


class WorkItem(TenantMixin, Base):
    __tablename__ = "work_items"
    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id"), nullable=False, index=True)
    template_id: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    equipment_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list, nullable=False)
    finding_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list, nullable=False)
    evidence_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list, nullable=False)
    labour: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)  # [{rate_code, hours, basis}]
    parts: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False)  # [{part_number|None, description, quantity, unit}]
    assumption_status: Mapped[str] = mapped_column(String(20), default="assumed", nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(300), nullable=False)
    __table_args__ = (UniqueConstraint("run_id", "dedupe_key"),)


class Estimate(TenantMixin, Base):
    __tablename__ = "estimates"
    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id"), nullable=False, index=True)
    rate_set_version: Mapped[str] = mapped_column(String(60), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    complete: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = created_at()


class ChecklistItem(TenantMixin, Base):
    __tablename__ = "checklist_items"
    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id"), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(300), nullable=False)
    __table_args__ = (UniqueConstraint("run_id", "dedupe_key"),)


class Report(TenantMixin, Base):
    __tablename__ = "reports"
    id: Mapped[uuid.UUID] = uuid_pk()
    change_request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("change_requests.id"), nullable=False, unique=True)
    created_at: Mapped[datetime] = created_at()


class ReportVersion(TenantMixin, Base):
    __tablename__ = "report_versions"
    id: Mapped[uuid.UUID] = uuid_pk()
    report_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reports.id"), nullable=False, index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id"), nullable=False)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    package: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    stale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    stale_reason: Mapped[str | None] = mapped_column(Text)
    export_key: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = created_at()
    __table_args__ = (UniqueConstraint("report_id", "version_no"), UniqueConstraint("run_id"))


class Review(TenantMixin, Base):
    __tablename__ = "reviews"
    id: Mapped[uuid.UUID] = uuid_pk()
    report_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("report_versions.id"), nullable=False, index=True)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)  # approved|changes_requested|rejected
    comment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    item_decisions: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)  # finding/checklist id -> decision
    created_at: Mapped[datetime] = created_at()


# --------------------------------------------------------------------------- operations

class ModelCall(Base):
    """Usage ledger. No tenant mixin so cost roll-ups can run org-wide for the budget guard."""

    __tablename__ = "model_calls"
    id: Mapped[uuid.UUID] = uuid_pk()
    org_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(60))
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ok: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    at: Mapped[datetime] = created_at()


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[uuid.UUID] = uuid_pk()
    org_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(40), nullable=False)
    subject_id: Mapped[str | None] = mapped_column(String(100))
    meta: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    at: Mapped[datetime] = created_at()


class JobQueue(Base):
    """Postgres-backed queue for local development (QUEUE_BACKEND=postgres). Mirrors SQS semantics:
    at-least-once delivery, visibility timeout, retries, dead-letter after max attempts."""

    __tablename__ = "job_queue"
    id: Mapped[uuid.UUID] = uuid_pk()
    queue: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)  # queued|in_flight|done|dead
    available_at: Mapped[datetime] = created_at()
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(100))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()


class ProcessedJob(Base):
    """Idempotency ledger for pipeline stages: (document_version, stage, pipeline_version)."""

    __tablename__ = "processed_jobs"
    key: Mapped[str] = mapped_column(String(300), primary_key=True)
    result: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    at: Mapped[datetime] = created_at()


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    key: Mapped[str] = mapped_column(String(300), primary_key=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    route: Mapped[str] = mapped_column(String(200), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = created_at()


TENANT_TABLES = [
    m.__tablename__
    for m in Base.__subclasses__()
    if issubclass(m, TenantMixin)
]
