import type { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export function Card({ className, elevated, ...props }: HTMLAttributes<HTMLDivElement> & { elevated?: boolean }) {
  return (
    <div
      className={cn(
        "bg-surface text-ink rounded-card border border-hairline p-4",
        elevated && "shadow-[0_12px_40px_rgba(0,0,0,0.4)]",
        className,
      )}
      {...props}
    />
  );
}

export function Tile({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("bg-surface rounded-card border border-hairline overflow-hidden shrink-0", className)} {...props} />;
}
