import type { ReactNode } from "react";
import { Card } from "./card";

export function EmptyState({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return (
    <Card className="flex flex-col items-start gap-3 py-8">
      <h3 className="text-heading font-extrabold">{title}</h3>
      <p className="text-body text-muted max-w-xl">{body}</p>
      {action}
    </Card>
  );
}
