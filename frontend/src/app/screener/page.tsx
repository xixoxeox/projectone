"use client";

import { AuthGuard } from "@/features/auth/components/AuthGuard";
import { ScreenerDashboard } from "@/features/screener/screener-dashboard";

export default function ScreenerPage() {
  return <AuthGuard><ScreenerDashboard /></AuthGuard>;
}
