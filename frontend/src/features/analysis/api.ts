import { apiRequest } from "@/lib/api";

import type { RealtimeAnalysis } from "./types";

export const getRealtimeAnalysis = (symbol: string): Promise<RealtimeAnalysis> =>
  apiRequest<RealtimeAnalysis>(`/instruments/${encodeURIComponent(symbol)}/analysis`, {
    cache: "no-store",
  });
