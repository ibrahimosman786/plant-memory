"use client";

import { ArrowRight } from "lucide-react";
import { useAuth } from "@/components/providers";
import { LinkButton } from "@/components/ui/button";

export function SplashHero() {
  const { ready, token } = useAuth();
  const signedIn = Boolean(token);

  return (
    <section className="relative mx-auto flex min-h-[calc(100svh-3.5rem)] w-full max-w-6xl flex-col items-center justify-center px-4 py-20 text-center">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(ellipse_80%_55%_at_50%_48%,var(--color-canvas)_0%,transparent_72%)]"
      />
      <div className="flex max-w-3xl flex-col items-center">
        <p
          className="pm-in mb-5 inline-flex items-center gap-2 rounded-full border border-hairline bg-surface/70 px-3 py-1 text-caption text-muted uppercase backdrop-blur-md"
        >
          <span aria-hidden="true" className="size-1.5 rounded-full bg-primary" />
          Spartan Controls
        </p>
        <h1
          className="pm-in text-balance text-4xl font-extrabold tracking-tight sm:text-5xl md:text-6xl"
          style={{ animationDelay: "80ms" }}
        >
          An agent that reads the plant records, drafts the upgrade, and never signs its own work.
        </h1>
        <p
          className="pm-in mt-6 max-w-2xl text-pretty text-body text-muted sm:text-title"
          style={{ animationDelay: "160ms" }}
        >
          Plant Memory is the investigation workspace for a panel upgrade. Load the files, ask for a change, and watch
          findings, scope, a CAD estimate, and tests come back with citations. A person still reviews the draft.
        </p>
        <div className="pm-in mt-9 flex flex-wrap items-center justify-center gap-3" style={{ animationDelay: "240ms" }}>
          {ready ? (
            <LinkButton href={signedIn ? "/projects" : "/login"} className="h-11 rounded-full px-6">
              {signedIn ? "Open workspace" : "Enter workspace"}
              <ArrowRight aria-hidden="true" className="size-4" />
            </LinkButton>
          ) : (
            <div className="h-11 w-44 rounded-full bg-surface" />
          )}
          <LinkButton href="#problem" variant="tertiary" className="h-11 rounded-full px-6 backdrop-blur-md">
            Read the story
          </LinkButton>
        </div>
        <p className="pm-in mt-8 max-w-md text-caption text-faint" style={{ animationDelay: "340ms" }}>
          Tap anywhere. Each ring is a ping — the agent answers with evidence, not a signature.
        </p>
      </div>
    </section>
  );
}
