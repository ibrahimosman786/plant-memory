"""build_work_scope: findings + templates → draft work items. Also run_consistency_checks and
lookup_catalogue tool implementations."""

from __future__ import annotations

import uuid
from collections import Counter

from sqlalchemy import select

from ..contracts import ToolResult
from ..db.models import CataloguePart, Finding, Run, WorkItem
from .context import SnapshotContext
from .rules import FindingDraft, run_rules, price_expired
from .templates import WORK_TEMPLATES, templates_for_types


def persist_findings(ctx: SnapshotContext, run: Run, drafts: list[FindingDraft]) -> list[Finding]:
    existing = {f.dedupe_key: f for f in ctx.s.execute(select(Finding).where(Finding.run_id == run.id)).scalars().all()}
    out = []
    for d in drafts:
        if d.dedupe_key in existing:
            out.append(existing[d.dedupe_key])
            continue
        f = Finding(org_id=ctx.org_id, project_id=ctx.project_id, run_id=run.id, snapshot_id=ctx.snapshot_id, type=d.type, severity=d.severity, title=d.title[:200],
                    summary=d.summary[:2000], affected_equipment_ids=d.affected_equipment_ids, evidence_ids=list(dict.fromkeys(d.evidence_ids)), basis=d.basis,
                    rule_id=d.rule_id, open_questions=d.open_questions, dedupe_key=d.dedupe_key[:300])
        ctx.s.add(f)
        out.append(f)
    ctx.s.flush()
    return out


def finding_out(f: Finding) -> dict:
    return {"id": str(f.id), "type": f.type, "severity": f.severity, "title": f.title, "summary": f.summary,
            "affected_equipment_ids": [str(e) for e in f.affected_equipment_ids], "evidence_ids": [str(e) for e in f.evidence_ids],
            "basis": f.basis, "rule_id": f.rule_id, "open_questions": list(f.open_questions), "review_status": f.review_status}


def run_consistency_checks(ctx: SnapshotContext, run: Run, scope_ids: list[str]) -> ToolResult:
    try:
        ids = [uuid.UUID(x) for x in scope_ids] if scope_ids else None
    except ValueError:
        return ctx.result({}, status="failed", unresolved=[{"code": "bad_id", "message": "scope ids must be UUIDs"}])
    drafts, errors = run_rules(ctx, ids)
    if ids is not None and not drafts:
        tags = ", ".join(e.normalized_tag for e in ctx.equipment_by_id(ids).values())
        drafts.append(FindingDraft("no_relevant_finding", "info", "No consistency findings for the affected scope",
                                   f"The rule catalogue produced no findings for {tags or 'the affected scope'} in this snapshot. This means no recorded inconsistency was detected; it does not certify the records are complete.",
                                   ids, [], "R012", dedupe_key="R012"))
    findings = persist_findings(ctx, run, drafts)
    status = "partial" if errors else "complete"
    ev = [e for f in findings for e in f.evidence_ids]
    by_sev = Counter(f.severity for f in findings)
    return ctx.result({"findings": [finding_out(f) for f in findings], "counts": dict(by_sev), "rules_version": run_rules.__module__},
                      status=status, evidence_ids=ev, warnings=errors)


def lookup_catalogue(ctx: SnapshotContext, *, part_number: str | None = None, category: str | None = None, attributes: dict | None = None) -> ToolResult:
    q = select(CataloguePart).where(CataloguePart.project_id == ctx.project_id)
    if part_number:
        q = q.where(CataloguePart.part_number == part_number)
    if category:
        q = q.where(CataloguePart.category == category)
    parts = ctx.s.execute(q).scalars().all()
    attributes = attributes or {}
    results = []
    missing = []
    for p in parts:
        mismatches = [k for k, v in attributes.items() if k in p.attributes and str(p.attributes[k]).lower() != str(v).lower()]
        unknown = [k for k in attributes if k not in p.attributes]
        results.append({
            "id": str(p.id), "part_number": p.part_number, "description": p.description, "category": p.category, "attributes": p.attributes,
            "unit_price": str(p.unit_price) if p.unit_price is not None else None, "currency": p.currency, "effective_date": p.effective_date.isoformat(),
            "price_status": "unpriced" if p.unit_price is None else ("expired" if price_expired(p.effective_date) else "priced"),
            "source": p.source, "attribute_mismatches": mismatches, "attributes_not_recorded": unknown, "evidence_ids": [str(e) for e in p.evidence_ids],
        })
        if p.unit_price is None:
            missing.append({"code": "unpriced", "message": f"{p.part_number} has no price in the catalogue", "subject": p.part_number})
        for k in unknown:
            missing.append({"code": "attribute_not_recorded", "message": f"{p.part_number}: catalogue does not record '{k}'", "subject": p.part_number})
    if not results:
        return ctx.result({"candidates": [], "query": {"part_number": part_number, "category": category, "attributes": attributes}}, status="partial",
                          unresolved=[{"code": "no_catalogue_match", "message": "no catalogue entry matches; part is unpriced scope"}])
    return ctx.result({"candidates": results}, evidence_ids=[e for p in parts for e in p.evidence_ids], unresolved=missing, status="complete" if not missing else "partial")


