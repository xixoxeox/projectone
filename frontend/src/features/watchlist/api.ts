import type { ScreenerDefinitions, ScreeningExecution, WatchlistDetail, WatchlistItem } from "./types";

const API_BASE_PATH = process.env.NEXT_PUBLIC_API_BASE_PATH ?? "/api/v1";

export class WatchlistApiError extends Error {
  constructor(public readonly status: number | null) {
    super(status === 404 ? "요청한 관심 종목을 찾을 수 없습니다." : "관심 종목을 불러오지 못했습니다.");
    this.name = "WatchlistApiError";
  }
}

async function get<T>(path: string): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_PATH}${path}`, { headers: { Accept: "application/json" } });
  } catch {
    throw new WatchlistApiError(null);
  }
  if (!response.ok) throw new WatchlistApiError(response.status);
  return response.json() as Promise<T>;
}

export const getLatestWatchlist = () => get<WatchlistItem[]>("/watchlist/latest");
export const getWatchlistHistory = () => get<string[]>("/watchlist/history");
export const getWatchlistByDate = (date: string) => get<WatchlistItem[]>(`/watchlist/${encodeURIComponent(date)}`);
export const getWatchlistDetail = (date: string, symbol: string) =>
  get<WatchlistDetail>(`/watchlist/${encodeURIComponent(date)}/${encodeURIComponent(symbol)}`);
export const getScreenerDefinitions = () => get<ScreenerDefinitions>("/screener/definitions");
export const getLatestScreeningExecution = () => get<ScreeningExecution>("/admin/watchlist/executions/latest");
export async function runScreening(): Promise<ScreeningExecution> {
  const response=await fetch(`${API_BASE_PATH}/admin/watchlist/run`,{method:"POST",headers:{Accept:"application/json","Content-Type":"application/json"},body:"{}"});
  if(!response.ok) throw new WatchlistApiError(response.status);
  return response.json() as Promise<ScreeningExecution>;
}
