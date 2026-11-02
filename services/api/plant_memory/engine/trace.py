"""trace_dependencies: bounded recursive traversal with cycle detection and a visible truncation flag.

Separate views: recorded, engineer-verified, candidate, and missing/disputed links.
Default depth 3, maximum 6. Traverses both directions (what feeds X, what X feeds).
"""

from __future__ import annotations

import uuid

from sqlalchemy import text

from ..config import get_settings
from ..contracts import ToolResult
from .context import SnapshotContext
from .resolve import equipment_summary

TRAVERSAL_SQL = """
WITH RECURSIVE walk(node_id, depth, path, via_rel, status) AS (
    SELECT CAST(:start AS uuid), 0, ARRAY[CAST(:start AS uuid)], NULL::uuid, NULL::text
  UNION ALL
    SELECT CASE WHEN r.source_id = w.node_id THEN r.target_id ELSE r.source_id END,
           w.depth + 1,
           w.path || (CASE WHEN r.source_id = w.node_id THEN r.target_id ELSE r.source_id END),
           r.id,
           r.status
    FROM walk w
    JOIN relationships r ON (r.source_id = w.node_id OR r.target_id = w.node_id)
    WHERE w.depth < :depth
      AND r.project_id = CAST(:project AS uuid)
      AND (r.document_version_id = ANY(CAST(:versions AS uuid[])) OR r.document_version_id IS NULL)
      AND r.status <> 'disputed'
      AND NOT ((CASE WHEN r.source_id = w.node_id THEN r.target_id ELSE r.source_id END) = ANY(w.path))
)
SELECT node_id, MIN(depth) AS depth FROM walk GROUP BY node_id
"""


def trace_dependencies(ctx: SnapshotContext, equipment_ids: list[str], depth: int | None = None) -> ToolResult:
    s = get_settings()
    depth = max(1, min(depth or s.trace_default_depth, s.trace_max_depth))
    try:
        start_ids = [uuid.UUID(e) for e in equipment_ids]
    except ValueError:
        return ctx.result({}, status="failed", unresolved=[{"code": "bad_id", "message": "equipment_ids must be UUIDs"}])
    known = ctx.equipment_by_id(start_ids)
    missing = [str(e) for e in start_ids if e not in known]
    if missing:
        return ctx.result({"missing": missing}, status="failed", unresolved=[{"code": "unknown_equipment", "message": "equipment not in snapshot", "subject": ",".join(missing)}])

    reached: dict[uuid.UUID, int] = {}
    for sid in start_ids:
        rows = ctx.s.execute(text(TRAVERSAL_SQL), {"start": str(sid), "depth": depth, "project": str(ctx.project_id), "versions": [str(v) for v in ctx.version_ids]}).fetchall()
        for node_id, d in rows:
            reached[node_id] = min(d, reached.get(node_id, 99))

    # Was anything cut off at the depth limit? Probe one level further.
    truncated = False
    frontier = [n for n, d in reached.items() if d == depth]
    if frontier:
        probe = ctx.s.execute(text("""
            SELECT COUNT(*) FROM relationships r
            WHERE r.project_id = CAST(:project AS uuid)
              AND (r.document_version_id = ANY(CAST(:versions AS uuid[])) OR r.document_version_id IS NULL)
              AND r.status <> 'disputed'
              AND (r.source_id = ANY(CAST(:frontier AS uuid[])) OR r.target_id = ANY(CAST(:frontier AS uuid[])))
              AND NOT (r.source_id = ANY(CAST(:reached AS uuid[])) AND r.target_id = ANY(CAST(:reached AS uuid[])))
        """), {"project": str(ctx.project_id), "versions": [str(v) for v in ctx.version_ids], "frontier": [str(f) for f in frontier], "reached": [str(r) for r in reached]}).scalar_one()
        truncated = probe > 0

    rels = [r for r in ctx.relationships() if r.source_id in reached and r.target_id in reached]
    eq_map = ctx.equipment_by_id(list(reached.keys()))
    nodes = [{**equipment_summary(eq_map[n]), "depth": d} for n, d in sorted(reached.items(), key=lambda kv: kv[1]) if n in eq_map]
    edges = [{"id": str(r.id), "source_id": str(r.source_id), "target_id": str(r.target_id), "type": r.relationship_type, "status": r.status,
              "evidence_ids": [str(e) for e in r.evidence_ids], "source": ctx.source_label(r.document_version_id) if r.document_version_id else "placeholder"} for r in rels]
    views = {
        "recorded": [e["id"] for e in edges if e["status"] == "recorded"],
        "verified": [e["id"] for e in edges if e["status"] == "verified"],
        "candidate": [e["id"] for e in edges if e["status"] == "candidate"],
    }
    unresolved_links = [{"raw_tag": u.raw_tag, "normalized_tag": u.normalized_tag, "evidence_ids": [str(e) for e in u.evidence_ids], "source": ctx.source_label(u.document_version_id)}
                        for u in ctx.unresolved_references()]
    warnings = []
    if truncated:
        warnings.append(f"traversal truncated at depth {depth}; request a deeper trace if the upgrade may reach further")
    if views["candidate"]:
        warnings.append(f"{len(views['candidate'])} candidate relationships included; they are not engineer-verified")
    evidence = [e for r in rels for e in r.evidence_ids]
    return ctx.result({"depth": depth, "truncated": truncated, "nodes": nodes, "edges": edges, "views": views, "unresolved_links": unresolved_links,
                       "affected_equipment_ids": [str(n) for n in reached if n not in start_ids]}, status="partial" if truncated else "complete",
                      evidence_ids=evidence, warnings=warnings)