def build_work_scope(ctx: SnapshotContext, run: Run, *, target_equipment_ids: list[str], affected_equipment_ids: list[str], finding_ids: list[str],
                     template_ids: list[str] | None = None, change_kind: str | None = None) -> ToolResult:
    try:
        targets = [uuid.UUID(x) for x in target_equipment_ids]
        affected = [uuid.UUID(x) for x in affected_equipment_ids]
        f_ids = [uuid.UUID(x) for x in finding_ids]
    except ValueError:
        return ctx.result({}, status="failed", unresolved=[{"code": "bad_id", "message": "ids must be UUIDs"}])
    eq_map = ctx.equipment_by_id(targets + affected)
    missing = [str(t) for t in targets if t not in eq_map]
    if missing:
        return ctx.result({"missing": missing}, status="failed", unresolved=[{"code": "unknown_equipment", "message": "target not in snapshot"}])
    findings = ctx.s.execute(select(Finding).where(Finding.run_id == run.id, Finding.id.in_(f_ids))).scalars().all() if f_ids else []
    target_types = {eq_map[t].equipment_type for t in targets}

    if template_ids:
        templates = [WORK_TEMPLATES[t] for t in template_ids if t in WORK_TEMPLATES]
    else:
        templates = templates_for_types(target_types)
        if change_kind == "rerange":
            templates = [WORK_TEMPLATES["WT-RERANGE"]]
        elif change_kind == "like_for_like":
            templates = [WORK_TEMPLATES["WT-VALVE-LIKE-FOR-LIKE"]] if target_types & set(WORK_TEMPLATES["WT-VALVE-LIKE-FOR-LIKE"].applies_to_types) else templates
    warnings = []
    if not templates:
        templates = [WORK_TEMPLATES["WT-GENERIC"]]
        warnings.append("no template matched the target equipment types; a scoping allowance was added")

    # Counts for per-unit labour/parts: I/O points and cards among affected scope.
    all_eq = list(eq_map.values())
    cards = [e for e in all_eq if e.equipment_type.endswith("_card")]
    instruments = [e for e in all_eq if e.equipment_type.endswith("_transmitter") or e.equipment_type in ("analyzer",)]
    io_points = [e for e in all_eq if e.id in {a.equipment_id for a in ctx.assertions([x.id for x in all_eq], attributes=["channel"])}]
    counts = {"job": 1, "io_point": max(len(io_points), 0), "card": len(cards), "instrument": len(instruments), "finding": len(findings)}

    existing = {w.dedupe_key: w for w in ctx.s.execute(select(WorkItem).where(WorkItem.run_id == run.id)).scalars().all()}
    items: list[WorkItem] = []
    for t in templates:
        key = f"{t.id}:{','.join(sorted(str(x) for x in targets))}"
        if key in existing:
            items.append(existing[key])
            continue
        labour = []
        for l in t.labour:
            n = counts.get(l.per, 1)
            if n == 0:
                continue
            labour.append({"rate_code": l.rate_code, "description": l.description, "per": l.per, "count": n, "unit": l.unit,
                           "hours_low": l.hours_low * n, "hours_base": l.hours_base * n, "hours_high": l.hours_high * n, "basis": f"template {t.id} {t.version}"})
        parts = []
        for p in t.parts:
            n = counts.get(p.quantity_per, 1)
            if n == 0:
                continue
            parts.append({"description": p.description, "part_number": p.part_number, "category": p.category, "quantity": p.quantity * n, "unit": "ea",
                          "reuse_candidate": p.reuse_candidate, "optional": p.optional, "equipment_ids": [str(c.id) for c in cards] if p.quantity_per == "card" else []})
        wi = WorkItem(org_id=ctx.org_id, project_id=ctx.project_id, run_id=run.id, template_id=t.id, title=t.title, description=t.description,
                      equipment_ids=targets + [a for a in affected if a not in targets], finding_ids=[f.id for f in findings], evidence_ids=[],
                      labour=labour, parts=parts, assumption_status="assumed", dedupe_key=key[:300])
        ctx.s.add(wi)
        items.append(wi)
    # Conflict-resolution effort per actionable finding
    actionable = [f for f in findings if f.severity in ("high", "medium") and f.basis == "rule"]
    if actionable and "WT-RECORD-CONFLICT" not in {i.template_id for i in items}:
        key = f"WT-RECORD-CONFLICT:{run.id}"
        if key not in existing:
            t = WORK_TEMPLATES["WT-RECORD-CONFLICT"]
            l = t.labour[0]
            n = len(actionable)
            wi = WorkItem(org_id=ctx.org_id, project_id=ctx.project_id, run_id=run.id, template_id=t.id, title=f"{t.title} ({n} findings)", description=t.description,
                          equipment_ids=[e for f in actionable for e in f.affected_equipment_ids], finding_ids=[f.id for f in actionable], evidence_ids=[e for f in actionable for e in f.evidence_ids],
                          labour=[{"rate_code": l.rate_code, "description": l.description, "per": "finding", "count": n, "unit": "hour", "hours_low": l.hours_low * n, "hours_base": l.hours_base * n, "hours_high": l.hours_high * n, "basis": f"template {t.id}"}],
                          parts=[], dedupe_key=key)
            ctx.s.add(wi)
            items.append(wi)
        else:
            items.append(existing[key])
    ctx.s.flush()
    reuse = [{"equipment_id": str(c.id), "tag": c.normalized_tag, "basis": "template lists existing cards/enclosure/power supply as reuse candidates; compatibility unverified"} for c in cards]
    return ctx.result({"work_items": [work_item_out(w) for w in items], "counts": counts, "templates": [t.id for t in templates], "reuse_candidates": reuse},
                      warnings=warnings + ["labour hours are template assumptions, not calibrated actuals"])


def work_item_out(w: WorkItem) -> dict:
    return {"id": str(w.id), "template_id": w.template_id, "title": w.title, "description": w.description, "equipment_ids": [str(e) for e in w.equipment_ids],
            "finding_ids": [str(e) for e in w.finding_ids], "labour": w.labour, "parts": w.parts, "assumption_status": w.assumption_status}
