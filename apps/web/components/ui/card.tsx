import type { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export function Card({ className, elevated, ...props }: HTMLAttributes<HTMLDivElement> & { elevated?: boolean }) {
  return (
    <div
      className={cn(
        "bg-surface text-ink rounded-card border border-hairline p-5 shadow-[0_2px_8px_rgba(24,48,71,0.025)]",
        elevated && "shadow-[0_12px_40px_rgba(24,48,71,0.08)]",
        className,
      )}
      {...props}
    />
  );
}

export function Tile({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("bg-surface rounded-card border border-hairline overflow-hidden shrink-0", className)} {...props} />;
}
