"use client";

import type { ReactNode } from "react";
import { SonarGrid } from "@/components/ui/sonar-grid";

export function SplashFrame({ children }: { children: ReactNode }) {
  return (
    <SonarGrid
      id="plant-memory-home"
      spacing={28}
      dotRadius={1.35}
      baseOpacity={0.2}
      pingEvery={2.6}
      speed={230}
      ringWidth={110}
      amplitude={2.1}
      interactive
      maxRings={6}
      seedPing
      pingArea={[0.2, 0.22, 0.8, 0.78]}
      className="min-h-svh bg-canvas text-ink"
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(ellipse_42%_36%_at_50%_28%,color-mix(in_srgb,var(--color-canvas)_88%,transparent)_0%,transparent_72%)]"
      />
      {children}
    </SonarGrid>
  );
}
