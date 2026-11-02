"""Chunking and indexing of evidence spans for hybrid retrieval.

- Rows/records/tables are indexed whole (one chunk each) so headers stay with values.
- Prose lines on a page are grouped into ~600-character chunks, well inside the embedding
  model's 512-token input limit.
- Every chunk carries the normalized tags it mentions for exact-match boosting.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from ..db.models import EvidenceChunk, EvidenceSpan
from ..embeddings import get_embedder
from .normalize import find_tags

CHUNK_CHARS = 600


def build_chunks(spans: list[EvidenceSpan]) -> list[tuple[list[uuid.UUID], str]]:
    chunks: list[tuple[list[uuid.UUID], str]] = []
    buf_ids: list[uuid.UUID] = []
    buf_text: list[str] = []
    buf_page = None

    def flush():
        nonlocal buf_ids, buf_text
        if buf_ids:
            chunks.append((buf_ids, "\n".join(buf_text)))
        buf_ids, buf_text = [], []

    for sp in sorted(spans, key=lambda s: s.seq):
        if sp.kind in ("row", "record", "table", "region"):
            flush()
            chunks.append(([sp.id], sp.text))
            continue
        page = sp.locator.get("page") or sp.locator.get("paragraph")
        if buf_page is not None and page != buf_page and sp.locator.get("page") is not None:
            flush()
        buf_page = page
        if sum(len(t) for t in buf_text) + len(sp.text) > CHUNK_CHARS:
            flush()
        buf_ids.append(sp.id)
        buf_text.append(sp.text)
    flush()
    return chunks


def index_version(session: Session, *, org_id: uuid.UUID, project_id: uuid.UUID, version_id: uuid.UUID, spans: list[EvidenceSpan]) -> int:
    chunks = build_chunks(spans)
    if not chunks:
        return 0
    embedder = get_embedder()
    vectors = embedder.embed([t for _, t in chunks])
    for (span_ids, text), vec in zip(chunks, vectors):
        tags = sorted({n for _, n in find_tags(text)})
        session.add(EvidenceChunk(org_id=org_id, project_id=project_id, document_version_id=version_id, span_ids=span_ids, text=text, tags=tags,
                                  embedding=vec, embedding_model=embedder.name))
    return len(chunks)
