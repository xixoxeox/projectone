import { AuthGuard } from "@/features/auth/components/AuthGuard";
import { ScreenerDashboard } from "@/features/watchlist/components/screener-dashboard";
export default function ScreenerPage(){return <AuthGuard><ScreenerDashboard/></AuthGuard>}
