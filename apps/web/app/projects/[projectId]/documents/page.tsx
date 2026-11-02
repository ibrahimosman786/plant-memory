"use client";

import { FormEvent, useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { bytes, kindLabel, statusDetailText, when } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Select, TextInput } from "@/components/ui/input";
import { Pill, statusTone } from "@/components/ui/pill";
import { DOCUMENT_KINDS } from "@/lib/types";

export default function DocumentsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const qc = useQueryClient();
  const documents = useQuery({ queryKey: ["documents", projectId], queryFn: () => api.documents(projectId), refetchInterval: 4000 });
  const snapshots = useQuery({ queryKey: ["snapshots", projectId], queryFn: () => api.snapshots(projectId) });
  const [kind, setKind] = useState("other");
  const [revision, setRevision] = useState("");
  const [snapshotName, setSnapshotName] = useState("Investigation snapshot");

  const upload = useMutation({
    mutationFn: (files: FileList) =>
      Promise.all(Array.from(files).map((file) => api.uploadDocument(projectId, file, kind, revision || undefined))),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["documents", projectId] }),
  });
  const freeze = useMutation({
    mutationFn: () => api.createSnapshot(projectId, snapshotName),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["snapshots", projectId] }),
  });

  function onUpload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const input = e.currentTarget.elements.namedItem("files") as HTMLInputElement;
    if (input.files?.length) upload.mutate(input.files);
  }

  return (
    <div className="space-y-6 pb-16">
      <div>
        <p className="text-caption text-muted uppercase">Records</p>
        <h1 className="text-display font-extrabold">Documents</h1>
        <p className="text-body text-muted max-w-2xl">
          Files are processed on upload, not on every question. Originals stay unchanged; a new revision creates a new version and can stale earlier reports.
        </p>
      </div>

      <Card className="space-y-3">
        <h2 className="text-heading font-extrabold">Upload</h2>
        <form onSubmit={onUpload} className="grid gap-3 md:grid-cols-4">
          <Select value={kind} onChange={(e) => setKind(e.target.value)} className="md:col-span-1">
            {DOCUMENT_KINDS.map((k) => (
              <option key={k} value={k}>
                {kindLabel(k)}
              </option>
            ))}
          </Select>
          <TextInput value={revision} onChange={(e) => setRevision(e.target.value)} placeholder="Revision label" />
          <input
            name="files"
            type="file"
            multiple
            className="bg-surface text-ink border border-hairline rounded-md px-3 py-2 text-body file:mr-3 file:border-0 file:bg-secondary file:text-on-primary file:rounded-lg file:px-3 file:py-1"
          />
          <Button type="submit" disabled={upload.isPending}>
            {upload.isPending ? "Uploading…" : "Queue files"}
          </Button>
        </form>
        {upload.error ? <p className="text-ui">{(upload.error as Error).message}</p> : null}
      </Card>

      {(documents.data ?? []).length === 0 && !documents.isLoading ? (
        <EmptyState title="No files yet" body="Upload equipment lists, I/O sheets, datasheets, the control narrative, P&ID, configuration CSV, and the rate set." />
      ) : null}

      <div className="overflow-x-auto rounded-card border border-hairline">
        <table className="w-full text-ui">
          <thead className="bg-surface text-left text-caption text-muted uppercase">
            <tr>
              <th className="px-4 py-3">File</th>
              <th className="px-4 py-3">Kind</th>
              <th className="px-4 py-3">Latest</th>
              <th className="px-4 py-3">Size</th>
              <th className="px-4 py-3">Uploaded</th>
            </tr>
          </thead>
          <tbody>
            {(documents.data ?? []).map((doc) => {
              const latest = doc.versions.at(-1);
              const detail = statusDetailText(latest?.status_detail);
              return (
                <tr key={doc.id} className="border-t border-hairline">
                  <td className="px-4 py-3">
                    <p className="text-title">{doc.filename}</p>
                    <p className="text-caption text-faint">{doc.versions.length} version{doc.versions.length === 1 ? "" : "s"}</p>
                  </td>
                  <td className="px-4 py-3">{kindLabel(doc.kind)}</td>
                  <td className="px-4 py-3">
                    {latest ? (
                      <div className="space-y-1">
                        <Pill tone={statusTone(latest.status)}>{latest.status}</Pill>
                        {detail ? <p className="text-caption text-muted max-w-xs">{detail}</p> : null}
                      </div>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-4 py-3">{bytes(latest?.size_bytes)}</td>
                  <td className="px-4 py-3">{when(doc.created_at)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <Card className="space-y-3 max-w-xl">
        <h2 className="text-heading font-extrabold">Freeze snapshot</h2>
        <p className="text-body text-muted">Investigations run against an immutable collection of document versions. New uploads do not rewrite a reviewed report.</p>
        <div className="flex gap-2">
          <TextInput value={snapshotName} onChange={(e) => setSnapshotName(e.target.value)} />
          <Button variant="secondary" onClick={() => freeze.mutate()} disabled={freeze.isPending}>
            Freeze
          </Button>
        </div>
        {freeze.error ? <p className="text-ui">{(freeze.error as Error).message}</p> : null}
        <ul className="space-y-2">
          {(snapshots.data ?? []).map((s) => (
            <li key={s.id} className="flex justify-between text-ui">
              <span>{s.name}</span>
              <span className="text-muted">{s.document_version_ids.length} versions · {when(s.created_at)}</span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
