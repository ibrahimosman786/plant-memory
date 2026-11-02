"""Deterministic Decimal estimator (section 12.4).

Rules:
- Every line carries origin, pricing_status, assumption_status, classification.
- Unpriced or expired lines are never summed into priced_subtotal; they are listed.
- Scenario totals (low/base/high) are only emitted when every included line is priced.
- Expired prices make the estimate incomplete and raise an expired_price finding draft.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select

from ..contracts import ToolResult
from ..db.models import CataloguePart, Estimate, Rate, Run, WorkItem
from .context import SnapshotContext
from .rules import FindingDraft, price_expired
from .scope import persist_findings, finding_out

CENT = Decimal("0.01")
Q_HOURS = Decimal("0.01")


def money(x: Decimal) -> str:
    return str(x.quantize(CENT, rounding=ROUND_HALF_UP))


def _dec(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x))


def latest_rates(ctx: SnapshotContext) -> tuple[dict[str, Rate], str | None]:
    rows = ctx.s.execute(select(Rate).where(Rate.project_id == ctx.project_id).order_by(Rate.effective_date.desc())).scalars().all()
    if not rows:
        return {}, None
    version = rows[0].rate_set_version
    rates = {}
    for r in rows:
        if r.rate_set_version == version and r.rate_code not in rates:
            rates[r.rate_code] = r
    return rates, version


def _catalogue(ctx: SnapshotContext) -> dict[str, CataloguePart]:
    rows = ctx.s.execute(select(CataloguePart).where(CataloguePart.project_id == ctx.project_id).order_by(CataloguePart.effective_date.desc())).scalars().all()
    out: dict[str, CataloguePart] = {}
    for p in rows:
        out.setdefault(p.part_number, p)
    return out


def build_estimate(ctx: SnapshotContext, run: Run, *, work_item_ids: list[str], exclusions: list[str] | None = None, today: date | None = None) -> ToolResult:
    try:
        ids = [uuid.UUID(x) for x in work_item_ids]
    except ValueError:
        return ctx.result({}, status="failed", unresolved=[{"code": "bad_id", "message": "work item ids must be UUIDs"}])
    items = ctx.s.execute(select(WorkItem).where(WorkItem.run_id == run.id, WorkItem.id.in_(ids))).scalars().all() if ids else []
    if not items:
        return ctx.result({}, status="failed", unresolved=[{"code": "no_work_items", "message": "no work items for this run match the request"}])
    rates, rate_version = latest_rates(ctx)
    catalogue = _catalogue(ctx)
    exclusions = list(exclusions or [])
    exclusions.extend([
        "Site civil, mechanical, and electrical power work beyond panel terminations",
        "Permits, shutdown coordination, and production losses",
        "Replacement of field wiring unless identified as a finding",
    ])

    lines: list[dict] = []
    allowances: list[dict] = []
    unpriced: list[dict] = []
    drafts: list[FindingDraft] = []
    evidence: list[uuid.UUID] = []
    priced_subtotal = Decimal("0")
    low = Decimal("0")
    high = Decimal("0")
    all_priced = True
    warnings = []
    line_no = 0

    def new_line(**kw) -> dict:
        nonlocal line_no
        line_no += 1
        kw.setdefault("equipment_ids", [])
        kw.setdefault("evidence_ids", [])
        kw.setdefault("currency", "CAD")
        kw["id"] = f"L{line_no:03d}"
        return kw

    for wi in items:
        origin_base = {"work_item_id": str(wi.id), "template_id": wi.template_id}
        # ---- labour
        for lab in wi.labour:
            rate = rates.get(lab["rate_code"])
            hours = _dec(lab["hours_base"]).quantize(Q_HOURS)
            h_lo = _dec(lab["hours_low"]).quantize(Q_HOURS)
            h_hi = _dec(lab["hours_high"]).quantize(Q_HOURS)
            unit = lab.get("unit", "hour")
            desc = f"{lab['description']} ({lab['rate_code']}, {lab['count']} x {lab['per']})"
            if rate is None:
                all_priced = False
                ln = new_line(kind="labour", description=desc, quantity=str(hours), unit=unit, unit_price=None, extended=None, price_source=None, price_effective_date=None,
                              pricing_status="unpriced", assumption_status=wi.assumption_status, classification="included", origin={**origin_base, "rate_code": lab["rate_code"]},
                              equipment_ids=[str(e) for e in wi.equipment_ids])
                unpriced.append(ln)
                drafts.append(FindingDraft("unpriced_line", "medium", f"No rate for {lab['rate_code']}", f"Work item '{wi.title}' needs rate code {lab['rate_code']} but no rate is loaded for this project. The labour line is shown unpriced.", list(wi.equipment_ids), [], "R007", dedupe_key=f"R007:rate:{lab['rate_code']}"))
                continue
            if rate.unit != unit:
                warnings.append(f"{lab['rate_code']} rate is per {rate.unit} but template uses {unit}; applied as-is")
            ext = (rate.rate * hours).quantize(CENT)
            status = "expired" if price_expired(rate.effective_date, today) else "priced"
            ln = new_line(kind="labour", description=desc, quantity=str(hours), unit=unit, unit_price=money(rate.rate), extended=money(ext), price_source=f"rate set {rate.rate_set_version}",
                          price_effective_date=rate.effective_date.isoformat(), pricing_status=status, assumption_status=wi.assumption_status, classification="included",
                          origin={**origin_base, "rate_code": lab["rate_code"], "hours_low": str(h_lo), "hours_high": str(h_hi)}, equipment_ids=[str(e) for e in wi.equipment_ids],
                          evidence_ids=[str(e) for e in rate.evidence_ids])
            evidence.extend(rate.evidence_ids)
            if status == "expired":
                all_priced = False
                unpriced.append(ln)
                drafts.append(FindingDraft("expired_price", "medium", f"Rate {lab['rate_code']} is older than the allowed age", f"Rate set {rate.rate_set_version} effective {rate.effective_date} exceeds the configured price age limit. The line is shown but excluded from the priced subtotal until rates are refreshed.", [], list(rate.evidence_ids), "R008", dedupe_key=f"R008:rate:{lab['rate_code']}"))
            else:
                lines.append(ln)
                priced_subtotal += ext
                low += (rate.rate * h_lo).quantize(CENT)
                high += (rate.rate * h_hi).quantize(CENT)
        # ---- parts
        for part in wi.parts:
            qty = _dec(part["quantity"])
            desc = part["description"]
            eq_ids = part.get("equipment_ids", []) or [str(e) for e in wi.equipment_ids]
            if part.get("reuse_candidate"):
                ln = new_line(kind="part", description=f"{desc} — reuse candidate (compatibility unverified)", quantity=str(qty), unit=part.get("unit", "ea"), unit_price=None, extended=None,
                              pricing_status="allowance", assumption_status="assumed", classification="optional", origin={**origin_base, "part_number": part.get("part_number") or ""}, equipment_ids=eq_ids)
                allowances.append(ln)
                continue
            pn = part.get("part_number")
            optional = bool(part.get("optional"))
            classification = "optional" if optional else "included"
            cat = catalogue.get(pn) if pn else None
            if cat is None:
                if not optional:
                    all_priced = False
                ln = new_line(kind="part", description=desc + (f" [{pn}]" if pn else ""), quantity=str(qty), unit=part.get("unit", "ea"), unit_price=None, extended=None,
                              pricing_status="unpriced", assumption_status="assumed", classification=classification, origin={**origin_base, "part_number": pn or ""}, equipment_ids=eq_ids)
                unpriced.append(ln)
                drafts.append(FindingDraft("unpriced_line", "medium" if not optional else "low", f"No catalogue entry for {pn or desc}", f"Work item '{wi.title}' lists '{desc}' but the catalogue has no matching entry. The part is shown as unpriced scope.", list(wi.equipment_ids), [], "R007", dedupe_key=f"R007:part:{pn or desc}"))
                continue
            evidence.extend(cat.evidence_ids)
            if cat.unit_price is None:
                if not optional:
                    all_priced = False
                ln = new_line(kind="part", description=f"{cat.description} [{cat.part_number}]", quantity=str(qty), unit=part.get("unit", "ea"), unit_price=None, extended=None, price_source=cat.source,
                              price_effective_date=cat.effective_date.isoformat(), pricing_status="unpriced", assumption_status="assumed", classification=classification, origin={**origin_base, "part_number": cat.part_number},
                              equipment_ids=eq_ids, evidence_ids=[str(e) for e in cat.evidence_ids])
                unpriced.append(ln)
                drafts.append(FindingDraft("unpriced_line", "medium", f"{cat.part_number} has no price", f"The catalogue lists {cat.part_number} ({cat.description}) without a unit price (source: {cat.source}). The {'optional ' if optional else ''}part is shown as unpriced scope; a quotation is required. No price is ever treated as zero.", list(wi.equipment_ids), list(cat.evidence_ids), "R007", dedupe_key=f"R007:part:{cat.part_number}"))
                continue
            ext = (cat.unit_price * qty).quantize(CENT)
            status = "expired" if price_expired(cat.effective_date, today) else "priced"
            ln = new_line(kind="part", description=f"{cat.description} [{cat.part_number}]", quantity=str(qty), unit=part.get("unit", "ea"), unit_price=money(cat.unit_price), extended=money(ext),
                          price_source=cat.source, price_effective_date=cat.effective_date.isoformat(), pricing_status=status, assumption_status="assumed", classification=classification,
                          origin={**origin_base, "part_number": cat.part_number}, equipment_ids=eq_ids, evidence_ids=[str(e) for e in cat.evidence_ids])
            if status == "expired":
                if not optional:
                    all_priced = False
                unpriced.append(ln)
                drafts.append(FindingDraft("expired_price", "medium", f"Price for {cat.part_number} is expired", f"{cat.part_number} price {money(cat.unit_price)} {cat.currency} is effective {cat.effective_date}, older than the allowed age. The line is excluded from the priced subtotal until a current price is loaded.", list(wi.equipment_ids), list(cat.evidence_ids), "R008", dedupe_key=f"R008:part:{cat.part_number}"))
            elif optional:
                allowances.append(ln)  # priced, shown, never summed into the base figure
            else:
                lines.append(ln)
                priced_subtotal += ext
                low += ext
                high += ext

    findings = persist_findings(ctx, run, drafts)
    complete = all_priced and bool(rate_version)
    scenarios = []
    if complete:
        scenarios = [
            {"name": "low", "total": money(low), "assumptions": ["template low-hour values; all parts at catalogue price"]},
            {"name": "base", "total": money(priced_subtotal), "assumptions": ["template base-hour values; all parts at catalogue price"]},
            {"name": "high", "total": money(high), "assumptions": ["template high-hour values; all parts at catalogue price"]},
        ]
    payload = {"currency": "CAD", "rate_set_version": rate_version or "none", "lines": lines, "priced_subtotal": money(priced_subtotal), "allowances": allowances,
               "unpriced": unpriced, "exclusions": exclusions, "scenarios": scenarios, "complete": complete}
    existing = ctx.s.execute(select(Estimate).where(Estimate.run_id == run.id)).scalars().first()
    if existing:
        existing.payload = payload
        existing.complete = complete
        existing.rate_set_version = rate_version or "none"
        est = existing
    else:
        est = Estimate(org_id=ctx.org_id, project_id=ctx.project_id, run_id=run.id, rate_set_version=rate_version or "none", payload=payload, complete=complete)
        ctx.s.add(est)
    ctx.s.flush()
    if not rate_version:
        warnings.append("no rate set loaded for this project; all labour is unpriced")
    unresolved = [{"code": "unpriced", "message": l["description"], "subject": l["id"]} for l in unpriced]
    return ctx.result({"estimate_id": str(est.id), "estimate": payload, "findings": [finding_out(f) for f in findings]},
                      status="complete" if complete else "partial", evidence_ids=evidence, warnings=warnings, unresolved=unresolved)
