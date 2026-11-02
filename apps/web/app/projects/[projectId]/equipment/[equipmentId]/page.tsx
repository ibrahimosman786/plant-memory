"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useEvidence } from "@/components/providers";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { TextArea, TextInput } from "@/components/ui/input";
import { Pill } from "@/components/ui/pill";

export default function EquipmentDetailPage() {
  const { projectId, equipmentId } = useParams<{ projectId: string; equipmentId: string }>();
  const { open } = useEvidence();
  const qc = useQueryClient();
  const detail = useQuery({ queryKey: ["equipment-detail", projectId, equipmentId], queryFn: () => api.equipmentDetail(projectId, equipmentId) });
  const [decision, setDecision] = useState("");
  const [rationale, setRationale] = useState("");
  const [subjectKey, setSubjectKey] = useState("");

  const record = useMutation({
    mutationFn: () =>
      api.recordDecision(projectId, {
        subject_type: "assertion_conflict",
        subject_key: subjectKey,
        decision,
        rationale,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["equipment-detail", projectId, equipmentId] }),
  });

  function onDecision(e: FormEvent) {
    e.preventDefault();
    record.mutate();
  }

  const eq = detail.data;
  if (detail.isLoading) return <p className="text-muted">Loading equipment…</p>;
  if (!eq) return <p>Equipment was not found in the current snapshot.</p>;

  return (
    <div className="space-y-6 pb-16">
      <div>
        <Link href={`/projects/${projectId}/equipment`} className="text-body text-secondary">
          Equipment
        </Link>
        <h1 className="text-display font-extrabold">{eq.tag}</h1>
        <p className="text-body text-muted">
          {eq.type} · {eq.description || "No description"} · {eq.source}
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button variant="secondary" disabled={eq.evidence_ids.length === 0} onClick={() => open(eq.evidence_ids)}>
            Open listing evidence
          </Button>
          <Link href={`/projects/${projectId}/graph?from=${eq.id}`}>
            <Button variant="tertiary">Trace dependencies</Button>
          </Link>
        </div>
      </div>

      {eq.conflicting_attributes.length > 0 ? (
        <Card className="space-y-2">
          <Pill tone="secondary">Conflicting records preserved</Pill>
          <p className="text-body text-muted">
            Both values remain. Last write does not win. Record an engineer decision if you resolve one of them.
          </p>
          <p className="text-title">{eq.conflicting_attributes.join(", ")}</p>
        </Card>
      ) : null}

      {Object.entries(eq.assertions).map(([attr, values]) => {
        const conflict = eq.conflicting_attributes.includes(attr);
        return (
          <Card key={attr} className="space-y-3">
            <div className="flex items-center gap-2">
              <h2 className="text-heading font-extrabold">{attr}</h2>
              {conflict ? <Pill tone="secondary">conflict</Pill> : null}
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              {values.map((v) => (
                <div key={v.id} className="rounded-xl border border-hairline p-3 space-y-2">
                  <p className="text-title">
                    {v.value} {v.unit ?? ""}
                  </p>
                  <p className="text-caption text-muted">
                    {v.source} · {v.method} · {v.review_status}
                  </p>
                  <Button variant="ghost" disabled={v.evidence_ids.length === 0} onClick={() => open(v.evidence_ids)}>
                    Evidence
                  </Button>
                </div>
              ))}
            </div>
          </Card>
        );
      })}

      <Card className="space-y-3">
        <h2 className="text-heading font-extrabold">Relationships</h2>
        {(eq.relationships ?? []).length === 0 ? <p className="text-muted text-body">No recorded links.</p> : null}
        <ul className="space-y-2">
          {eq.relationships.map((r) => (
            <li key={r.id} className="flex flex-wrap items-center gap-2 text-ui">
              <Pill tone={r.status === "candidate" ? "secondary" : r.status === "verified" ? "primary" : "muted"}>{r.status}</Pill>
              <span>
                {r.direction === "out" ? "feeds" : "fed by"} {r.other?.tag ?? "unknown"} ({r.type})
              </span>
              {r.other ? (
                <Link href={`/projects/${projectId}/equipment/${r.other.id}`} className="text-secondary">
                  Open
                </Link>
              ) : null}
              <Button variant="ghost" disabled={r.evidence_ids.length === 0} onClick={() => open(r.evidence_ids)}>
                Evidence
              </Button>
            </li>
          ))}
        </ul>
      </Card>

      <Card className="space-y-3 max-w-xl">
        <h2 className="text-heading font-extrabold">Engineer decision</h2>
        <p className="text-body text-muted">Additive and attributable. Original assertions stay in the record.</p>
        <form onSubmit={onDecision} className="space-y-3">
          <TextInput
            value={subjectKey}
            onChange={(e) => setSubjectKey(e.target.value)}
            placeholder={`assertion_conflict:${eq.id}:range`}
            required
          />
          <TextInput value={decision} onChange={(e) => setDecision(e.target.value)} placeholder="Decision, e.g. use datasheet 0-10 bar" required />
          <TextArea value={rationale} onChange={(e) => setRationale(e.target.value)} placeholder="Rationale and supporting evidence" />
          <Button type="submit" disabled={record.isPending}>
            Record decision
          </Button>
        </form>
        {eq.decisions.map((d) => (
          <p key={d.id} className="text-ui text-muted">
            {d.decision} — {d.rationale}
          </p>
        ))}
      </Card>
    </div>
  );
}
