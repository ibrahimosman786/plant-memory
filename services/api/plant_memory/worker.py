"""Ingestion worker: pulls jobs from the queue (Postgres SKIP LOCKED locally, SQS in AWS) and
runs the idempotent pipeline. Run with `python -m plant_memory.worker`."""

from __future__ import annotations

import logging
import signal
import time
import uuid

from .config import get_settings
from .ingestion.pipeline import process_document_version
from .queue import get_queue

log = logging.getLogger("plant_memory.worker")
_stop = False


def _handle(sig, frame):
    global _stop
    _stop = True


def handle_message(msg) -> None:
    p = msg.payload
    if msg.job == "ingest":
        summary = process_document_version(uuid.UUID(p["version_id"]), uuid.UUID(p["org_id"]), uuid.UUID(p["project_id"]))
        log.info("ingested %s -> %s", p["version_id"], summary.get("status"))
    else:
        raise ValueError(f"unknown job {msg.job}")


def run_forever(poll_seconds: float = 1.0) -> None:
    logging.basicConfig(level=get_settings().log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)
    q = get_queue()
    log.info("worker started (queue backend %s)", get_settings().queue_backend)
    while not _stop:
        msgs = q.receive(max_messages=1, visibility_seconds=600)
        if not msgs:
            time.sleep(poll_seconds)
            continue
        for m in msgs:
            try:
                handle_message(m)
                q.ack(m)
            except Exception as exc:
                log.exception("job %s failed", m.id)
                _mark_failed(m, exc)
                q.nack(m, str(exc)[:500])


def _mark_failed(msg, exc: Exception) -> None:
    """Surface the failure on the document version so the UI never shows a silent 'processing'."""
    from .db.models import DocumentVersion
    from .db.session import TenantScope, scoped_session
    p = msg.payload
    try:
        with scoped_session(TenantScope(uuid.UUID(p["org_id"]), (uuid.UUID(p["project_id"]),))) as s:
            v = s.get(DocumentVersion, uuid.UUID(p["version_id"]))
            if v:
                v.status = "failed" if msg.attempts >= 4 else "processing"
                detail = dict(v.status_detail or {})
                detail["last_error"] = str(exc)[:500]
                detail["attempts"] = msg.attempts
                v.status_detail = detail
                s.commit()
    except Exception:
        log.exception("could not record failure for %s", p.get("version_id"))


def drain_once() -> int:
    """Process everything currently queued, then return. Used by tests and `make ingest`."""
    q = get_queue()
    n = 0
    while True:
        msgs = q.receive(max_messages=5, visibility_seconds=600)
        if not msgs:
            return n
        for m in msgs:
            try:
                handle_message(m)
                q.ack(m)
                n += 1
            except Exception as exc:
                log.exception("job %s failed", m.id)
                _mark_failed(m, exc)
                q.nack(m, str(exc)[:500])


if __name__ == "__main__":
    run_forever()
