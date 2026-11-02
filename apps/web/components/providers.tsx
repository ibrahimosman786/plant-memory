"use client";

import { useClerk } from "@clerk/nextjs";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";
import { api, getToken, setToken as persistToken, ApiError } from "@/lib/api";
import type { Me, Role } from "@/lib/types";

let browserQueryClient: QueryClient | undefined;

function getQueryClient() {
  if (typeof window === "undefined") return new QueryClient();
  browserQueryClient ??= new QueryClient({
    defaultOptions: { queries: { staleTime: 8_000, retry: 1, refetchOnWindowFocus: false } },
  });
  return browserQueryClient;
}

type AuthState = {
  ready: boolean;
  token: string | null;
  me: Me | null;
  login: (token: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within Providers");
  return ctx;
}

export function useProjectRole(projectId: string | undefined): Role | null {
  const { me } = useAuth();
  if (!projectId || !me) return null;
  return me.projects.find((p) => p.id === projectId)?.role ?? me.org_role;
}

type EvidenceState = {
  ids: string[];
  open: (ids: string[]) => void;
  close: () => void;
};

const EvidenceContext = createContext<EvidenceState | null>(null);

export function useEvidence() {
  const ctx = useContext(EvidenceContext);
  if (!ctx) throw new Error("useEvidence must be used within Providers");
  return ctx;
}

function ProvidersCore({
  children,
  signOutImpl,
}: {
  children: ReactNode;
  signOutImpl: () => void;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [token, setTokenState] = useState<string | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);
  const [ids, setIds] = useState<string[]>([]);

  const loadMe = useCallback(async (nextToken: string | null) => {
    persistToken(nextToken);
    setTokenState(nextToken);
    if (!nextToken) {
      setMe(null);
      return;
    }
    try {
      setMe(await api.me());
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        persistToken(null);
        setTokenState(null);
        setMe(null);
      }
    }
  }, []);

  useEffect(() => {
    let disposed = false;
    async function hydrate() {
      const stored = getToken();
      let identity: Me | null = null;
      let valid = stored;
      if (stored) {
        try { identity = await api.me(); }
        catch (error) {
          if (error instanceof ApiError && error.status === 401) {
            valid = null;
            persistToken(null);
          }
        }
      }
      return { identity, valid };
    }
    void hydrate().then(({ identity, valid }) => {
      if (disposed) return;
      setMe(identity);
      setTokenState(valid);
      setReady(true);
    });
    return () => { disposed = true; };
  }, [loadMe]);

  useEffect(() => {
    if (!ready) return;
    const isAuthPage = pathname === "/login" || pathname.startsWith("/sign-in") || pathname.startsWith("/sign-up");
    const isPublic = pathname === "/" || isAuthPage;
    if (!token && !isPublic) router.replace("/login");
    if (token && isAuthPage) router.replace("/projects");
  }, [ready, token, pathname, router]);

  const login = useCallback(async (next: string) => {
    await loadMe(next);
    router.replace("/projects");
  }, [loadMe, router]);

  const logout = useCallback(() => {
    persistToken(null);
    setTokenState(null);
    setMe(null);
    getQueryClient().clear();
    try {
      signOutImpl();
    } catch {
      router.replace("/login");
    }
  }, [router, signOutImpl]);

  const auth = useMemo(() => ({ ready, token, me, login, logout }), [ready, token, me, login, logout]);
  const evidence = useMemo(
    () => ({
      ids,
      open: (next: string[]) => setIds(Array.from(new Set(next.filter(Boolean)))),
      close: () => setIds([]),
    }),
    [ids],
  );

  return (
    <QueryClientProvider client={getQueryClient()}>
      <AuthContext.Provider value={auth}>
        <EvidenceContext.Provider value={evidence}>{children}</EvidenceContext.Provider>
      </AuthContext.Provider>
    </QueryClientProvider>
  );
}

function ProvidersWithClerk({ children }: { children: ReactNode }) {
  const { signOut } = useClerk();
  const router = useRouter();
  const signOutImpl = useCallback(() => {
    void signOut({ redirectUrl: "/login" }).catch(() => router.replace("/login"));
  }, [router, signOut]);
  return <ProvidersCore signOutImpl={signOutImpl}>{children}</ProvidersCore>;
}

export function Providers({ children }: { children: ReactNode }) {
  if (process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY) {
    return <ProvidersWithClerk>{children}</ProvidersWithClerk>;
  }
  return (
    <ProvidersCore signOutImpl={() => {
      if (typeof window !== "undefined") window.location.assign("/login");
    }}
    >
      {children}
    </ProvidersCore>
  );
}
