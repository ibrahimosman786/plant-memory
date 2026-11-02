import { Card } from "@/components/ui/card";

const STEPS = [
  {
    n: "1",
    title: "Bring the project records in",
    body: "Upload the equipment list, I/O list, drawings, and narrative this project is allowed to use. Plant Memory reads those files. It does not connect to a live panel or write to a PLC.",
  },
  {
    n: "2",
    title: "Freeze a snapshot",
    body: "A snapshot is the set of files an investigation may see. Later uploads do not silently change a run that already started.",
  },
  {
    n: "3",
    title: "Describe the change",
    body: "Say what Spartan is being asked to do, and name the tags. Example: replace the station control panel and keep field instruments where the records support it.",
  },
  {
    n: "4",
    title: "Watch the agent investigate",
    body: "The agent finds the equipment, traces what it connects to, checks for conflicts, and drafts the work, the CAD estimate, and the proposed tests. Each step is written on the run page.",
  },
  {
    n: "5",
    title: "An engineer reviews the draft",
    body: "Nothing is approved because the agent wrote it. A reviewer accepts, changes, or rejects the package. A price that is missing stays unpriced.",
  },
];

export function HowItWorks() {
  return (
    <div className="space-y-3">
      <h2 className="text-heading font-extrabold">Your path from records to review</h2>
      <p className="text-body text-muted max-w-3xl">
        Plant Memory is a workspace for an upgrade assessment. An application engineer loads the project records, asks for an investigation, and reviews the draft before anyone treats it as a decision.
      </p>
      <ol className="grid gap-3 md:grid-cols-2">
        {STEPS.map((step) => (
          <li key={step.n}>
            <Card className="h-full space-y-2">
              <p className="text-caption text-primary uppercase">Step {step.n}</p>
              <h3 className="text-title">{step.title}</h3>
              <p className="text-body text-muted">{step.body}</p>
            </Card>
          </li>
        ))}
      </ol>
    </div>
  );
}
