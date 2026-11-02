"""search_evidence: exact tag lookup → lexical → vector, fused with reciprocal rank fusion.

Defaults (section 7): 20 lexical + 20 vector candidates, dedupe, up to 12 passages returned.
Exact tag matches always rank first. Snapshot and project filters apply inside SQL.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text

from ..config import get_settings
from ..contracts import ToolResult
from ..db.models import EvidenceSpan
from ..embeddings import get_embedder
from ..ingestion.normalize import find_tags, normalize_tag
from .context import SnapshotContext


def search_evidence(ctx: SnapshotContext, query: str, *, kinds: list[str] | None = None, tags: list[str] | None = None, limit: int | None = None) -> ToolResult:
    s = get_settings()
    limit = min(limit or s.search_passages_to_model, 30)
    query = (query or "").strip()
    if not query and not tags:
        return ctx.result({"passages": [], "query": query}, status="failed", unresolved=[{"code": "empty_query", "message": "query or tags required"}])
    if not ctx.version_ids:
        return ctx.result({"passages": [], "query": query}, status="blocked", unresolved=[{"code": "empty_snapshot", "message": "snapshot has no documents"}])

    version_list = [str(v) for v in ctx.version_ids]
    params = {"project": str(ctx.project_id), "versions": version_list}
    kind_filter = ""
    if kinds:
        kind_filter = " AND d.kind = ANY(:kinds)"
        params["kinds"] = kinds

    base_from = """
        FROM evidence_chunks c
        JOIN document_versions v ON v.id = c.document_version_id
        JOIN documents d ON d.id = v.document_id
        WHERE c.project_id = CAST(:project AS uuid) AND c.document_version_id = ANY(CAST(:versions AS uuid[]))
    """ + kind_filter

    ranked: dict[str, float] = {}
    sources: dict[str, set[str]] = {}

    def add(rows, source: str, weight: float = 1.0):
        for rank, row in enumerate(rows, start=1):
            cid = str(row[0])
            ranked[cid] = ranked.get(cid, 0.0) + weight / (60 + rank)
            sources.setdefault(cid, set()).add(source)

    # 1) exact tag matches
    mention_tags = sorted({n for _, n in find_tags(query.upper())} | {normalize_tag(t) for t in (tags or []) if normalize_tag(t)})
    if mention_tags:
        rows = ctx.s.execute(text(f"SELECT c.id {base_from} AND c.tags && CAST(:tags AS text[]) LIMIT :n"), {**params, "tags": mention_tags, "n": s.search_lexical_candidates}).fetchall()
        add(rows, "exact_tag", weight=3.0)

    # 2) lexical
    if query:
        rows = ctx.s.execute(
            text(f"SELECT c.id, ts_rank_cd(c.tsv, websearch_to_tsquery('english', :q)) AS r {base_from} AND c.tsv @@ websearch_to_tsquery('english', :q) ORDER BY r DESC LIMIT :n"),
            {**params, "q": query, "n": s.search_lexical_candidates},
        ).fetchall()
        add(rows, "lexical")

        # 3) vector
        vec = get_embedder().embed([query])[0]
        rows = ctx.s.execute(
            text(f"SELECT c.id, (c.embedding <=> CAST(:vec AS vector)) AS dist {base_from} AND c.embedding IS NOT NULL ORDER BY dist ASC LIMIT :n"),
            {**params, "vec": "[" + ",".join(f"{x:.6f}" for x in vec) + "]", "n": s.search_vector_candidates},
        ).fetchall()
        add(rows, "vector")

    ordered = sorted(ranked.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    if not ordered:
        return ctx.result({"passages": [], "query": query, "tags": mention_tags}, status="complete", warnings=["no passages matched; absence of evidence is not evidence of absence"])

    chunk_ids = [uuid.UUID(cid) for cid, _ in ordered]
    rows = ctx.s.execute(
        text("SELECT c.id, c.text, c.span_ids, c.document_version_id, c.tags FROM evidence_chunks c WHERE c.id = ANY(CAST(:ids AS uuid[]))"),
        {"ids": [str(c) for c in chunk_ids]},
    ).fetchall()
    by_id = {str(r[0]): r for r in rows}
    passages = []
    evidence_ids: list[str] = []
    for cid, score in ordered:
        r = by_id.get(cid)
        if not r:
            continue
        span_ids = list(r[2] or [])
        spans = ctx.s.query(EvidenceSpan).filter(EvidenceSpan.id.in_(span_ids)).order_by(EvidenceSpan.seq).all() if span_ids else []
        first = spans[0] if spans else None
        passages.append({
            "chunk_id": cid,
            "score": round(score, 5),
            "matched_by": sorted(sources.get(cid, [])),
            "source": ctx.source_label(r[3]),
            "document_version_id": str(r[3]),
            "evidence_ids": [str(x) for x in span_ids],
            "locator": first.locator if first else {},
            "tags": list(r[4] or []),
            "text": r[1][:1500],
        })
        evidence_ids.extend(str(x) for x in span_ids)
    return ctx.result({"passages": passages, "query": query, "tags": mention_tags, "embedding_model": get_embedder().name}, evidence_ids=evidence_ids)
