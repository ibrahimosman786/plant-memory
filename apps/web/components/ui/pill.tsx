import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

const tones = {
  primary: "bg-primary text-on-primary",
  secondary: "bg-secondary text-on-primary",
  outline: "border border-hairline text-ink bg-transparent",
  muted: "border border-hairline text-muted bg-surface",
  live: "bg-secondary text-on-primary",
} as const;

export function Pill({
  tone = "outline",
  className,
  children,
}: {
  tone?: keyof typeof tones;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-caption font-semibold uppercase tracking-wide", tones[tone], className)}>
      {children}
    </span>
  );
}

export function statusTone(status: string): keyof typeof tones {
  if (status === "ready" || status === "approved" || status === "complete" || status === "priced") return "primary";
  if (status === "processing" || status === "running" || status === "queued" || status === "live") return "secondary";
  if (status === "failed" || status === "rejected" || status === "stale") return "outline";
  return "muted";
}
