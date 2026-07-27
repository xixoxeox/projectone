import { WatchlistDetail } from "@/features/watchlist/components/watchlist-detail";
export default async function WatchlistDetailPage({ params }: { params: Promise<{ tradingDate: string; symbol: string }> }) { const { tradingDate, symbol } = await params; return <WatchlistDetail tradingDate={tradingDate} symbol={symbol}/>; }
