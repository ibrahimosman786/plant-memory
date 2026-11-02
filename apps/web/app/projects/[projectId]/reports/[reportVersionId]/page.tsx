"use client";

import { useParams } from "next/navigation";
import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { EstimatePanel } from "@/components/estimate/estimate-panel";
import { FindingCard } from "@/components/findings/finding-card";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select, TextArea } from "@/components/ui/input";
import { Pill } from "@/components/ui/pill";
import type { ChecklistItem, Estimate, Finding } from "@/lib/types";

type PackageShape = {
  package?: {
    status?: string;
    scope_summary?: string;
    open_questions?: string[];
    sections_incomplete?: { section: string; reason: string }[];
    reuse_candidates?: { equipment_id: string; rationale: string; status: string }[];
  };
  findings?: Finding[];
  work_items?: { id: string; title: string; description: string; assumption_status: string }[];
  estimate?: Estimate | null;
  checklist?: ChecklistItem[];
  disclaimer?: string;
  change_request?: { title: string };
  snapshot?: { name: string };
};

export default function ReportPage() {
  const { projectId, reportVersionId } = useParams<{ projectId: string; reportVersionId: string }>();
  const qc = useQueryClient();
  const report = useQuery({
    queryKey: ["report", projectId, reportVersionId],
    queryFn: () => api.reportVersion(projectId, reportVersionId),
  });
  const reviews = useQuery({
    queryKey: ["reviews", projectId, reportVersionId],
    queryFn: () => api.reviews(projectId, reportVersionId),
  });
  const [decision, setDecision] = useState<"approved" | "changes_requested" | "rejected">("changes_requested");
  const [comment, setComment] = useState("");
  const [itemDecisions, setItemDecisions] = useState<Record<string, string>>({});

  const pkg = (report.data?.package ?? {}) as PackageShape;
  const findings = pkg.findings ?? [];
  const checklist = pkg.checklist ?? [];

  const items = useMemo(
    () => [
      ...findings.map((f) => ({ kind: "finding" as const, id: f.id, decision: itemDecisions[`finding:${f.id}`] })),
      ...checklist.map((c) => ({ kind: "checklist" as const, id: c.id, decision: itemDecisions[`checklist:${c.id}`] })),
    ],
    [findings, checklist, itemDecisions],
  );

  const review = useMutation({
    mutationFn: () =>
      api.createReview(projectId, reportVersionId, {
        decision,
        comment,
        items: items.filter((i) => i.decision).map((i) => ({ kind: i.kind, id: i.id, decision: i.decision })),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["report", projectId, reportVersionId] });
      qc.invalidateQueries({ queryKey: ["reviews", projectId, reportVersionId] });
    },
  });
  const exp = useMutation({
    mutationFn: (format: "md" | "html" | "json") => api.exportReport(projectId, reportVersionId, format),
    onSuccess: (res) => {
      window.open(res.url, "_blank", "noopener,noreferrer");
    },
  });

  function onReview(e: FormEvent) {
    e.preventDefault();
    review.mutate();
  }

  const rv = report.data;
  if (report.isLoading) return <p className="text-muted">Loading report…</p>;
  if (!rv) return <p>Report version not found.</p>;

  return (
    <div className="space-y-6 pb-16">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-caption text-muted uppercase">Review-ready draft</p>
          <h1 className="text-display font-extrabold">{pkg.change_request?.title ?? `Report v${rv.version_no}`}</h1>
          <p className="text-body text-muted">{pkg.disclaimer || "Draft assessment from project evidence. Not an approval or executed test record."}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Pill tone={rv.stale ? "outline" : "primary"}>{rv.stale ? "Stale" : rv.status}</Pill>
          <Button variant="tertiary" onClick={() => exp.mutate("html")}>
            Export HTML
          </Button>
          <Button variant="ghost" onClick={() => exp.mutate("md")}>
            Markdown
          </Button>
          <Button variant="ghost" onClick={() => exp.mutate("json")}>
            JSON
          </Button>
        </div>
      </div>

      {rv.stale ? (
        <Card>
          <p className="text-title">This package is stale</p>
          <p className="text-body text-muted">{rv.stale_reason}. Re-run against the current snapshot before approving.</p>
        </Card>
      ) : null}

      <Card className="space-y-2">
        <h2 className="text-heading font-extrabold">Scope</h2>
        <p className="text-body">{pkg.package?.scope_summary}</p>
        {(pkg.package?.open_questions ?? []).map((q) => (
          <p key={q} className="text-ui">
            Unresolved: {q}
          </p>
        ))}
        {(pkg.package?.sections_incomplete ?? []).map((s) => (
          <p key={s.section} className="text-ui text-muted">
            Incomplete {s.section}: {s.reason}
          </p>
        ))}
      </Card>

      {(pkg.package?.reuse_candidates ?? []).length > 0 ? (
        <Card className="space-y-2">
          <h2 className="text-heading font-extrabold">Reuse candidates</h2>
          {pkg.package!.reuse_candidates!.map((c) => (
            <p key={c.equipment_id} className="text-ui">
              {c.status}: {c.rationale}
            </p>
          ))}
        </Card>
      ) : null}

      <section className="space-y-3">
        <h2 className="text-heading font-extrabold">Findings</h2>
        {findings.map((f) => (
          <div key={f.id} className="space-y-2">
            <FindingCard finding={f} />
            <Select
              className="max-w-xs"
              value={itemDecisions[`finding:${f.id}`] ?? ""}
              onChange={(e) => setItemDecisions((prev) => ({ ...prev, [`finding:${f.id}`]: e.target.value }))}
            >
              <option value="">Item decision…</option>
              <option value="accepted">Accept</option>
              <option value="rejected">Reject</option>
              <option value="needs_info">Needs info</option>
            </Select>
          </div>
        ))}
      </section>

      <EstimatePanel estimate={pkg.estimate ?? null} />

      <Card className="space-y-3">
        <h2 className="text-heading font-extrabold">Checklist review</h2>
        {checklist.map((c) => (
          <div key={c.id} className="border-t border-hairline pt-3 space-y-2">
            <p className="text-title">{c.requirement}</p>
            <p className="text-body text-muted">{c.proposed_verification}</p>
            <Select
              className="max-w-xs"
              value={itemDecisions[`checklist:${c.id}`] ?? ""}
              onChange={(e) => setItemDecisions((prev) => ({ ...prev, [`checklist:${c.id}`]: e.target.value }))}
            >
              <option value="">Item decision…</option>
              <option value="accepted">Accept</option>
              <option value="modified">Modify</option>
              <option value="rejected">Reject</option>
            </Select>
          </div>
        ))}
      </Card>

      <Card className="space-y-3 max-w-xl">
        <h2 className="text-heading font-extrabold">Reviewer decision</h2>
        <p className="text-body text-muted">Targets this immutable report version. Approving a stale version is blocked.</p>
        <form onSubmit={onReview} className="space-y-3">
          <Select value={decision} onChange={(e) => setDecision(e.target.value as typeof decision)}>
            <option value="approved">Approved</option>
            <option value="changes_requested">Changes requested</option>
            <option value="rejected">Rejected</option>
          </Select>
          <TextArea value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Comment" />
          {review.error ? <p className="text-ui">{(review.error as Error).message}</p> : null}
          <Button type="submit" disabled={review.isPending}>
            Record review
          </Button>
        </form>
        {reviews.data?.map((rev) => (
          <p key={rev.id} className="text-ui text-muted">
            {rev.reviewer}: {rev.decision} — {rev.comment}
          </p>
        ))}
      </Card>
    </div>
  );
}
