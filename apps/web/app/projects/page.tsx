"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { AgentStatus } from "@/components/guide/agent-status";
import { AppShell } from "@/components/shell/app-shell";
import { Button } from "@/components/ui/button";
import { Card, Tile } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { TextArea, TextInput } from "@/components/ui/input";
import { Pill } from "@/components/ui/pill";
import { when } from "@/lib/format";

export default function ProjectsPage() {
  const qc = useQueryClient();
  const projects = useQuery({ queryKey: ["projects"], queryFn: api.projects });
  const [name, setName] = useState("North pumping station");
  const [description, setDescription] = useState("Fictional two-pump station used for panel-upgrade assessments.");
  const create = useMutation({
    mutationFn: () => api.createProject({ name, description }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["projects"] }),
  });

  function onCreate(e: FormEvent) {
    e.preventDefault();
    create.mutate();
  }

  return (
    <AppShell>
      <section className="rounded-card overflow-hidden border border-hairline mb-8" style={{ background: "linear-gradient(135deg, rgba(0,85,135,0.07), rgba(255,255,255,0.9))" }}>
        <div className="p-6 md:p-8 space-y-3 max-w-3xl">
          <p className="text-caption text-muted uppercase">Spartan Controls · demonstration</p>
          <h1 className="text-display font-extrabold">Your engineering workspace.</h1>
          <p className="text-body text-ink max-w-2xl">
            Choose a project to explore its documents, ask the AI assistant a question, or investigate an engineering change.
          </p>
        </div>
      </section>

      <div className="mb-8">
        <AgentStatus />
      </div>

      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-heading font-extrabold">Projects</h2>
        <Pill tone="muted">{projects.data?.length ?? 0} open</Pill>
      </div>

      {projects.isLoading ? <p className="text-muted text-body">Loading projects…</p> : null}
      {projects.error ? (
        <EmptyState
          title="API is not reachable"
          body="Start the FastAPI service on localhost:8000, then refresh. Local sign-in only works while AUTH_BACKEND=dev."
        />
      ) : null}

      <div className="mb-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {(projects.data ?? []).map((p) => (
          <Link key={p.id} href={`/projects/${p.id}`}>
            <Tile className="min-h-[180px] p-6 hover:border-primary/40 hover:shadow-md flex flex-col justify-between">
              <div>
                <p className="text-title line-clamp-2">{p.name}</p>
                <p className="mt-2 text-caption text-muted line-clamp-3">{p.description || "No description"}</p>
              </div>
              <div className="flex items-center justify-between">
                <Pill>{p.role ?? "member"}</Pill>
                <span className="text-caption text-faint">{when(p.created_at)}</span>
              </div>
            </Tile>
          </Link>
        ))}
      </div>

      {(projects.data?.length ?? 0) === 0 && !projects.isLoading && !projects.error ? (
        <EmptyState title="No projects yet" body="Create a project, upload the synthetic pumping-station records, then freeze a snapshot before investigating." />
      ) : null}

      <details className="max-w-xl rounded-xl border border-hairline bg-white p-5"><summary className="cursor-pointer text-title font-semibold">Create a new project</summary><Card className="mt-4 space-y-3 border-0 p-0 shadow-none">

        <form onSubmit={onCreate} className="space-y-3">
          <TextInput aria-label="Project name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Project name" required />
          <TextArea aria-label="Project description" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What plant or panel is this?" />
          <Button type="submit" disabled={create.isPending}>
            Create project
          </Button>
        </form>
      {create.error ? <p role="alert">{create.error.message}</p> : null}</Card></details>
    </AppShell>
  );
}
