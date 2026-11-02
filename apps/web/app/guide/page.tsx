"use client";

import Link from "next/link";
import { AppShell } from "@/components/shell/app-shell";
import { AgentStatus } from "@/components/guide/agent-status";
import { HowItWorks } from "@/components/guide/how-it-works";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

export default function GuidePage() {
  return (
    <AppShell>
      <div className="space-y-6 pb-16 max-w-5xl">
        <div>
          <p className="text-caption text-muted uppercase">Start here</p>
          <h1 className="text-display font-extrabold">How to use Plant Memory</h1>
          <p className="text-body text-muted max-w-3xl">
            You do not need to know the database or the agent internals. Follow the five steps. The software tells you when it is waiting on you, and when a step has not happened yet.
          </p>
        </div>
        <AgentStatus />
        <HowItWorks />
        <Card className="space-y-3">
          <h2 className="text-heading font-extrabold">What the agent will not do</h2>
          <ul className="space-y-2 text-body text-muted">
            <li>It does not approve an engineering decision. A person reviews the draft.</li>
            <li>It does not turn a missing document into a fact. The gap stays visible.</li>
            <li>It does not mark a proposed test as passed.</li>
            <li>It does not write to a live controller.</li>
          </ul>
          <Link href="/projects">
            <Button>Back to projects</Button>
          </Link>
        </Card>
      </div>
    </AppShell>
  );
}
