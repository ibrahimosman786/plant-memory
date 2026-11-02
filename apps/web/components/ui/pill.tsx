import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

const tones = {
  primary: "bg-primary/10 text-primary",
  secondary: "bg-secondary/10 text-secondary",
  outline: "border border-hairline text-ink bg-transparent",
  muted: "border border-hairline text-muted bg-surface",
  live: "bg-secondary/10 text-secondary",
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
    <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-caption font-medium", tones[tone], className)}>
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
