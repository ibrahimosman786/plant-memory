"use client";

import { FormEvent, useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/components/providers";
import { ClerkEntry } from "@/components/auth/clerk-entry";
import { AgentStatus } from "@/components/guide/agent-status";
import { HowItWorks } from "@/components/guide/how-it-works";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Select, TextInput } from "@/components/ui/input";
import type { Role } from "@/lib/types";

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("engineer@spartan.local");
  const [name, setName] = useState("Spartan engineer");
  const [role, setRole] = useState<Role>("admin");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setPending(true);
    setError(null);
    try {
      const res = await api.devToken({ email, name, role, org_name: "Spartan Controls (dev)" });
      await login(res.token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not enter the workspace");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="min-h-dvh bg-canvas px-4 py-8">
      <div className="mx-auto grid max-w-5xl gap-6 lg:grid-cols-[minmax(0,380px)_1fr]">
      <Card elevated className="w-full space-y-6 p-6 h-fit">
        <div>
          <p className="text-caption text-muted uppercase">Spartan Controls</p>
          <h1 className="text-display font-extrabold">Plant Memory</h1>
          <p className="mt-2 text-body text-muted">
            Enter the Spartan Controls workspace. Use Google or email, or the demo engineer on this machine.
          </p>
        </div>
        <ClerkEntry />
        <form onSubmit={onSubmit} className="space-y-3">
          <label className="block space-y-1">
            <span className="text-caption text-muted">Email</span>
            <TextInput value={email} onChange={(e) => setEmail(e.target.value)} type="email" required />
          </label>
          <label className="block space-y-1">
            <span className="text-caption text-muted">Name</span>
            <TextInput value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label className="block space-y-1">
            <span className="text-caption text-muted">Role</span>
            <Select value={role} onChange={(e) => setRole(e.target.value as Role)}>
              <option value="admin">Administrator</option>
              <option value="reviewer">Reviewer</option>
              <option value="analyst">Analyst</option>
              <option value="viewer">Viewer</option>
            </Select>
          </label>
          {error ? <p className="text-ui">{error}</p> : null}
          <div className="flex gap-2 pt-2">
            <Button type="submit" className="flex-1" disabled={pending}>
              {pending ? "Entering…" : "Enter workspace"}
            </Button>
            <Button
              type="button"
              variant="secondary"
              className="flex-1"
              onClick={() => {
                setEmail("engineer@spartan.local");
                setName("Spartan engineer");
                setRole("admin");
              }}
            >
              Use demo engineer
            </Button>
          </div>
        </form>
      </Card>
      <div className="space-y-6">
        <AgentStatus />
        <HowItWorks />
      </div>
      </div>
    </div>
  );
}
