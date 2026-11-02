"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { TextInput } from "@/components/ui/input";
import { Pill } from "@/components/ui/pill";

export default function EquipmentPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [q, setQ] = useState("");
  const equipment = useQuery({ queryKey: ["equipment", projectId, q], queryFn: () => api.equipment(projectId, { q: q || undefined }) });
  const unresolved = useQuery({ queryKey: ["unresolved", projectId], queryFn: () => api.unresolved(projectId) });

  return (
    <div className="space-y-6 pb-16">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-caption text-muted uppercase">Plant records</p>
          <h1 className="text-display font-extrabold">Equipment</h1>
        </div>
        <TextInput value={q} onChange={(e) => setQ(e.target.value)} placeholder="Exact tag first" className="max-w-xs" />
      </div>

      {(unresolved.data?.length ?? 0) > 0 ? (
        <div className="rounded-card border border-hairline bg-surface p-4">
          <p className="text-title mb-2">Unresolved references</p>
          <div className="flex flex-wrap gap-2">
            {unresolved.data!.map((u) => (
              <Pill key={u.id} tone="outline">
                {u.normalized_tag} · {u.source}
              </Pill>
            ))}
          </div>
        </div>
      ) : null}

      {(equipment.data?.equipment.length ?? 0) === 0 && !equipment.isLoading ? (
        <EmptyState title="No equipment in this snapshot" body="Upload and process records, then freeze a snapshot. Exact tag matches take precedence over semantic search." />
      ) : null}

      <div className="overflow-x-auto rounded-card border border-hairline">
        <table className="w-full text-ui">
          <thead className="bg-surface text-left text-caption text-muted uppercase">
            <tr>
              <th className="px-4 py-3">Tag</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Description</th>
              <th className="px-4 py-3">Facts</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {(equipment.data?.equipment ?? []).map((eq) => (
              <tr key={eq.id} className="border-t border-hairline">
                <td className="px-4 py-3">
                  <p className="text-title">{eq.tag}</p>
                  {eq.duplicate_tag ? <Pill tone="secondary">duplicate tag</Pill> : null}
                </td>
                <td className="px-4 py-3">{eq.type}</td>
                <td className="px-4 py-3 text-muted">{eq.description || "—"}</td>
                <td className="px-4 py-3">{eq.assertion_count ?? 0}</td>
                <td className="px-4 py-3 text-right">
                  <Link href={`/projects/${projectId}/equipment/${eq.id}`}>
                    <Button variant="ghost">Inspect</Button>
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
