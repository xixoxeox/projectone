import { getBacktestAnalysis } from "./api";
import type { BacktestAnalysis } from "./types";

const results = new Map<string, BacktestAnalysis>();
const requests = new Map<string, Promise<BacktestAnalysis>>();

export function cachedBacktestAnalysis(runId: string): BacktestAnalysis | undefined {
  return results.get(runId);
}

export function loadBacktestAnalysis(runId: string): Promise<BacktestAnalysis> {
  const cached = results.get(runId);
  if (cached) return Promise.resolve(cached);
  let request = requests.get(runId);
  if (!request) {
    request = getBacktestAnalysis(runId)
      .then((analysis) => {
        if (
          !Array.isArray(analysis.cumulative_realized_pnl) ||
          !Array.isArray(analysis.by_symbol) ||
          !Array.isArray(analysis.by_exit_reason) ||
          !Array.isArray(analysis.by_month)
        ) throw new Error("Invalid analysis response");
        results.set(runId, analysis);
        return analysis;
      })
      .finally(() => requests.delete(runId));
    requests.set(runId, request);
  }
  return request;
}

export function clearBacktestAnalysisCache(): void {
  results.clear();
  requests.clear();
}
