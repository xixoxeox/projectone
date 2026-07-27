"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { apiRequest, getMe, setAccessToken } from "@/lib/api";
export function AuthGuard({ children }: { children: ReactNode }) {
  const router = useRouter(); const [ready, setReady] = useState(false);
  useEffect(() => { void (async () => { try { const refreshed = await apiRequest<{access_token:string}>("/auth/refresh", {method:"POST"}); setAccessToken(refreshed.access_token); await getMe(); setReady(true); } catch { router.replace("/login"); } })(); }, [router]);
  return ready ? children : <main className="center"><p>인증 확인 중…</p></main>;
}
