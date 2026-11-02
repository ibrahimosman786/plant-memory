import { Card } from "@/components/ui/card";

const PROBLEMS = [
  {
    title: "Records disagree and nobody can see it",
    body: "The I/O list, the datasheet, and the PLC export can all claim a different range for the same tag. The conflict lives in three files. The quote is written from whichever file was open last.",
  },
  {
    title: "Missing price becomes zero",
    body: "A catalogue row with no unit price is easy to skip. The subtotal still looks complete. The customer sees a number that was never a price.",
  },
  {
    title: "Vendor language is treated as fact",
    body: "“Fully compatible”, “requires no program changes”, “tests passed” sit in a memo with no test record attached. They migrate into the proposal as if they were verified.",
  },
  {
    title: "The citation is gone by the time the quote is sent",
    body: "An engineer can tell you PT-103A came from a datasheet. The recipient cannot click back to the page. Review becomes a conversation about memory, not evidence.",
  },
];

export function SplashProblem() {
  return (
    <section id="problem" className="scroll-mt-20 space-y-4">
      <p className="text-caption text-primary uppercase">The problem</p>
      <h2 className="text-heading font-extrabold">Upgrade assessments are assembled by hand from files that do not agree.</h2>
      <p className="max-w-3xl text-body text-muted">
        Spartan is asked to replace a panel, re-range a transmitter, or reuse existing I/O. The answer has to come from
        equipment lists, spreadsheets, P&amp;IDs, narratives, and vendor notes that were written years apart. The work
        is slow not because the engineer cannot think, but because the records will not sit still.
      </p>
      <div className="grid gap-3 md:grid-cols-2">
        {PROBLEMS.map((item) => (
          <Card key={item.title} className="space-y-2 bg-surface/80 backdrop-blur-md">
            <h3 className="text-title">{item.title}</h3>
            <p className="text-body text-muted">{item.body}</p>
          </Card>
        ))}
      </div>
    </section>
  );
}
