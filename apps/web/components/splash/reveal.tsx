import type { ReactNode } from "react";

export function SplashReveal({ children }: { children: ReactNode }) {
  return <div className="pm-in">{children}</div>;
}
