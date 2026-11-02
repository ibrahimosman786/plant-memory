"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/projects");
  }, [router]);
  return <div className="min-h-dvh bg-canvas" />;
}
