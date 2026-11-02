"""Review workflow and export.

A report version is a draft until a reviewer records a decision. Item decisions (accept/reject/
needs_info per finding, accept/modify/reject per checklist item) are attributable and additive.
Export renders the persisted package (never re-queries the model) to Markdown/HTML/JSON.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..auth.deps import DbDep, require_project_role
from ..auth.principal import Principal
from ..db.models import ChecklistItem, Finding, ReportVersion, Review, Run, User
from ..db.session import scoped_session
from ..storage import Buckets, get_storage, report_key
from .runs import report_version_out

router = APIRouter(prefix="/v1/projects/{project_id}", tags=["reviews"])


class ItemDecision(BaseModel):
    kind: Literal["finding", "checklist"]
    id: uuid.UUID
    decision: str
    note: str = ""
    modified_text: str | None = None  # for checklist "modified"


class ReviewIn(BaseModel):
    decision: Literal["approved", "changes_requested", "rejected"]
    comment: str = ""
    items: list[ItemDecision] = Field(default_factory=list)


def _rv(s, project_id: uuid.UUID, report_version_id: uuid.UUID) -> ReportVersion:
    rv = s.get(ReportVersion, report_version_id)
    if rv is None or rv.project_id != project_id:
        raise HTTPException(404, "report version not found")
    return rv


@router.post("/report-versions/{report_version_id}/reviews", status_code=201)
def create_review(project_id: uuid.UUID, report_version_id: uuid.UUID, body: ReviewIn, principal: Annotated[Principal, Depends(require_project_role("reviewer"))], s: DbDep) -> dict:
    rv = _rv(s, project_id, report_version_id)
    run = s.get(Run, rv.run_id)
    if rv.stale and body.decision == "approved":
        raise HTTPException(409, f"report version is stale: {rv.stale_reason}; re-run against the current snapshot before approving")
    item_decisions: dict = {}
    for it in body.items:
        if it.kind == "finding":
            f = s.get(Finding, it.id)
            if f is None or f.run_id != run.id:
                raise HTTPException(404, f"finding {it.id} not in this report")
            if it.decision not in ("accepted", "rejected", "needs_info"):
                raise HTTPException(422, "finding decision must be accepted|rejected|needs_info")
            f.review_status = it.decision
        else:
            c = s.get(ChecklistItem, it.id)
            if c is None or c.run_id != run.id:
                raise HTTPException(404, f"checklist item {it.id} not in this report")
            if it.decision not in ("accepted", "modified", "rejected"):
                raise HTTPException(422, "checklist decision must be accepted|modified|rejected")
            payload = dict(c.payload)
            payload["reviewer_decision"] = it.decision
            if it.decision == "modified" and it.modified_text:
                payload["proposed_verification"] = it.modified_text
                payload["modified_by"] = str(principal.user_id)
            c.payload = payload
        item_decisions[f"{it.kind}:{it.id}"] = {"decision": it.decision, "note": it.note, "modified_text": it.modified_text}
    review = Review(org_id=principal.org_id, project_id=project_id, report_version_id=rv.id, reviewer_id=principal.user_id, decision=body.decision, comment=body.comment, item_decisions=item_decisions)
    s.add(review)
    # Report status reflects the reviewer, not the agent.
    rv.status = {"approved": "approved", "changes_requested": "changes_requested", "rejected": "rejected"}[body.decision]
    pkg = dict(rv.package)
    pkg["review"] = {"decision": body.decision, "comment": body.comment, "reviewer_id": str(principal.user_id), "reviewed_at": datetime.now(timezone.utc).isoformat(), "items": item_decisions}
    # refresh embedded findings/checklist so exports show reviewer state
    pkg["findings"] = [{**f, "review_status": s.get(Finding, uuid.UUID(f["id"])).review_status} for f in pkg.get("findings", [])]
    pkg["checklist"] = [s.get(ChecklistItem, uuid.UUID(c["id"])).payload for c in pkg.get("checklist", []) if s.get(ChecklistItem, uuid.UUID(c["id"]))]
    rv.package = pkg
    s.commit()
    return {"id": str(review.id), "decision": review.decision, "report_version": report_version_out(rv)}


@router.get("/report-versions/{report_version_id}/reviews")
def list_reviews(project_id: uuid.UUID, report_version_id: uuid.UUID, principal: Annotated[Principal, Depends(require_project_role("viewer"))], s: DbDep) -> list[dict]:
    rv = _rv(s, project_id, report_version_id)
    reviews = s.execute(select(Review).where(Review.report_version_id == rv.id).order_by(Review.created_at)).scalars().all()
    with scoped_session(None) as ident:
        names = {u.id: u.name for u in ident.execute(select(User).where(User.id.in_([r.reviewer_id for r in reviews] or [uuid.UUID(int=0)]))).scalars().all()}
    return [{"id": str(r.id), "reviewer": names.get(r.reviewer_id, str(r.reviewer_id)), "decision": r.decision, "comment": r.comment, "item_decisions": r.item_decisions, "created_at": r.created_at.isoformat()} for r in reviews]


# ------------------------------------------------------------------ export

def render_markdown(rv: ReportVersion) -> str:
    p = rv.package
    pkg = p["package"]
    cr = p.get("change_request") or {}
    lines = [f"# Upgrade assessment — {cr.get('title', '')}", "", f"Report version {rv.version_no} · status **{rv.status}** · snapshot `{p['snapshot']['name']}`" + (" · **STALE**: " + (rv.stale_reason or "") if rv.stale else ""), "",
             f"> {p.get('disclaimer', '')}", "", "## Scope", "", pkg["scope_summary"], ""]
    if pkg.get("open_questions"):
        lines += ["### Open questions", ""] + [f"- {q}" for q in pkg["open_questions"]] + [""]
    if pkg.get("sections_incomplete"):
        lines += ["### Incomplete sections", ""] + [f"- **{s['section']}**: {s['reason']}" for s in pkg["sections_incomplete"]] + [""]
    lines += ["## Documents in snapshot", ""] + [f"- {d['label']}" for d in p["snapshot"]["documents"]] + [""]
    lines += ["## Findings", ""]
    if not p["findings"]:
        lines.append("_No findings recorded._")
    for f in p["findings"]:
        lines += [f"### [{f['severity'].upper()}] {f['title']}", "", f"*{f['type']} · basis: {f['basis']} · rule {f.get('rule_id') or '—'} · review: {f.get('review_status', 'unreviewed')}*", "", f["summary"], ""]
        if f.get("open_questions"):
            lines += [f"- Question: {q}" for q in f["open_questions"]] + [""]
        lines += [f"Evidence: {', '.join(f['evidence_ids']) or 'none'}", ""]
    lines += ["## Work breakdown", ""]
    for w in p["work_items"]:
        lines += [f"### {w['title']} (`{w['template_id']}`, {w['assumption_status']})", "", w["description"], ""]
        for l in w["labour"]:
            lines.append(f"- Labour {l['rate_code']}: {l['description']} — {l['hours_low']}/{l['hours_base']}/{l['hours_high']} {l.get('unit', 'hour')} (low/base/high)")
        for part in w["parts"]:
            lines.append(f"- Part: {part['description']} × {part['quantity']}" + (" — reuse candidate" if part.get("reuse_candidate") else ""))
        lines.append("")
    est = p.get("estimate")
    lines += ["## Estimate", ""]
    if est:
        lines += [f"Currency {est['currency']} · rate set `{est['rate_set_version']}` · **{'complete' if est['complete'] else 'INCOMPLETE'}**", "", "| Line | Description | Qty | Unit | Unit price | Extended | Status |", "|---|---|---|---|---|---|---|"]
        for l in est["lines"] + est["unpriced"] + est["allowances"]:
            lines.append(f"| {l['id']} | {l['description']} | {l['quantity']} | {l['unit']} | {l.get('unit_price') or '—'} | {l.get('extended') or '—'} | {l['pricing_status']} |")
        lines += ["", f"**Priced subtotal: {est['priced_subtotal']} {est['currency']}**", ""]
        if est["scenarios"]:
            lines += ["Scenarios (from template hour ranges, not statistical confidence):", ""] + [f"- {sc['name']}: {sc['total']} — {'; '.join(sc['assumptions'])}" for sc in est["scenarios"]] + [""]
        lines += ["Exclusions:", ""] + [f"- {e}" for e in est["exclusions"]] + [""]
    else:
        lines.append("_No estimate._")
    lines += ["", "## Verification checklist", "", "| Requirement | Proposed verification | Expected outcome | Status | Reviewer |", "|---|---|---|---|---|"]
    for c in p["checklist"]:
        lines.append(f"| {c['requirement']} | {c['proposed_verification']} | {(c.get('expected_outcome') or '—').replace('|', '/')[:160]} | {c['expected_outcome_status']} | {c.get('reviewer_decision', 'pending')} |")
    if p.get("review"):
        r = p["review"]
        lines += ["", "## Review", "", f"Decision: **{r['decision']}** by {r['reviewer_id']} at {r['reviewed_at']}", "", r.get("comment", "")]
    lines += ["", "## Evidence index", ""]
    for e in p["evidence"]:
        loc = e["locator"]
        where = f"page {loc['page']}" if "page" in loc else (f"{loc.get('sheet', '')}!{loc.get('cell_range', '')}" if "sheet" in loc else (f"row {loc['row']}" if "row" in loc else json.dumps(loc)))
        lines.append(f"- `{e['id']}` — {e['filename']} ({e['revision_label'] or 'v?'}) {where}: {e['text'][:200].replace(chr(10), ' ')}")
    return "\n".join(lines) + "\n"


def render_html(md: str, title: str) -> str:
    import html
    # Minimal, dependency-free rendering: headings, bullets, tables, paragraphs.
    out = []
    in_table = False
    in_list = False
    for raw in md.splitlines():
        line = raw.rstrip()
        if line.startswith("|"):
            cells = [html.escape(c.strip()) for c in line.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            if not in_table:
                out.append('<table>')
                in_table = True
            out.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</table>")
            in_table = False
        if line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{html.escape(line[2:])}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if line.startswith("### "):
            out.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("## "):
            out.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("# "):
            out.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("> "):
            out.append(f"<blockquote>{html.escape(line[2:])}</blockquote>")
        elif line:
            out.append(f"<p>{html.escape(line)}</p>")
    if in_table:
        out.append("</table>")
    if in_list:
        out.append("</ul>")
    style = ("body{font-family:Inter,system-ui,sans-serif;background:#141415;color:#f0f2f5;max-width:960px;margin:40px auto;padding:0 24px;line-height:1.5}"
             "h1,h2,h3{font-weight:800}table{border-collapse:collapse;width:100%;margin:12px 0}td{border:1px solid #2d2f33;padding:6px 8px;font-size:13px;vertical-align:top}"
             "blockquote{border-left:3px solid #00b24b;margin:0;padding:4px 12px;color:#9aa1b1}code{font-family:'Geist Mono',ui-monospace,monospace;color:#9aa1b1}")
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title><style>{style}</style></head><body>{''.join(out)}</body></html>"


@router.post("/report-versions/{report_version_id}/export")
def export_report(project_id: uuid.UUID, report_version_id: uuid.UUID, principal: Annotated[Principal, Depends(require_project_role("viewer"))], s: DbDep, format: Literal["md", "html", "json"] = "html") -> dict:
    rv = _rv(s, project_id, report_version_id)
    run = s.get(Run, rv.run_id)
    md = render_markdown(rv)
    title = (rv.package.get("change_request") or {}).get("title", "report")
    if format == "md":
        body, ct, ext = md.encode(), "text/markdown", "md"
    elif format == "json":
        body, ct, ext = json.dumps(rv.package, indent=2, default=str).encode(), "application/json", "json"
    else:
        body, ct, ext = render_html(md, title).encode(), "text/html", "html"
    key = report_key(rv.org_id, rv.project_id, run.id, rv.version_no, f"report.{ext}")
    storage = get_storage()
    storage.put(Buckets.reports(), key, body, ct)
    rv.export_key = key
    s.commit()
    return {"url": storage.presign_get(Buckets.reports(), key, ttl_seconds=600, filename=f"report-v{rv.version_no}.{ext}"), "format": format, "bytes": len(body), "stale": rv.stale}
