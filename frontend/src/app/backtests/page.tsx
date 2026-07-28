import { AuthGuard } from "@/features/auth/components/AuthGuard";
import { BacktestsDashboard } from "@/features/backtests/components/backtests-dashboard";
export default function BacktestsPage() {
  return (
    <AuthGuard>
      <BacktestsDashboard />
    </AuthGuard>
  );
}
