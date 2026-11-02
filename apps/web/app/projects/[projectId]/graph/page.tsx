"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Select } from "@/components/ui/input";
import { Pill } from "@/components/ui/pill";

const DependencyGraph = dynamic(() => import("@/components/graph/dependency-graph"), { ssr: false });

export default function GraphPage() {
  return (
    <Suspense fallback={<p className="text-muted">Loading map…</p>}>
      <GraphPageInner />
    </Suspense>
  );
}

function GraphPageInner() {
  const { projectId } = useParams<{ projectId: string }>();
  const search = useSearchParams();
  const router = useRouter();
  const equipment = useQuery({ queryKey: ["equipment", projectId], queryFn: () => api.equipment(projectId) });
  const initial = search.get("from") || equipment.data?.equipment.find((e) => e.type.toLowerCase().includes("panel"))?.id || equipment.data?.equipment[0]?.id || "";
  const [from, setFrom] = useState(initial);
  const startId = from || initial;

  useEffect(() => {
    if (!from && initial) setFrom(initial);
  }, [from, initial]);
  const [depth, setDepth] = useState(3);
  const [view, setView] = useState<"all" | "recorded" | "verified" | "candidate">("all");

  const trace = useQuery({
    queryKey: ["trace", projectId, startId, depth],
    queryFn: () => api.trace(projectId, [startId], undefined, depth),
    enabled: Boolean(startId),
  });

  const filtered = useMemo(() => {
    const data = trace.data?.data;
    if (!data) return null;
    if (view === "all") return data;
    const allowed = new Set(data.views[view] ?? []);
    return { ...data, edges: data.edges.filter((e) => allowed.has(e.id)) };
  }, [trace.data, view]);

  return (
    <div className="space-y-4 pb-16">
      <div>
        <p className="text-caption text-muted uppercase">Recorded dependencies</p>
        <h1 className="text-display font-extrabold">Relationship map</h1>
        <p className="text-body text-muted max-w-2xl">
          Candidate links stay visually distinct. Nearby symbols on a P&ID are not treated as confirmed connections.
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Select value={startId} onChange={(e) => setFrom(e.target.value)} className="max-w-xs">
          {(equipment.data?.equipment ?? []).map((eq) => (
            <option key={eq.id} value={eq.id}>
              {eq.tag} · {eq.type}
            </option>
          ))}
        </Select>
        <Select value={String(depth)} onChange={(e) => setDepth(Number(e.target.value))} className="w-28">
          {[1, 2, 3, 4, 5, 6].map((d) => (
            <option key={d} value={d}>
              depth {d}
            </option>
          ))}
        </Select>
        {(["all", "recorded", "verified", "candidate"] as const).map((v) => (
          <Button key={v} variant={view === v ? "secondary" : "ghost"} onClick={() => setView(v)}>
            {v}
          </Button>
        ))}
      </div>
      {trace.data?.warnings.map((w) => (
        <Pill key={w} tone="outline">
          {w}
        </Pill>
      ))}
      {trace.data?.data.truncated ? <Pill tone="secondary">Truncated — request a broader investigation</Pill> : null}
      {!startId ? (
        <EmptyState title="Pick a starting tag" body="Freeze a snapshot with equipment records first, then trace from the panel or a pump." />
      ) : filtered ? (
        <DependencyGraph
          data={filtered}
          onSelect={(id) => router.push(`/projects/${projectId}/equipment/${id}`)}
        />
      ) : (
        <p className="text-muted">Tracing…</p>
      )}
      {(trace.data?.data.unresolved_links.length ?? 0) > 0 ? (
        <p className="text-ui text-muted">
          Unresolved: {trace.data!.data.unresolved_links.map((u) => u.normalized_tag).join(", ")}
        </p>
      ) : null}
      {startId ? (
        <Link href={`/projects/${projectId}/equipment/${startId}`} className="text-secondary text-body">
          Open selected equipment
        </Link>
      ) : null}
    </div>
  );
}
