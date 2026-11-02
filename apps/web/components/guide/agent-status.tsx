"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Pill } from "@/components/ui/pill";

export function AgentStatus() {
  const status = useQuery({ queryKey: ["system-status"], queryFn: api.status, refetchInterval: 15000 });
  const model = status.data?.model_connected;
  const db = status.data?.database;

  return (
    <Card className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-heading font-extrabold">What is happening</h2>
        <Pill tone={db ? "primary" : "secondary"}>{db ? "Database connected" : "Database offline"}</Pill>
        <Pill tone={model ? "primary" : "muted"}>{model ? "Model agent" : "Checklist agent"}</Pill>
      </div>
      {status.isLoading ? <p className="text-body text-muted">Checking the workspace…</p> : null}
      {status.error ? (
        <p className="text-body text-muted">The API on localhost:8000 is not answering. Start it, then refresh. Sign-in and investigations both need that service.</p>
      ) : null}
      {status.data ? (
        <div className="space-y-2 text-body text-muted max-w-3xl">
          {model ? (
            <p>
              The investigation agent can read the request and choose which checks to run, using {status.data.reasoning_model}. It still cannot approve the work, invent a price, or operate equipment. You see each step it takes.
            </p>
          ) : (
            <p>
              The investigation agent is on, and it follows a fixed engineering checklist: find the equipment, trace connections, check conflicts, draft the work, price it, and propose tests. A language model is not connected, so it cannot choose a different order or read unmarked prose on its own. Connect an AI Gateway key when you want that.
            </p>
          )}
          <p>
            {process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
              ? "Google or email sign-in is on the sign-in page. It opens this same workspace. The demo engineer button is the local sign-in."
              : "Sign-in is the local workspace login."}
          </p>
        </div>
      ) : null}
    </Card>
  );
}
