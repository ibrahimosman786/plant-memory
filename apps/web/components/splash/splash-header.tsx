"use client";

import Link from "next/link";
import { useAuth } from "@/components/providers";
import { LinkButton } from "@/components/ui/button";

export function SplashHeader() {
  const { ready, token } = useAuth();
  const href = token ? "/projects" : "/login";
  const label = token ? "Open workspace" : "Enter workspace";

  return (
    <header className="sticky top-0 z-30 border-b border-hairline/70 bg-canvas/55 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-3 px-4">
        <Link href="/" className="shrink-0 text-title font-extrabold tracking-tight">
          Plant Memory
        </Link>
        <nav className="hidden items-center gap-4 md:ml-6 md:flex">
          <a href="#problem" className="text-ui text-muted transition-colors hover:text-ink">
            Problem
          </a>
          <a href="#approach" className="text-ui text-muted transition-colors hover:text-ink">
            Approach
          </a>
          <a href="#agent" className="text-ui text-muted transition-colors hover:text-ink">
            Agent
          </a>
          <a href="#architecture" className="text-ui text-muted transition-colors hover:text-ink">
            Architecture
          </a>
        </nav>
        {ready ? (
          <LinkButton href={href} className="ml-auto h-9 rounded-full px-4">
            {label}
          </LinkButton>
        ) : (
          <div className="ml-auto h-9 w-36 rounded-full bg-surface" />
        )}
      </div>
    </header>
  );
}
