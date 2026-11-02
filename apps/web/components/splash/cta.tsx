"use client";

import { useAuth } from "@/components/providers";
import { LinkButton } from "@/components/ui/button";

export function SplashCta({
  secondaryHref,
  secondaryLabel,
}: {
  secondaryHref?: string;
  secondaryLabel?: string;
}) {
  const { ready, token } = useAuth();
  const signedIn = Boolean(token);

  return (
    <div className="flex flex-wrap gap-2">
      {ready ? (
        <LinkButton href={signedIn ? "/projects" : "/login"} className="h-11 rounded-full px-6">
          {signedIn ? "Open workspace" : "Enter workspace"}
        </LinkButton>
      ) : (
        <div className="h-11 w-40 rounded-full bg-surface" />
      )}
      {secondaryHref && secondaryLabel ? (
        <LinkButton href={secondaryHref} variant="tertiary" className="h-11 rounded-full px-6">
          {secondaryLabel}
        </LinkButton>
      ) : null}
    </div>
  );
}
