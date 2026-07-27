import { Suspense } from "react";
import { WatchlistDashboard } from "@/features/watchlist/components/watchlist-dashboard";
import { WatchlistLoading } from "@/features/watchlist/components/states";
export default function WatchlistPage() { return <Suspense fallback={<main className="watchlist-shell"><WatchlistLoading/></main>}><WatchlistDashboard/></Suspense>; }
