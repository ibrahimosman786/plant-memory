"use client";

import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  ClipboardCheck,
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
import { Pill } from "@/components/ui/pill";

const projectNav = [
  { href: "", label: "Overview", icon: LayoutGrid },
  { href: "/documents", label: "Documents", icon: Files },
  { href: "/equipment", label: "Equipment", icon: Cpu },
  { href: "/graph", label: "Graph", icon: GitBranch },
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
      <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-hairline bg-canvas px-4">
        <Link href="/projects" className="text-title font-extrabold tracking-tight shrink-0">
          Plant Memory
        </Link>
        <Link href="/guide" className="text-ui text-secondary shrink-0">
          How to use
        </Link>
        {project.data ? (
          <span className="hidden md:inline text-ui text-muted truncate">{project.data.name}</span>
        ) : null}
        {projectId ? (
          <div className="relative mx-auto hidden w-full max-w-md md:block">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-faint" />
            <TextInput
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setSearchOpen(true);
              }}
              onFocus={() => setSearchOpen(true)}
              placeholder="Search tags, evidence, requirements"
              className="pl-9"
            />
            {searchOpen && q.length > 1 ? <SearchResults projectId={projectId} q={q} onClose={() => setSearchOpen(false)} /> : null}
          </div>
        ) : (
          <div className="flex-1" />
        )}
        {me ? <Pill tone="muted">{me.org_role}</Pill> : null}
        {projectId ? (
          <Link href={`/projects/${projectId}/investigate`}>
            <Button>Investigate</Button>
          </Link>
        ) : null}
        {me ? (
          <Button variant="ghost" onClick={logout} aria-label="Log out">
            <LogOut className="size-4" />
            <span className="hidden sm:inline">{me.name}</span>
          </Button>
        ) : null}
      </header>

      <div className="flex">
        <nav className="sticky top-14 hidden h-[calc(100dvh-3.5rem)] w-16 shrink-0 flex-col items-center gap-1 border-r border-hairline bg-canvas py-2 md:flex">
          {projectId
            ? projectNav.map((item) => {
                const href = `/projects/${projectId}${item.href}`;
                const active = item.href === "" ? pathname === href : pathname.startsWith(href);
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={href}
                    title={item.label}
                    className={cn(
                      "flex size-11 items-center justify-center rounded-lg text-muted",
                      active && "text-primary bg-surface",
                    )}
                  >
                    <Icon className="size-5" />
                  </Link>
                );
              })
            : (
                <Link href="/projects" title="Projects" className="flex size-11 items-center justify-center rounded-lg bg-surface text-primary">
                  <LayoutGrid className="size-5" />
                </Link>
              )}
          {projectId ? (
            <Link
              href={`/projects/${projectId}/investigate`}
              title="Reports"
              className={cn("mt-auto mb-3 flex size-11 items-center justify-center rounded-lg text-muted", pathname.includes("/reports/") && "text-primary bg-surface")}
            >
              <ClipboardCheck className="size-5" />
            </Link>
          ) : null}
        </nav>

        <main className={cn("min-w-0 flex-1 px-4 py-5 md:px-6", ids.length > 0 && "md:pr-[400px]")}>
          {children}
        </main>
      </div>

      {projectId ? (
        <nav className="fixed inset-x-0 bottom-0 z-30 flex h-14 items-center justify-around border-t border-hairline bg-canvas md:hidden">
          {projectNav.map((item) => {
            const href = `/projects/${projectId}${item.href}`;
            const active = item.href === "" ? pathname === href : pathname.startsWith(href);
            const Icon = item.icon;
            return (
              <Link key={item.href} href={href} className={cn("flex flex-col items-center text-caption text-muted", active && "text-primary")}>
                <Icon className="size-5" />
                {item.label}
              </Link>
            );
          })}
        </nav>
      ) : null}

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
