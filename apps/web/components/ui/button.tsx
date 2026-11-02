import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

const variants = {
  primary: "bg-primary text-on-primary rounded-lg min-h-11 px-3 py-2",
  secondary: "bg-secondary text-on-primary rounded-lg min-h-11 px-3 py-2",
  tertiary: "bg-surface text-ink rounded-xl min-h-11 px-3 py-2 border border-hairline",
  ghost: "bg-surface text-ink rounded-lg h-8 px-2 border border-hairline",
} as const;

export function Button({
  variant = "primary",
  className,
  type = "button",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: keyof typeof variants }) {
  return (
    <button
      type={type}
      className={cn(
        "inline-flex items-center justify-center gap-2 text-body font-semibold active:brightness-90 disabled:pointer-events-none disabled:opacity-40",
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}
