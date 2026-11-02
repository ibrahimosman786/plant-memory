import { Card } from "@/components/ui/card";

const LAYERS = [
  {
    title: "Workspace",
    items: ["Next.js UI", "Clerk sign-in", "Evidence viewer", "Dependency graph"],
  },
  {
    title: "API",
    items: ["FastAPI", "Row-level security", "Uploads and snapshots", "Reviews and export"],
  },
  {
    title: "Agent",
    items: ["In-process gateway", "Claude via AI Gateway", "Signed run token", "Tool cap and budget"],
  },
  {
    title: "Records",
    items: ["Postgres 16 + pgvector", "Valkey", "Local files or S3", "Frozen snapshots"],
  },
];

const FACTS = [
  {
    title: "Tenant is injected, not chosen",
    body: "The API mints a short-lived run token with org, project, snapshot, and run id. The model never selects a tenant.",
  },
  {
    title: "A snapshot freezes the files",
    body: "An investigation reads a named set of document versions. A later upload does not silently rewrite a run that already started. Superseded evidence is a finding.",
  },
  {
    title: "Hybrid search, then rules",
    body: "Tag match, lexical search, and vector search are fused. Passages go to the model as evidence. Conflicts are decided by the rule catalogue, not by similarity.",
  },
];

export function SplashArchitecture() {
  return (
    <section id="architecture" className="scroll-mt-20 space-y-4">
      <p className="text-caption text-primary uppercase">Architecture</p>
      <h2 className="text-heading font-extrabold">Four layers. The plant stays on the other side of a file upload.</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {LAYERS.map((layer, i) => (
          <Card key={layer.title} className="space-y-3 bg-surface/80 backdrop-blur-md">
            <p className="text-caption text-muted uppercase">Layer {i + 1}</p>
            <h3 className="text-title">{layer.title}</h3>
            <ul className="space-y-1 text-body text-muted">
              {layer.items.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </Card>
        ))}
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        {FACTS.map((fact) => (
          <Card key={fact.title} className="space-y-2 bg-surface/80 backdrop-blur-md">
            <h3 className="text-title">{fact.title}</h3>
            <p className="text-body text-muted">{fact.body}</p>
          </Card>
        ))}
      </div>
    </section>
  );
}
