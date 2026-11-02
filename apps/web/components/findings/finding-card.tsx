"use client";

import { useEvidence } from "@/components/providers";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Pill } from "@/components/ui/pill";
import type { Finding } from "@/lib/types";

export function FindingCard({ finding }: { finding: Finding }) {
  const { open } = useEvidence();
  const tone = finding.severity === "high" ? "secondary" : finding.severity === "info" ? "muted" : "outline";
  return (
    <Card className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={tone}>{finding.severity}</Pill>
        <Pill>{finding.type.replaceAll("_", " ")}</Pill>
        <Pill tone="muted">{finding.basis.replaceAll("_", " ")}</Pill>
        <Pill tone={finding.review_status === "accepted" ? "primary" : "muted"}>{finding.review_status}</Pill>
      </div>
      <h3 className="text-title">{finding.title}</h3>
      <p className="text-body text-muted">{finding.summary}</p>
      {finding.open_questions.length > 0 ? (
        <ul className="space-y-1 text-ui text-ink">
          {finding.open_questions.map((q) => (
            <li key={q}>Unresolved: {q}</li>
          ))}
        </ul>
      ) : null}
      <div className="flex items-center gap-2">
        <Button variant="secondary" className="min-h-8 h-8 text-ui" disabled={finding.evidence_ids.length === 0} onClick={() => open(finding.evidence_ids)}>
          Open evidence
        </Button>
        {finding.rule_id ? <span className="text-caption text-faint">{finding.rule_id}</span> : null}
      </div>
    </Card>
  );
}
