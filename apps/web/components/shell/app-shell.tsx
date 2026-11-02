"use client";

import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  MessageSquare,
  Cpu,
  Files,
  GitBranch,
  LayoutGrid,
  LogOut,
  Search,
  Sparkles,
} from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useAuth, useEvidence } from "@/components/providers";
import { EvidencePanel } from "@/components/evidence/evidence-panel";
import { Button } from "@/components/ui/button";
import { TextInput } from "@/components/ui/input";
import { Brand } from "@/components/ui/brand";

const projectNav = [
  { href: "", label: "Overview", icon: LayoutGrid },
  { href: "/documents", label: "Documents", icon: Files },
  { href: "/equipment", label: "Equipment", icon: Cpu },
  { href: "/graph", label: "Connections", icon: GitBranch },
  { href: "/chat", label: "Ask AI", icon: MessageSquare },
  { href: "/investigate", label: "Investigate", icon: Sparkles },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const { me, logout } = useAuth();
  const pathname = usePathname();
  const params = useParams<{ projectId?: string }>();
  const projectId = params.projectId;
  const { ids } = useEvidence();
  const [q, setQ] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);

  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api.project(projectId!),
    enabled: Boolean(projectId && me),
  });

  return (
    <div className="min-h-dvh bg-canvas text-ink">
      <header className="sticky top-0 z-30 flex min-h-20 flex-wrap items-center gap-4 border-b border-hairline bg-white px-5 py-3 lg:px-7">
        <Brand />
        <div className="flex-1" />
        {projectId ? <div className="relative hidden w-72 lg:block">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
          <TextInput aria-label="Search project records" value={q} onChange={(e) => {setQ(e.target.value); setSearchOpen(true);}} onFocus={() => setSearchOpen(true)} placeholder="Find equipment or evidence…" className="pl-9 bg-canvas" />
          {searchOpen && q.length > 1 ? <SearchResults projectId={projectId} q={q} onClose={() => setSearchOpen(false)} /> : null}
        </div> : null}
        <Link href="/guide" className="text-ui text-muted hover:text-primary">Help</Link>
        {me ? <Button variant="ghost" onClick={logout} aria-label="Log out"><LogOut className="size-4" /><span className="hidden xl:inline">{me.name}</span></Button> : null}
      </header>
      <div className="flex">
        <aside className="sticky top-20 hidden h-[calc(100dvh-5rem)] w-56 shrink-0 flex-col border-r border-hairline bg-white p-4 md:flex">
          <Link href="/projects" className="mb-7 flex items-center gap-3 rounded-lg px-3 py-3 text-ui font-semibold text-muted hover:bg-canvas"><LayoutGrid size={18} />All projects</Link>
          <p className="px-3 text-[10px] font-semibold uppercase tracking-[0.15em] text-muted">{project.data?.name ?? "Workspace"}</p>
          <nav aria-label="Project navigation" className="mt-3 space-y-1">
            {projectId ? projectNav.map(item => {
              const href = `/projects/${projectId}${item.href}`;
              const active = item.href === "" ? pathname === href : pathname.startsWith(href);
              const Icon = item.icon;
              return <Link key={item.href} href={href} aria-current={active ? "page" : undefined} className={cn("flex items-center gap-3 rounded-lg px-3 py-3 text-ui font-medium text-muted hover:bg-canvas", active && "bg-primary/10 text-primary font-semibold")}><Icon size={18}/>{item.label}</Link>;
            }) : <p className="px-3 py-3 text-body text-muted">Choose a project to explore its records and start an investigation.</p>}
          </nav>
          <div className="mt-auto rounded-xl border border-hairline bg-canvas p-3"><p className="text-ui font-semibold">Evidence before decisions</p><p className="mt-2 text-caption leading-relaxed text-muted">AI drafts and explains. Your engineers review and approve.</p><span className="mt-3 block text-[10px] uppercase tracking-widest text-muted">Demonstration workspace</span></div>
        </aside>
        <div className="min-w-0 flex-1">
          {projectId ? <nav aria-label="Mobile project navigation" className="flex gap-1 overflow-x-auto border-b border-hairline bg-white px-3 py-2 md:hidden">{projectNav.map(item => <Link key={item.href} href={`/projects/${projectId}${item.href}`} className="shrink-0 rounded-md px-3 py-2 text-ui text-primary">{item.label}</Link>)}</nav> : null}
          <main id="main-content" className={cn("min-w-0 px-5 py-7 md:px-8 lg:px-10", ids.length > 0 && "xl:pr-[410px]")}>{children}</main>
        </div>
      </div>
      {projectId ? <EvidencePanel projectId={projectId} /> : null}
    </div>
  );
}

function SearchResults({ projectId, q, onClose }: { projectId: string; q: string; onClose: () => void }) {
  const { open } = useEvidence();
  const router = useRouter();
  const search = useQuery({
    queryKey: ["search", projectId, q],
    queryFn: () => api.search(projectId, q),
    enabled: q.length > 1,
  });
  const equipment = useQuery({
    queryKey: ["equipment", projectId, q],
    queryFn: () => api.equipment(projectId, { q }),
    enabled: q.length > 1,
  });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="absolute top-full z-40 mt-2 w-full overflow-hidden rounded-card border border-hairline bg-surface shadow-[0_12px_40px_rgba(0,0,0,0.4)]">
      <div className="max-h-96 overflow-y-auto p-2">
        <p className="px-2 py-1 text-caption text-muted uppercase">Equipment</p>
        {(equipment.data?.equipment ?? []).slice(0, 6).map((eq) => (
          <button
            key={eq.id}
            className="flex w-full items-center justify-between rounded-md px-2 py-2 text-left text-body active:bg-canvas"
            onClick={() => {
              router.push(`/projects/${projectId}/equipment/${eq.id}`);
              onClose();
            }}
          >
            <span>{eq.tag}</span>
            <span className="text-caption text-muted">{eq.type}</span>
          </button>
        ))}
        <p className="mt-2 px-2 py-1 text-caption text-muted uppercase">Evidence</p>
        {(search.data?.data.passages ?? []).slice(0, 6).map((p) => (
          <button
            key={p.chunk_id}
            className="block w-full rounded-md px-2 py-2 text-left text-ui active:bg-canvas"
            onClick={() => {
              open(p.evidence_ids);
              onClose();
            }}
          >
            <span className="text-muted">{p.source}</span>
            <span className="ml-2 line-clamp-2">{p.text}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
