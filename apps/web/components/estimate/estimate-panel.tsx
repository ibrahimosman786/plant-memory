"use client";

import { Card } from "@/components/ui/card";
import { Pill } from "@/components/ui/pill";
import { cad } from "@/lib/format";
import type { Estimate } from "@/lib/types";
import { useEvidence } from "@/components/providers";

export function EstimatePanel({ estimate }: { estimate: Estimate | null }) {
  const { open } = useEvidence();
  if (!estimate) {
    return (
      <Card>
        <h3 className="text-heading font-extrabold">Estimate</h3>
        <p className="mt-2 text-body text-muted">No estimate has been calculated for this run.</p>
      </Card>
    );
  }

  const rows = [...estimate.lines, ...estimate.allowances, ...estimate.unpriced];

  return (
    <Card className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-caption text-muted uppercase">Supported estimate</p>
          <h3 className="text-heading font-extrabold">Priced subtotal {cad(estimate.priced_subtotal)}</h3>
          <p className="text-ui text-muted">CAD · rate set {estimate.rate_set_version}</p>
        </div>
        <Pill tone={estimate.complete ? "primary" : "outline"}>{estimate.complete ? "Complete inputs" : "Incomplete"}</Pill>
      </div>
      {!estimate.complete ? (
        <p className="text-body text-muted">
          This is not a project total. Unpriced work and missing inputs remain visible instead of being filled with zero.
        </p>
      ) : null}
      <div className="overflow-x-auto">
        <table className="w-full text-ui">
          <thead>
            <tr className="text-left text-caption text-muted uppercase">
              <th className="py-2 pr-3">Description</th>
              <th className="py-2 pr-3">Qty</th>
              <th className="py-2 pr-3">Unit price</th>
              <th className="py-2 pr-3">Extended</th>
              <th className="py-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((line) => (
              <tr key={line.id} className="border-t border-hairline">
                <td className="py-2 pr-3">
                  <button
                    className="text-left text-secondary"
                    disabled={!line.evidence_ids?.length}
                    onClick={() => line.evidence_ids && open(line.evidence_ids)}
                  >
                    {line.description}
                  </button>
                </td>
                <td className="py-2 pr-3 whitespace-nowrap">
                  {line.quantity} {line.unit}
                </td>
                <td className="py-2 pr-3">{cad(line.unit_price)}</td>
                <td className="py-2 pr-3">{cad(line.extended)}</td>
                <td className="py-2">
                  <Pill tone={line.pricing_status === "priced" ? "primary" : "outline"}>{line.pricing_status}</Pill>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {estimate.scenarios && estimate.scenarios.length > 0 ? (
        <div>
          <p className="text-caption text-muted uppercase mb-2">Scenarios from stated input ranges — not a statistical interval</p>
          <div className="flex flex-wrap gap-2">
            {estimate.scenarios.map((s) => (
              <Pill key={s.name} tone="muted">
                {s.name}: {cad(s.total)}
              </Pill>
            ))}
          </div>
        </div>
      ) : null}
      {estimate.exclusions.length > 0 ? (
        <ul className="text-ui text-muted space-y-1">
          {estimate.exclusions.map((e) => (
            <li key={e}>Excluded: {e}</li>
          ))}
        </ul>
      ) : null}
    </Card>
  );
}
