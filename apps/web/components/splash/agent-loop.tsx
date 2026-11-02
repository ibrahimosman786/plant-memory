import { Card } from "@/components/ui/card";

const STEPS = [
  { n: "1", name: "resolve_equipment", body: "Exact tag first. Loose spelling is returned as ambiguity, never guessed." },
  { n: "2", name: "trace_dependencies", body: "Walk recorded relationships from the targets, depth 3 by default, 6 at most." },
  { n: "3", name: "run_consistency_checks", body: "The rule catalogue runs over the affected scope. Failures are reported. Silence is not a clean bill of health." },
  { n: "4", name: "build_work_scope", body: "Templates produce labour and parts. Hours are assumptions until calibrated against actual jobs." },
  { n: "5", name: "build_estimate", body: "Catalogue prices and rate sets. Unpriced stays unpriced. Expired stays expired." },
  { n: "6", name: "draft_checklist", body: "Expected outcomes only when a requirement with evidence exists. Never marked passed." },
  { n: "7", name: "save_draft_package", body: "The server validates the package against this run and this snapshot, then writes a report version." },
];

export function SplashAgentLoop() {
  return (
    <section id="agent" className="scroll-mt-20 space-y-4">
      <p className="text-caption text-primary uppercase">What the agent actually does</p>
      <h2 className="text-heading font-extrabold">Same tools either way. The model only chooses the order.</h2>
      <p className="max-w-3xl text-body text-muted">
        With an AI Gateway key, Claude Sonnet reads the change request, calls these tools, speaks one sentence per
        step, and may ask a clarification. Without a key, the same tools run in this fixed order and the UI says so.
        In both cases the server closes the package. The model cannot pick a tenant, invent a finding, or approve the
        draft.
      </p>
      <ol className="grid gap-3 md:grid-cols-2">
        {STEPS.map((step) => (
          <li key={step.n}>
            <Card className="h-full space-y-2 bg-surface/80 backdrop-blur-md">
              <p className="text-caption text-primary uppercase">
                Step {step.n}
              </p>
              <h3 className="text-title tracking-tight">{step.name}</h3>
              <p className="text-body text-muted">{step.body}</p>
            </Card>
          </li>
        ))}
      </ol>
    </section>
  );
}
