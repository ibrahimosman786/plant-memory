"""resolve_equipment: exact tag match first, then loose/prefix matches. Ambiguity is returned,
never resolved by guessing."""

from __future__ import annotations

from ..contracts import ToolResult
from ..ingestion.normalize import normalize_tag, LOOSE_TAG_RE
from .context import SnapshotContext


def equipment_summary(eq) -> dict:
    return {"id": str(eq.id), "tag": eq.normalized_tag, "raw_tag": eq.raw_tag, "type": eq.equipment_type, "description": eq.description, "location": eq.location,
            "evidence_ids": [str(e) for e in eq.evidence_ids]}


def resolve_equipment(ctx: SnapshotContext, query: str) -> ToolResult:
    query = (query or "").strip()
    if not query:
        return ctx.result({"matches": [], "query": query}, status="failed", unresolved=[{"code": "empty_query", "message": "no tag supplied"}])
    equipment = ctx.equipment()
    norm = normalize_tag(query)
    exact = [e for e in equipment if norm and e.normalized_tag == norm]
    loose: list = []
    if norm:
        # Loose: same prefix+number, different suffix (PT-103A vs PT-103A1), or the query is a prefix.
        base = LOOSE_TAG_RE.fullmatch(query)
        stem = f"{base.group(1).upper()}-{base.group(2)}" if base else norm
        loose = [e for e in equipment if e.normalized_tag.startswith(stem) and e not in exact]
    else:
        q = query.lower()
        loose = [e for e in equipment if q in e.normalized_tag.lower() or q in (e.description or "").lower()]

    duplicates = len(exact) > 1
    loose_spelling = bool(norm) and query.upper().replace(" ", "") != norm.replace("-", "") and query.upper() != norm
    ambiguous = duplicates or (loose_spelling and len(loose) > 0) or (not exact and len(loose) > 1)
    data = {
        "query": query,
        "normalized": norm,
        "exact_matches": [equipment_summary(e) for e in exact],
        "loose_matches": [equipment_summary(e) for e in loose[:10]],
        "ambiguous": ambiguous,
        "ambiguity_reason": (
            "duplicate tag entries in the project" if duplicates else
            "loose spelling matches more than one equipment item" if loose_spelling and loose else
            "no exact match; several similar tags" if not exact and len(loose) > 1 else None
        ),
    }
    evidence = [eid for e in exact + loose[:10] for eid in e.evidence_ids]
    if not exact and not loose:
        return ctx.result(data, status="partial", evidence_ids=evidence, unresolved=[{"code": "no_match", "message": f"no equipment matches '{query}' in this snapshot", "subject": query}])
    if ambiguous:
        return ctx.result(data, status="partial", evidence_ids=evidence, warnings=["ambiguous identifier; ask the engineer to confirm which equipment is meant"],
                          unresolved=[{"code": "ambiguous_identifier", "message": data["ambiguity_reason"], "subject": query}])
    return ctx.result(data, evidence_ids=evidence)
