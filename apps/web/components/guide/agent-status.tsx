"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleCheck, CircleAlert, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/components/providers";

export function AgentStatus() {
  const { token } = useAuth();
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["system-status"], queryFn: api.status, refetchInterval: 60000 });
  const check = useMutation({mutationFn: () => api.checkModel(status.data!.default_model), onSuccess: () => qc.invalidateQueries({queryKey: ["system-status"]})});
  const health = status.data?.model_health;
  const ready = health?.state === "ready";
  return <Card className="space-y-3">
    <div className="flex flex-wrap items-center justify-between gap-3"><div className="flex items-center gap-3">{ready ? <CircleCheck className="text-primary" size={20}/> : <CircleAlert className="text-muted" size={20}/>}<div><h2 className="text-ui font-semibold">{status.isLoading ? "Checking workspace…" : ready ? "AI connection verified" : health?.state === "blocked" ? "AI needs attention" : "Workspace connection"}</h2><p className="mt-1 text-caption text-muted">{status.data?.database ? "Project records are available" : "Checking access to project records"}</p></div></div>{token && status.data?.model_configured ? <Button variant="secondary" disabled={check.isPending} onClick={() => check.mutate()}><RefreshCw size={14} className={check.isPending ? "animate-spin" : ""}/>{check.isPending ? "Checking…" : "Check AI connection"}</Button> : null}</div>
    {status.error ? <p role="alert" className="text-body text-muted">The workspace service is unavailable. Please retry shortly.</p> : null}
    {health && !ready ? <p role={health.state === "blocked" ? "alert" : undefined} className="text-body text-muted">{health.message} {health.state === "blocked" ? <a href="https://vercel.com/ai-gateway" target="_blank" rel="noreferrer" className="text-primary underline">Open AI Gateway settings</a> : null}</p> : null}
    {check.error ? <p role="alert" className="text-body">{check.error.message}</p> : null}
    <details className="text-caption text-muted"><summary className="cursor-pointer">Connection details</summary><p className="mt-2">{status.data?.default_model ?? "Loading model"} · Connection checks make one small model request. Each investigation records its own connection result.</p></details>
  </Card>;
}
