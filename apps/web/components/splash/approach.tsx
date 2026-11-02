import { Card } from "@/components/ui/card";

const MOVES = [
  {
    title: "Evidence is a span, not a vibe",
    body: "Every extracted fact points at a page region, a spreadsheet row, or a config record. Document text is evidence. It is never treated as an instruction to the model.",
  },
  {
    title: "Findings come from versioned rules",
    body: "Duplicate tags, conflicting ranges, unpriced lines, expired prices, unsupported compatibility claims. The catalogue is code. The model does not invent a finding and cannot mark one verified.",
  },
  {
    title: "Money is Decimal, and incomplete stays incomplete",
    body: "Labour and parts are summed with Decimal arithmetic. Unpriced and expired lines are listed, never folded into the subtotal as zero. Scenario totals only appear when every included line is priced.",
  },
  {
    title: "Reuse is a candidate until a person says so",
    body: "Existing cards, enclosure, and power supply can be shown as reuse candidates. Compatibility is not assumed. The engineer still decides.",
  },
  {
    title: "The draft is not the decision",
    body: "A report version is review_ready until a reviewer accepts, changes, or rejects it. AI output never promotes itself to verified. A proposed test is never created as passed.",
  },
  {
    title: "No live plant",
    body: "The workspace reads uploaded files. It does not connect to a PLC or DCS, and it does not write a configuration. The synthetic pumping station is the demonstration plant.",
  },
];

export function SplashApproach() {
  return (
    <section id="approach" className="scroll-mt-20 space-y-4">
      <p className="text-caption text-primary uppercase">How this was approached</p>
      <h2 className="text-heading font-extrabold">Put the model in a box. Put the engineering outside it.</h2>
      <p className="max-w-3xl text-body text-muted">
        The agent is useful for reading a request, choosing which checks to run, and asking when a tag is ambiguous.
        The things Spartan cannot afford to get wrong — isolation, prices, conflicts, completeness — stay on the
        server as deterministic tools.
      </p>
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        {MOVES.map((item) => (
          <Card key={item.title} className="space-y-2 bg-surface/80 backdrop-blur-md">
            <h3 className="text-title">{item.title}</h3>
            <p className="text-body text-muted">{item.body}</p>
          </Card>
        ))}
      </div>
    </section>
  );
}
