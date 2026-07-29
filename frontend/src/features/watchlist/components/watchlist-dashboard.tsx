"use client";
import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { getLatestWatchlist, getWatchlistByDate, getWatchlistHistory, WatchlistApiError } from "../api";
import type { WatchlistItem } from "../types";
import { WatchlistCard } from "./watchlist-card";
import { WatchlistDateSelector } from "./watchlist-date-selector";
import { WatchlistEmpty, WatchlistError, WatchlistLoading } from "./states";

type Status = "loading" | "ready" | "empty" | "not-found" | "error";
export function WatchlistDashboard() {
  const router = useRouter(); const searchParams = useSearchParams();
  const requestedDate = searchParams.get("date") ?? "";
  const [items, setItems] = useState<WatchlistItem[]>([]); const [dates, setDates] = useState<string[]>([]);
  const [selectedDate, setSelectedDate] = useState(requestedDate); const [status, setStatus] = useState<Status>("loading"); const [attempt, setAttempt] = useState(0);
  const load = useCallback(async () => {
    void attempt;
    setStatus("loading");
    try {
      const history = (await getWatchlistHistory()).slice().sort((a,b) => b.localeCompare(a));
      setDates(history);
      const date = requestedDate || history[0] || ""; setSelectedDate(date);
      const result = requestedDate ? await getWatchlistByDate(requestedDate) : await getLatestWatchlist();
      setItems(result.slice().sort((a,b) => a.rank - b.rank)); setStatus(result.length ? "ready" : "empty");
    } catch (error) { setStatus(error instanceof WatchlistApiError && error.status === 404 ? "not-found" : "error"); }
  }, [requestedDate, attempt]);
  useEffect(() => { void load(); }, [load]);
  const selectDate = (date: string) => { setSelectedDate(date); router.push(`/watchlist?date=${encodeURIComponent(date)}`); };
  return <main className="watchlist-shell"><nav aria-label="주요 메뉴"><a href="/screener">스크리너</a></nav><header className="watchlist-header"><p className="eyebrow">KOSPI SWING WATCHLIST</p><h1>관심 종목</h1><p>순위와 경고를 빠르게 확인하세요.</p></header>
    {dates.length > 0 && <WatchlistDateSelector dates={dates} selected={selectedDate} onSelect={selectDate}/>} 
    {selectedDate && <p className="as-of" aria-live="polite">기준일 <strong>{selectedDate}</strong></p>}
    {status === "loading" && <WatchlistLoading/>}{status === "ready" && <section className="watchlist-list" aria-label="순위별 관심 종목">{items.map(item => <WatchlistCard key={item.symbol} item={item} tradingDate={selectedDate}/>)}</section>}
    {status === "empty" && <WatchlistEmpty/>}{status === "not-found" && <WatchlistEmpty notFound/>}{status === "error" && <WatchlistError onRetry={() => setAttempt(value => value + 1)}/>} 
  </main>;
}
