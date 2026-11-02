"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, Tile } from "@/components/ui/card";
import { Pill, statusTone } from "@/components/ui/pill";
import { kindLabel, when } from "@/lib/format";

export default function ProjectOverviewPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const project = useQuery({ queryKey: ["project", projectId], queryFn: () => api.project(projectId) });
  const documents = useQuery({ queryKey: ["documents", projectId], queryFn: () => api.documents(projectId) });
  const equipment = useQuery({ queryKey: ["equipment", projectId], queryFn: () => api.equipment(projectId) });
  const snapshots = useQuery({ queryKey: ["snapshots", projectId], queryFn: () => api.snapshots(projectId) });
  const requests = useQuery({ queryKey: ["change-requests", projectId], queryFn: () => api.changeRequests(projectId) });
  const reports = useQuery({ queryKey: ["reports", projectId], queryFn: () => api.reports(projectId) });

  const latest = requests.data?.[0];
  const latestRun = latest?.runs[0];
  const conflicts = (equipment.data?.equipment ?? []).filter((e) => e.duplicate_tag).length;
  const docs = documents.data ?? [];
  const busy = docs.some((doc) => {
    const status = doc.versions.at(-1)?.status;
    return status === "uploaded" || status === "processing";
  });
  const next = !docs.length
    ? { title: "Upload the project records", body: "Start with the equipment list and the I/O list. The agent cannot investigate files that are not here.", href: `/projects/${projectId}/documents`, action: "Open documents" }
    : busy
      ? { title: "Documents are still being read", body: "Wait until each file says ready or partial. The summary under the status tells you what was extracted.", href: `/projects/${projectId}/documents`, action: "Check documents" }
      : !(snapshots.data ?? []).length
        ? { title: "Freeze a snapshot", body: "On Documents, name a snapshot and freeze it. That is the file set the agent is allowed to use.", href: `/projects/${projectId}/documents`, action: "Freeze snapshot" }
        : !latest
          ? { title: "Describe the panel change", body: "Tell the agent which tag to investigate, for example CP-101, and what the upgrade is.", href: `/projects/${projectId}/investigate`, action: "Start investigation" }
          : latestRun && ["queued", "running", "waiting_clarification"].includes(latestRun.state)
            ? { title: "The agent is working on the latest request", body: "Open the run to read each step, or answer if it asks which equipment you mean.", href: `/projects/${projectId}/runs/${latestRun.id}`, action: "Open the run" }
            : { title: "Review the latest draft", body: "The agent has saved a package. An engineer still has to accept, change, or reject it.", href: `/projects/${projectId}/investigate`, action: "Open investigations" };

  return (
    <div className="space-y-8 pb-16">
      <section className="rounded-card overflow-hidden border border-hairline" style={{ background: "linear-gradient(135deg, rgba(0,85,135,0.07), rgba(255,255,255,0.9))" }}>
        <div className="p-6 md:p-8 space-y-3">
          <p className="text-caption text-primary uppercase tracking-widest">Project overview</p>
          <h1 className="text-display font-extrabold">{project.data?.name ?? "Project"}</h1>
          <p className="text-body max-w-2xl">{project.data?.description}</p>
          <div className="flex flex-wrap gap-2">
            <Pill tone="muted">{equipment.data?.equipment.length ?? "—"} tags</Pill>
            <Pill tone="muted">{documents.data?.length ?? "—"} documents</Pill>
            <Pill tone={conflicts ? "secondary" : "muted"}>{conflicts} duplicate-tag flags</Pill>
            <Pill>{snapshots.data?.[0]?.name ?? "No snapshot"}</Pill>
          </div>
          <div className="flex flex-wrap gap-2 pt-2">
            <Link href={`/projects/${projectId}/chat`}><Button>Ask AI about this project</Button></Link>
            <Link href={`/projects/${projectId}/investigate`}>
              <Button variant="secondary">Start investigation</Button>
            </Link>
            <Link href={`/projects/${projectId}/documents`}>
              <Button variant="secondary">Upload records</Button>
            </Link>
          </div>
        </div>
      </section>

      <Card className="space-y-3">
        <p className="text-caption text-primary uppercase">Do this next</p>
        <h2 className="text-heading font-extrabold">{next.title}</h2>
        <p className="text-body text-muted max-w-2xl">{next.body}</p>
        <Link href={next.href}>
          <Button>{next.action}</Button>
        </Link>
      </Card>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-heading font-extrabold">Documents</h2>
          <Link href={`/projects/${projectId}/documents`} className="text-body text-secondary">
            Show more
          </Link>
        </div>
        <div className="rail flex gap-3 overflow-x-auto">
          {(documents.data ?? []).map((doc) => {
            const latestVersion = doc.versions.at(-1);
            return (
              <Tile key={doc.id} className="w-[180px] h-[140px] p-3 flex flex-col justify-between">
                <p className="text-title line-clamp-2">{doc.filename}</p>
                <div>
                  <p className="text-caption text-muted">{kindLabel(doc.kind)}</p>
                  {latestVersion ? <Pill tone={statusTone(latestVersion.status)}>{latestVersion.status}</Pill> : null}
                </div>
              </Tile>
            );
          })}
        </div>
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-heading font-extrabold">Equipment</h2>
          <Link href={`/projects/${projectId}/equipment`} className="text-body text-secondary">
            Show more
          </Link>
        </div>
        <div className="rail flex gap-3 overflow-x-auto">
          {(equipment.data?.equipment ?? []).slice(0, 16).map((eq) => (
            <Link key={eq.id} href={`/projects/${projectId}/equipment/${eq.id}`}>
              <Tile className="w-[160px] h-[120px] p-3 flex flex-col justify-between">
                <p className="text-title">{eq.tag}</p>
                <p className="text-caption text-muted">{eq.type}</p>
                {eq.duplicate_tag ? <Pill tone="secondary">duplicate tag</Pill> : <Pill tone="muted">{eq.assertion_count ?? 0} facts</Pill>}
              </Tile>
            </Link>
          ))}
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="space-y-3">
          <h2 className="text-heading font-extrabold">Latest investigation</h2>
          {latest ? (
            <>
              <p className="text-title">{latest.title}</p>
              <p className="text-body text-muted line-clamp-4">{latest.request_text}</p>
              {latestRun ? <Pill tone={statusTone(latestRun.state)}>{latestRun.state.replaceAll("_", " ")}</Pill> : <Pill>no run</Pill>}
              {latestRun ? (
                <Link href={`/projects/${projectId}/runs/${latestRun.id}`}>
                  <Button variant="tertiary">Open run</Button>
                </Link>
              ) : null}
            </>
          ) : (
            <p className="text-muted text-body">No change request yet. Describe the panel upgrade to start.</p>
          )}
        </Card>
        <Card className="space-y-3">
          <h2 className="text-heading font-extrabold">Reports</h2>
          {(reports.data ?? []).slice(0, 4).map((r) => {
            const v = r.versions.at(-1);
            return (
              <div key={r.id} className="flex items-center justify-between gap-2 border-t border-hairline pt-3 first:border-t-0 first:pt-0">
                <div>
                  <p className="text-title">{r.change_request?.title ?? "Report"}</p>
                  <p className="text-caption text-muted">{v ? `v${v.version_no} · ${when(v.created_at)}` : "no version"}</p>
                </div>
                {v ? (
                  <Link href={`/projects/${projectId}/reports/${v.id}`}>
                    <Button variant="ghost">{v.stale ? "Stale" : v.status}</Button>
                  </Link>
                ) : null}
              </div>
            );
          })}
          {(reports.data ?? []).length === 0 ? <p className="text-muted text-body">Draft packages appear here after a run saves a report version.</p> : null}
        </Card>
      </div>
    </div>
  );
}
