import { Card } from "@/components/ui/card";

const LIMITS = [
  { label: "Tool calls per run", value: "20" },
  { label: "Clarification cycles", value: "2" },
  { label: "Active deadline", value: "10 min" },
  { label: "Cost ceiling per run", value: "USD 1.50" },
  { label: "Monthly model budget", value: "USD 200" },
  { label: "Traversal depth", value: "3 default, 6 max" },
];

const RULES = [
  "Document text is evidence, never instructions.",
  "AI output never self-promotes to verified.",
  "A failed lookup is not “no issue found”.",
  "Conflicting assertions are preserved until an engineer decides.",
  "Authorization is injected server-side. The model cannot choose a tenant.",
  "Provider credentials never enter the browser.",
];

export function SplashGuardrails() {
  return (
    <section id="guardrails" className="scroll-mt-20 space-y-4">
      <p className="text-caption text-primary uppercase">Guardrails</p>
      <h2 className="text-heading font-extrabold">The demo is bounded so a runaway run cannot become a bill or a plant event.</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {LIMITS.map((item) => (
          <Card key={item.label} className="space-y-1 bg-surface/80 backdrop-blur-md">
            <p className="text-caption text-muted uppercase">{item.label}</p>
            <p className="text-title">{item.value}</p>
          </Card>
        ))}
      </div>
      <Card className="space-y-3 bg-surface/80 backdrop-blur-md">
        <h3 className="text-title">What the agent is forbidden to do</h3>
        <ul className="grid gap-2 md:grid-cols-2">
          {RULES.map((rule) => (
            <li key={rule} className="text-body text-muted">
              {rule}
            </li>
          ))}
        </ul>
      </Card>
    </section>
  );
}
