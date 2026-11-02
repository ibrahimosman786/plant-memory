export function cad(value: string | number | null | undefined): string {
  if (value == null || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD" }).format(n);
}

export function bytes(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function when(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("en-CA", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
}

export function kindLabel(kind: string): string {
  return kind.replaceAll("_", " ");
}

export function eventLabel(type: string): string {
  const map: Record<string, string> = {
    "run.created": "Run created",
    "run.started": "Investigation started",
    "snapshot.frozen": "Snapshot frozen",
    "scope.parsed": "Scope parsed",
    "tool.started": "Tool started",
    "tool.completed": "Tool completed",
    "tool.failed": "Tool failed",
    "finding.added": "Finding added",
    "section.completed": "Section completed",
    "section.incomplete": "Section incomplete",
    "clarification.requested": "Clarification requested",
    "clarification.answered": "Clarification answered",
    "limit.reached": "Run limit reached",
    "package.saved": "Draft package saved",
    "run.completed": "Investigation completed",
    "run.failed": "Investigation failed",
    "run.cancelled": "Investigation cancelled",
    "agent.said": "Agent",
  };
  return map[type] ?? type;
}

export function eventSentence(type: string, payload: Record<string, unknown>): string {
  if (typeof payload.text === "string" && payload.text) return payload.text;
  if (typeof payload.question === "string") return payload.question;
  if (typeof payload.title === "string") return payload.title;
  if (typeof payload.error === "string") return payload.error;
  if (type === "tool.started" && typeof payload.tool === "string") return `Running ${payload.tool.replaceAll("_", " ")}`;
  if (type === "tool.completed" && typeof payload.tool === "string") return `Finished ${payload.tool.replaceAll("_", " ")}`;
  if (type === "section.completed" && typeof payload.section === "string") return `Finished the ${payload.section} section`;
  if (type === "snapshot.frozen") return "The investigation is locked to this snapshot";
  if (type === "run.created") return "The investigation was queued";
  if (type === "run.started") return "The agent started";
  if (type === "run.completed") return "The draft package is ready for review";
  return "";
}

export function statusDetailText(detail: unknown): string | null {
  if (!detail) return null;
  if (typeof detail === "string") return detail;
  if (typeof detail !== "object") return null;
  const record = detail as Record<string, unknown>;
  const parts: string[] = [];
  if (typeof record.last_error === "string" && record.last_error) parts.push(record.last_error);
  if (Array.isArray(record.warnings)) {
    const warnings = record.warnings.filter((item): item is string => typeof item === "string" && item.length > 0);
    if (warnings.length) parts.push(warnings.join(" "));
  }
  const extraction = record.extraction;
  if (extraction && typeof extraction === "object") {
    const counts = extraction as Record<string, unknown>;
    const labels: [string, string][] = [
      ["equipment_created", "equipment"],
      ["assertions", "assertions"],
      ["relationships", "links"],
      ["unresolved_references", "unresolved"],
    ];
    const summary = labels
      .filter(([key]) => typeof counts[key] === "number" && (counts[key] as number) > 0)
      .map(([key, label]) => `${counts[key]} ${label}`);
    if (summary.length) parts.push(summary.join(", "));
  }
  if (typeof record.spans === "number") parts.push(`${record.spans} spans`);
  return parts.join(" · ") || null;
}

export function locatorLabel(locator: Record<string, unknown> | null | undefined): string {
  if (!locator) return "source";
  if (typeof locator.page === "number") {
    const extra = locator.bbox ? " · region" : "";
    return `page ${locator.page}${extra}`;
  }
  if (typeof locator.sheet === "string") {
    return `${locator.sheet}${locator.cell_range ? `!${locator.cell_range}` : ""}`;
  }
  if (typeof locator.row === "number") {
    return `row ${locator.row}${locator.column != null ? `, col ${locator.column}` : ""}`;
  }
  return "source";
}
