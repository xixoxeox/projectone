import { getBacktestPortfolio } from "./api";
import type { PortfolioResult } from "./types";

const results = new Map<string, PortfolioResult>();
const requests = new Map<string, Promise<PortfolioResult>>();

export const cachedBacktestPortfolio = (runId: string) => results.get(runId);
export function loadBacktestPortfolio(runId: string): Promise<PortfolioResult> {
  const cached = results.get(runId);
  if (cached) return Promise.resolve(cached);
  let request = requests.get(runId);
  if (!request) {
    request = getBacktestPortfolio(runId)
      .then((result) => {
        if (!Array.isArray(result.snapshots)) throw new Error("Invalid portfolio response");
        results.set(runId, result);
        return result;
      })
      .finally(() => requests.delete(runId));
    requests.set(runId, request);
  }
  return request;
}
export function clearBacktestPortfolioCache(): void { results.clear(); requests.clear(); }
