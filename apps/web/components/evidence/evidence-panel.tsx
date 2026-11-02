"use client";

import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { api } from "@/lib/api";
import { locatorLabel } from "@/lib/format";
import { useEvidence } from "@/components/providers";
import { Button } from "@/components/ui/button";
import { Pill } from "@/components/ui/pill";

export function EvidencePanel({ projectId }: { projectId: string }) {
  const { ids, close } = useEvidence();
  const query = useQuery({
    queryKey: ["evidence", projectId, ids],
    queryFn: () => api.evidence(projectId, ids),
    enabled: ids.length > 0,
  });

  if (ids.length === 0) return null;

  return (
    <aside className="fixed inset-x-0 bottom-0 z-40 max-h-[70vh] overflow-y-auto border-t border-hairline bg-surface p-4 md:inset-y-0 md:left-auto md:right-0 md:top-0 md:h-full md:w-[380px] md:max-h-none md:border-l md:border-t-0 rounded-t-card md:rounded-none">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-caption text-muted uppercase">Source</p>
          <h2 className="text-heading font-extrabold">Evidence</h2>
        </div>
        <Button variant="ghost" onClick={close} aria-label="Close evidence">
          <X className="size-4" />
        </Button>
      </div>
      {query.isLoading ? <p className="text-muted text-body">Loading source…</p> : null}
      {query.error ? <p className="text-body">Could not load evidence. {String((query.error as Error).message)}</p> : null}
      <div className="space-y-4">
        {(query.data ?? []).map((item) => (
          <article key={item.id} className="rounded-card border border-hairline overflow-hidden">
            {item.page_image_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={item.page_image_url} alt={`${item.filename} ${locatorLabel(item.locator)}`} className="w-full bg-canvas" />
            ) : null}
            <div className="p-3 space-y-2">
              <div className="flex flex-wrap gap-2">
                <Pill tone="secondary">{locatorLabel(item.locator)}</Pill>
                <Pill>{item.revision_label || `v${item.version_no}`}</Pill>
              </div>
              <p className="text-title">{item.filename}</p>
              <p className="text-caption text-muted">{item.kind.replaceAll("_", " ")}</p>
              <p className="text-ui text-ink whitespace-pre-wrap">{item.text}</p>
              <p className="text-caption text-faint font-mono">{item.id}</p>
            </div>
          </article>
        ))}
        {query.data && query.data.length === 0 ? <p className="text-muted text-body">No authorized evidence for those IDs in this project.</p> : null}
      </div>
    </aside>
  );
}
