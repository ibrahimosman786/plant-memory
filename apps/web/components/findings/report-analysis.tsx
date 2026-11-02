"use client";

import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useEvidence } from "@/components/providers";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select, TextArea } from "@/components/ui/input";
import { Pill } from "@/components/ui/pill";

export function ReportAnalysis({ projectId, reportVersionId, stale }: { projectId: string; reportVersionId: string; stale: boolean }) {
  const qc = useQueryClient();
  const evidence = useEvidence();
  const status = useQuery({ queryKey: ["system-status"], queryFn: api.status });
  const history = useQuery({ queryKey: ["analyses", projectId, reportVersionId], queryFn: () => api.analyses(projectId, reportVersionId) });
  const [model, setModel] = useState("");
  const [question, setQuestion] = useState("Which recorded conflicts should the engineer investigate first, and what evidence is missing?");
  const analyze = useMutation({
    mutationFn: () => api.analyzeReport(projectId, reportVersionId, question, model || status.data?.default_model || ""),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["analyses", projectId, reportVersionId] }),
  });
  function submit(e: FormEvent) { e.preventDefault(); analyze.mutate(); }
  return <Card className="space-y-4">
    <div className="flex flex-wrap items-center gap-2">
      <h2 className="text-heading font-extrabold">Ask about this report</h2>
      <Pill>AI interpretation · engineer review required</Pill>
    </div>
    <p className="text-body text-muted">Analyze the frozen report with Claude or GPT. Each factual claim must link to source evidence. This does not change findings, prices, or approval status.</p>
    <form onSubmit={submit} className="space-y-3">
      <label className="block space-y-1 text-ui">Model
        <Select value={model || status.data?.default_model || ""} onChange={(e) => setModel(e.target.value)}>
          {(status.data?.models ?? []).map((id) => <option key={id} value={id}>{id}</option>)}
        </Select>
      </label>
      <label className="block space-y-1 text-ui">Question
        <TextArea value={question} onChange={(e) => setQuestion(e.target.value)} minLength={3} maxLength={2000} required />
      </label>
      {!status.data?.model_configured ? <p className="text-ui text-muted">AI analysis requires a configured API server credential. The engineering report remains available below.</p> : null}
      {stale ? <p className="text-ui">Run a fresh investigation before analyzing this stale report.</p> : null}
      {analyze.error ? <p role="alert" className="text-ui">{analyze.error.message}</p> : null}
      <Button type="submit" disabled={analyze.isPending || !status.data?.model_configured || stale}>
        {analyze.isPending ? "Analyzing evidence…" : "Analyze report"}
      </Button>
    </form>
    {history.error ? <p role="alert">Could not load previous analyses: {history.error.message}</p> : null}
    <div aria-live="polite" className="space-y-4">
      {(history.data ?? []).map((item) => <article key={item.id} className="border-t border-hairline pt-4 space-y-3">
        <p className="text-caption text-muted">{item.model} · {new Date(item.created_at).toLocaleString()}</p>
        <h3 className="text-title">{item.question}</h3>
        {item.analysis.claims.map((claim, i) => <div key={i} className="space-y-1">
          <p className="text-body">{claim.statement}</p>
          <Button variant="ghost" onClick={() => evidence.open(claim.evidence_ids)}>Inspect {claim.evidence_ids.length} source{claim.evidence_ids.length === 1 ? "" : "s"}</Button>
        </div>)}
        {item.analysis.questions_for_engineer.map((q, i) => <p key={i} className="text-ui">Engineer question: {q}</p>)}
        {item.analysis.limitations.map((text, i) => <p key={i} className="text-ui text-muted">Limitation: {text}</p>)}
        <p className="text-caption text-muted">{item.notice}</p>
      </article>)}
    </div>
  </Card>;
}
