import type { InputHTMLAttributes, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export function TextInput({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "w-full bg-surface text-ink placeholder:text-faint border border-hairline rounded-md px-3 py-2 text-body",
        className,
      )}
      {...props}
    />
  );
}

export function TextArea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "w-full bg-surface text-ink placeholder:text-faint border border-hairline rounded-md px-3 py-2 text-body resize-y min-h-28",
        className,
      )}
      {...props}
    />
  );
}

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "w-full bg-surface text-ink border border-hairline rounded-md px-3 py-2 text-body",
        className,
      )}
      {...props}
    />
  );
}
