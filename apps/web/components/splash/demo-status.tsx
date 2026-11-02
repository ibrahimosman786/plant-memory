"use client";

import { AgentStatus } from "@/components/guide/agent-status";
import { Card } from "@/components/ui/card";
import { Pill } from "@/components/ui/pill";

export function SplashDemoStatus() {
  const clerkOn = Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY);

  return (
    <section id="status" className="scroll-mt-20 space-y-4">
      <p className="text-caption text-primary uppercase">This machine</p>
      <h2 className="text-heading font-extrabold">What is connected right now</h2>
      <p className="max-w-3xl text-body text-muted">
        With an AI Gateway key the agent chooses tools. Without it, the same tools run as a spoken checklist. Sign-in
        is Clerk when a publishable key is present, plus a local demo engineer that never leaves this machine.
      </p>
      <AgentStatus />
      <Card className="flex flex-wrap items-center gap-2 bg-surface/80 backdrop-blur-md">
        <h3 className="text-title">Sign-in</h3>
        <Pill tone={clerkOn ? "primary" : "muted"}>{clerkOn ? "Clerk on" : "Local login only"}</Pill>
        <p className="w-full text-body text-muted">
          {clerkOn
            ? "Google or email is available on the workspace door. Secrets stay in env files, not on this page."
            : "Clerk is not configured. Use the demo engineer on the login page."}
        </p>
      </Card>
    </section>
  );
}
