import { auth, currentUser } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

export async function GET() {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Sign in first" }, { status: 401 });
  const user = await currentUser();
  const email = user?.primaryEmailAddress?.emailAddress ?? user?.emailAddresses[0]?.emailAddress;
  if (!email) return NextResponse.json({ error: "This account has no email address" }, { status: 400 });
  const name = user?.fullName || user?.firstName || email.split("@")[0];
  const api = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
  const res = await fetch(`${api}/v1/auth/dev-token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, name, org_name: "Spartan Controls (dev)", role: "admin" }),
  });
  const data = (await res.json().catch(() => null)) as { token?: string; detail?: unknown } | null;
  if (!res.ok || !data?.token) {
    return NextResponse.json({ error: "Could not open the Plant Memory workspace" }, { status: 502 });
  }
  return NextResponse.json({ token: data.token, email, name });
}
