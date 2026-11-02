"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { eventSentence, when } from "@/lib/format";
import { EstimatePanel } from "@/components/estimate/estimate-panel";
import { FindingCard } from "@/components/findings/finding-card";
import { useEvidence } from "@/components/providers";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { TextInput } from "@/components/ui/input";
import { Pill, statusTone } from "@/components/ui/pill";

const ACTIVE = new Set(["queued", "running", "waiting_clarification", "awaiting_clarification"]);

export default function RunPage() {
  const { projectId, runId } = useParams<{ projectId: string; runId: string }>();
  const qc = useQueryClient();
  const { open } = useEvidence();
  const run = useQuery({
    queryKey: ["run", projectId, runId],
    queryFn: () => api.run(projectId, runId),
    refetchInterval: (q) => (q.state.data && ACTIVE.has(q.state.data.state) ? 1500 : false),
  });
  const events = useQuery({
    queryKey: ["run-events", projectId, runId],
    queryFn: () => api.runEvents(projectId, runId),
    refetchInterval: () => (run.data && ACTIVE.has(run.data.state) ? 1500 : false),
  });
  const findings = useQuery({
    queryKey: ["findings", projectId, runId],
    queryFn: () => api.findings(projectId, runId),
    refetchInterval: () => (run.data && ACTIVE.has(run.data.state) ? 2000 : false),
  });
  const work = useQuery({
    queryKey: ["work", projectId, runId],
    queryFn: () => api.work(projectId, runId),
    refetchInterval: () => (run.data && ACTIVE.has(run.data.state) ? 2000 : false),
  });
  const [answer, setAnswer] = useState("");
  const cancel = useMutation({
    mutationFn: () => api.cancelRun(projectId, runId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["run", projectId, runId] }),
  });
  const pendingClarification = run.data?.clarifications?.find((c) => !c.answer);
  const clarify = useMutation({
    mutationFn: () => api.answerClarification(projectId, runId, pendingClarification!.id, answer),
    onSuccess: () => {
      setAnswer("");
      qc.invalidateQueries({ queryKey: ["run", projectId, runId] });
    },
  });

  function onClarify(e: FormEvent) {
    e.preventDefault();
    clarify.mutate();
  }

  const r = run.data;
  if (run.isLoading) return <p className="text-muted">Loading investigation…</p>;
  if (!r) return <p>Run not found.</p>;

  return (
    <div className="space-y-6 pb-16">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-caption text-muted uppercase">Investigation run</p>
          <h1 className="text-display font-extrabold">Live package</h1>
          <p className="text-body text-muted">Read what the agent is doing. Findings below come from the checks, not from a guess.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Pill tone={statusTone(r.state)}>{r.state.replaceAll("_", " ")}</Pill>
          {ACTIVE.has(r.state) ? (
            <Button variant="tertiary" onClick={() => cancel.mutate()} disabled={cancel.isPending}>
              Cancel
            </Button>
          ) : null}
          {r.report_version_id ? (
            <Link href={`/projects/${projectId}/reports/${r.report_version_id}`}>
              <Button>Open report</Button>
            </Link>
          ) : null}
        </div>
      </div>

      <div className="flex flex-wrap gap-2 text-caption text-muted">
        <span>Tools {r.tool_invocations}</span>
        <span>Tokens {r.input_tokens + r.output_tokens}</span>
        <span>Cost USD {r.cost_usd}</span>
        {r.deadline_at ? <span>Deadline {when(r.deadline_at)}</span> : null}
      </div>
      {r.error ? <Card>{r.error}</Card> : null}

      {pendingClarification ? (
        <Card className="space-y-3">
          <Pill tone="secondary">Needs clarification</Pill>
          <p className="text-title">{pendingClarification.question}</p>
          <div className="flex flex-wrap gap-2">
            {pendingClarification.options.map((opt) => (
              <Button key={opt} variant="ghost" onClick={() => setAnswer(opt)}>
                {opt}
              </Button>
            ))}
          </div>
          <form onSubmit={onClarify} className="flex gap-2">
            <TextInput value={answer} onChange={(e) => setAnswer(e.target.value)} required />
            <Button type="submit">Submit</Button>
          </form>
        </Card>
      ) : null}

      <Card className="space-y-3">
        <h2 className="text-heading font-extrabold">What the agent is doing</h2>
        <ol className="space-y-3">
          {(events.data ?? [])
            .filter((ev) => eventSentence(ev.type, ev.payload))
            .map((ev) => (
              <li key={ev.id} className="flex gap-3 text-body">
                <span className="text-faint w-16 shrink-0 text-caption">{when(ev.at)}</span>
                <span>{eventSentence(ev.type, ev.payload)}</span>
              </li>
            ))}
        </ol>
        {(events.data ?? []).length === 0 ? <p className="text-muted">Waiting for the first step…</p> : null}
      </Card>

      <section className="space-y-3">
        <h2 className="text-heading font-extrabold">Findings</h2>
        {(findings.data ?? []).map((f) => (
          <FindingCard key={f.id} finding={f} />
        ))}
      </section>

      <section className="space-y-3">
        <h2 className="text-heading font-extrabold">Work breakdown</h2>
        {(work.data?.work_items ?? []).map((w) => (
          <Card key={w.id} className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-title">{w.title}</h3>
              <Pill tone="muted">{w.assumption_status}</Pill>
            </div>
            <p className="text-body text-muted">{w.description}</p>
            {w.parts.filter((p) => p.reuse_candidate).length > 0 ? (
              <p className="text-ui text-primary">
                Reuse candidates: {w.parts.filter((p) => p.reuse_candidate).map((p) => p.description).join(", ")}
              </p>
            ) : null}
          </Card>
        ))}
      </section>

      <EstimatePanel estimate={work.data?.estimate ?? null} />

      <Card className="space-y-3">
        <h2 className="text-heading font-extrabold">Proposed verification</h2>
        <p className="text-body text-muted">Drafted checks are not executed tests. Nothing here is marked passed because it was generated.</p>
        {(work.data?.checklist ?? []).map((c) => (
          <div key={c.id} className="border-t border-hairline pt-3 space-y-1">
            <p className="text-title">{c.requirement}</p>
            <p className="text-body">{c.proposed_verification}</p>
            <p className="text-ui text-muted">
              Expected: {c.expected_outcome ?? "missing"} · {c.expected_outcome_status.replaceAll("_", " ")}
            </p>
            <Button variant="ghost" disabled={c.evidence_ids.length === 0} onClick={() => open(c.evidence_ids)}>
              Evidence
            </Button>
          </div>
        ))}
      </Card>
    </div>
  );
}
