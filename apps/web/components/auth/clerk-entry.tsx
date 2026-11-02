"use client";

import { Show, SignInButton, SignUpButton, useAuth as useClerkAuth } from "@clerk/nextjs";
import { Suspense, useEffect, useState } from "react";
import { useAuth } from "@/components/providers";
import { Button } from "@/components/ui/button";

export function ClerkEntry() {
  const { isLoaded, isSignedIn } = useClerkAuth();
  const { login, token } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoaded || !isSignedIn || token) return;
    let cancel = false;
    (async () => {
      try {
        const res = await fetch("/api/plant-session");
        const data = (await res.json()) as { token?: string; error?: string };
        if (!res.ok || !data.token) throw new Error(data.error || "Could not open the workspace");
        if (!cancel) await login(data.token);
      } catch (err) {
        if (!cancel) setError(err instanceof Error ? err.message : "Could not open the workspace");
      }
    })();
    return () => {
      cancel = true;
    };
  }, [isLoaded, isSignedIn, token, login]);

  return (
    <div className="space-y-2">
      <Suspense>
        <Show when="signed-out">
          <SignInButton mode="modal">
            <Button type="button" className="w-full">
              Sign in with Google or email
            </Button>
          </SignInButton>
          <SignUpButton mode="modal">
            <Button type="button" variant="secondary" className="w-full">
              Create an account
            </Button>
          </SignUpButton>
        </Show>
        <Show when="signed-in">
          <p className="text-body text-muted">{error ?? "Signed in. Opening the Spartan Controls workspace…"}</p>
        </Show>
      </Suspense>
      <p className="text-caption text-muted">A Google or email account joins this local workspace so you can open the demo project. The demo engineer button below does the same without leaving this machine.</p>
    </div>
  );
}
