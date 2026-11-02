import { Card } from "@/components/ui/card";
import { Pill } from "@/components/ui/pill";

export function SplashWorkedExample() {
  return (
    <section id="example" className="scroll-mt-20 space-y-4">
      <p className="text-caption text-primary uppercase">Worked example</p>
      <h2 className="text-heading font-extrabold">Replace CP-101. Keep the field instruments if the records support it.</h2>
      <p className="max-w-3xl text-body text-muted">
        The demonstration plant is a fictional raw-water pumping station. Variant v02 plants two faults that a real
        upgrade would hit: a measurement range that does not agree, and a catalogue part with no price.
      </p>
      <div className="grid gap-3 md:grid-cols-2">
        <Card className="space-y-3 bg-surface/80 backdrop-blur-md">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone="muted">PT-103A</Pill>
            <Pill tone="outline">conflicting_ranges</Pill>
          </div>
          <h3 className="text-title">Pump A discharge pressure</h3>
          <p className="text-body text-muted">
            Config export records 2000 kPa. The datasheet and I/O list record 1600 kPa. Both stay on file. The finding
            asks which value governs the new configuration. The checklist leaves the expected outcome blank until an
            engineer decides. The draft does not pick a winner.
          </p>
        </Card>
        <Card className="space-y-3 bg-surface/80 backdrop-blur-md">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone="muted">KC-HMI-15</Pill>
            <Pill tone="outline">unpriced_line</Pill>
          </div>
          <h3 className="text-title">Optional HMI, no unit price</h3>
          <p className="text-body text-muted">
            The catalogue lists the part and leaves the price empty. The line is shown as unpriced scope. It is never
            summed as zero. The estimate can still be complete for the priced work; the missing quotation stays visible.
          </p>
        </Card>
      </div>
    </section>
  );
}
