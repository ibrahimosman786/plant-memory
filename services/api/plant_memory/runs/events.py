"""Run events: persisted, monotonically sequenced per run, streamed to the UI via SSE."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import Run, RunEvent


def next_sequence(session: Session, run_id: uuid.UUID) -> int:
    cur = session.execute(select(func.max(RunEvent.sequence)).where(RunEvent.run_id == run_id)).scalar()
    return 0 if cur is None else cur + 1


def emit(session: Session, run: Run, type_: str, payload: dict) -> RunEvent:
    ev = RunEvent(org_id=run.org_id, project_id=run.project_id, run_id=run.id, sequence=next_sequence(session, run.id), type=type_, payload=payload)
    session.add(ev)
    session.flush()
    return ev


def event_out(ev: RunEvent) -> dict:
    return {"id": str(ev.id), "run_id": str(ev.run_id), "sequence": ev.sequence, "type": ev.type, "at": ev.at.isoformat(), "payload": ev.payload}


def events_after(session: Session, run_id: uuid.UUID, after: int = -1, limit: int = 500) -> list[RunEvent]:
    return session.execute(select(RunEvent).where(RunEvent.run_id == run_id, RunEvent.sequence > after).order_by(RunEvent.sequence).limit(limit)).scalars().all()
