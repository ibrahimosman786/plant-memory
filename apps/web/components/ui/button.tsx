import type { ButtonHTMLAttributes, ReactNode } from "react";
import Link from "next/link";
import { cn } from "@/lib/cn";

const variants = {
  primary: "bg-primary text-on-primary hover:bg-primary/90 shadow-sm rounded-lg min-h-11 px-3 py-2",
  secondary: "bg-white text-primary border border-hairline hover:bg-primary/5 rounded-lg min-h-11 px-3 py-2",
  tertiary: "bg-surface text-ink rounded-xl min-h-11 px-3 py-2 border border-hairline",
  ghost: "bg-surface text-ink rounded-lg h-8 px-2 border border-hairline",
} as const;

const base =
  "inline-flex items-center justify-center gap-2 text-ui font-semibold transition-colors active:brightness-90 disabled:pointer-events-none disabled:opacity-40";

export function Button({
  variant = "primary",
  className,
  type = "button",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: keyof typeof variants }) {
  return <button type={type} className={cn(base, variants[variant], className)} {...props} />;
}

export function LinkButton({
  href,
  variant = "primary",
  className,
  children,
}: {
  href: string;
  variant?: keyof typeof variants;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Link href={href} className={cn(base, variants[variant], className)}>
      {children}
    </Link>
  );
}
