import { auth, currentUser } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

export async function GET() {
  const { userId } = await auth.protect();
  if (!userId) return NextResponse.json({ error: "Sign in first" }, { status: 401 });
  const user = await currentUser();
  const address = user?.primaryEmailAddress;
  const email = address?.emailAddress;
  if (!email) return NextResponse.json({ error: "This account has no email address" }, { status: 400 });
  if (address?.verification?.status !== "verified") return NextResponse.json({ error: "Verify your primary email before opening the workspace" }, { status: 403 });
  const name = user?.fullName || user?.firstName || email.split("@")[0];
  const api = process.env.API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
  const exchange = process.env.SESSION_EXCHANGE_SECRET;
  if (process.env.NODE_ENV === "production" && !exchange) {
    return NextResponse.json({ error: "Secure workspace sign-in is not configured" }, { status: 503 });
  }
  const res = await fetch(`${api}/v1/auth/${exchange ? "session" : "dev-token"}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(exchange ? { "X-Session-Exchange": exchange } : {}) },
    body: JSON.stringify(exchange ? { subject: userId, email, name } : { email, name, org_name: "Spartan Controls (dev)", role: "admin" }),
    cache: "no-store",
    signal: AbortSignal.timeout(15000),
  });
  const data = (await res.json().catch(() => null)) as { token?: string; detail?: unknown } | null;
  if (!res.ok || !data?.token) {
    return NextResponse.json({ error: "Could not open the Plant Memory workspace" }, { status: 502 });
  }
  return NextResponse.json({ token: data.token, email, name }, { headers: { "Cache-Control": "no-store" } });
}
