"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { when } from "@/lib/format";
import { AgentStatus } from "@/components/guide/agent-status";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Select, TextArea, TextInput } from "@/components/ui/input";
import { Pill, statusTone } from "@/components/ui/pill";

const DEFAULT_REQUEST =
  "Investigate replacing this control panel. Identify equipment we may be able to reuse, conflicting information, required work, estimated costs, and proposed tests.";

export default function InvestigatePage() {
  const { projectId } = useParams<{ projectId: string }>();
  const router = useRouter();
  const snapshots = useQuery({ queryKey: ["snapshots", projectId], queryFn: () => api.snapshots(projectId) });
  const requests = useQuery({ queryKey: ["change-requests", projectId], queryFn: () => api.changeRequests(projectId) });
  const reports = useQuery({ queryKey: ["reports", projectId], queryFn: () => api.reports(projectId) });
  const [title, setTitle] = useState("Replace station control panel");
  const [requestText, setRequestText] = useState(DEFAULT_REQUEST);
  const [tags, setTags] = useState("CP-101");
  const [assumptions, setAssumptions] = useState("Reuse existing field instruments where recorded evidence supports it.");
  const [snapshotId, setSnapshotId] = useState("");

  const start = useMutation({
    mutationFn: async () => {
      const cr = await api.createChangeRequest(projectId, {
        title,
        request_text: requestText,
        target_tags: tags.split(/[\s,]+/).filter(Boolean),
        assumptions: assumptions ? [assumptions] : [],
      });
      const snap = snapshotId || snapshots.data?.[0]?.id;
      if (!snap) throw new Error("Freeze a snapshot before starting an investigation.");
      return api.startRun(projectId, cr.id, snap, "gateway");
    },
    onSuccess: (run) => router.push(`/projects/${projectId}/runs/${run.id}`),
  });

  function onStart(e: FormEvent) {
    e.preventDefault();
    start.mutate();
  }

  return (
    <div className="space-y-6 pb-16">
      <div>
        <p className="text-caption text-muted uppercase">Agent investigation</p>
        <h1 className="text-display font-extrabold">Upgrade request</h1>
        <p className="text-body text-muted max-w-2xl">
          Describe the change, name the tags, and start. The agent finds the equipment, traces connections, checks conflicts, and drafts the work, the cost, and the tests. You can read each step on the next screen. It cannot approve the package or invent a price.
        </p>
      </div>
      <AgentStatus />

      <Card className="space-y-3">
        <form onSubmit={onStart} className="space-y-3">
          <TextInput value={title} onChange={(e) => setTitle(e.target.value)} required />
          <TextArea value={requestText} onChange={(e) => setRequestText(e.target.value)} required />
          <TextInput value={tags} onChange={(e) => setTags(e.target.value)} placeholder="Target tags" />
          <TextInput value={assumptions} onChange={(e) => setAssumptions(e.target.value)} placeholder="Assumptions the engineer is willing to state" />
          <Select value={snapshotId} onChange={(e) => setSnapshotId(e.target.value)}>
            <option value="">Latest snapshot</option>
            {(snapshots.data ?? []).map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} · {when(s.created_at)}
              </option>
            ))}
          </Select>
          {start.error ? <p className="text-ui">{(start.error as Error).message}</p> : null}
          <Button type="submit" disabled={start.isPending}>
            {start.isPending ? "Starting…" : "Run investigation"}
          </Button>
        </form>
      </Card>

      {(snapshots.data?.length ?? 0) === 0 ? (
        <EmptyState
          title="No snapshot frozen"
          body="Process documents first, then freeze a snapshot. The investigation cannot silently read a moving set of files."
          action={
            <Link href={`/projects/${projectId}/documents`}>
              <Button variant="secondary">Open documents</Button>
            </Link>
          }
        />
      ) : null}

      <section className="space-y-3">
        <h2 className="text-heading font-extrabold">Previous runs</h2>
        {(requests.data ?? []).map((cr) => (
          <Card key={cr.id} className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-title">{cr.title}</h3>
              <span className="text-caption text-muted">{when(cr.created_at)}</span>
            </div>
            <p className="text-body text-muted line-clamp-2">{cr.request_text}</p>
            <div className="flex flex-wrap gap-2">
              {cr.runs.map((run) => (
                <Link key={run.id} href={`/projects/${projectId}/runs/${run.id}`}>
                  <Pill tone={statusTone(run.state)}>{run.state.replaceAll("_", " ")}</Pill>
                </Link>
              ))}
            </div>
          </Card>
        ))}
      </section>

      <section className="space-y-3">
        <h2 className="text-heading font-extrabold">Report versions</h2>
        {(reports.data ?? []).flatMap((r) =>
          r.versions.map((v) => (
            <Link key={v.id} href={`/projects/${projectId}/reports/${v.id}`} className="block">
              <Card className="flex items-center justify-between">
                <div>
                  <p className="text-title">{r.change_request?.title ?? "Report"}</p>
                  <p className="text-caption text-muted">
                    v{v.version_no} · {v.status} {v.stale ? "· stale" : ""}
                  </p>
                </div>
                <Button variant="ghost">Open</Button>
              </Card>
            </Link>
          )),
        )}
      </section>
    </div>
  );
}
