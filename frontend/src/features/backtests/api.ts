import type { BacktestAnalysis, BacktestFormValues, BacktestRun, BacktestTrade, PortfolioResult } from "./types";

const API_BASE_PATH = process.env.NEXT_PUBLIC_API_BASE_PATH ?? "/api/v1";
const MAX_TRADE_LIMIT = 500;

export class BacktestApiError extends Error {
  constructor(
    public readonly status: number | null,
    message = "백테스트 요청을 처리하지 못했습니다.",
  ) {
    super(message);
    this.name = "BacktestApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_PATH}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...init?.headers,
      },
    });
  } catch {
    throw new BacktestApiError(null);
  }

  if (!response.ok) {
    let message = "백테스트 요청을 처리하지 못했습니다.";
    try {
      const body = (await response.json()) as {
        detail?: string | Array<{ loc?: Array<string | number>; msg: string }>;
      };
      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (Array.isArray(body.detail)) {
        message = body.detail
          .map((item) => `${item.loc?.at(-1) ?? "입력"}: ${item.msg}`)
          .join(" · ");
      }
    } catch {
      // Keep the safe generic message for malformed error bodies.
    }
    throw new BacktestApiError(response.status, message);
  }
  return response.json() as Promise<T>;
}

export const listBacktests = (): Promise<BacktestRun[]> =>
  request("/backtests");
export const getBacktest = (id: string): Promise<BacktestRun> =>
  request(`/backtests/${encodeURIComponent(id)}`);
export const getBacktestAnalysis = (id: string): Promise<BacktestAnalysis> =>
  request(`/backtests/${encodeURIComponent(id)}/analysis`);
export const getBacktestPortfolio = (id: string): Promise<PortfolioResult> => request(`/backtests/${encodeURIComponent(id)}/portfolio`);

export function createBacktest(
  values: BacktestFormValues,
): Promise<BacktestRun> {
  return request("/backtests", {
    method: "POST",
    body: JSON.stringify({
      strategy_name: "watchlist_entry",
      strategy_version: "1",
      ...(values.execution_mode === "portfolio" ? { execution_mode: "portfolio" } : {}),
      start_date: values.start_date,
      end_date: values.end_date,
      parameters: {
        ...(values.execution_mode === "independent" ? {position_size: values.position_size} : {initial_capital:values.initial_capital,max_open_positions:Number(values.max_open_positions),position_sizing_mode:"fixed_fraction",position_size_pct:values.position_size_pct,minimum_cash_buffer_pct:values.minimum_cash_buffer_pct}),
        stop_loss_pct: values.stop_loss_pct,
        take_profit_pct: values.take_profit_pct,
        max_holding_days: Number(values.max_holding_days),
        commission_rate: values.commission_rate,
        sell_tax_rate: values.sell_tax_rate,
        slippage_rate: values.slippage_rate,
      },
    }),
  });
}

export function listBacktestTrades(
  id: string,
  options: {
    limit: number;
    offset: number;
    symbol?: string;
    exit_reason?: string;
  },
): Promise<BacktestTrade[]> {
  const query = new URLSearchParams({
    limit: String(Math.min(options.limit, MAX_TRADE_LIMIT)),
    offset: String(options.offset),
  });
  if (options.symbol) query.set("symbol", options.symbol);
  if (options.exit_reason) query.set("exit_reason", options.exit_reason);
  return request(`/backtests/${encodeURIComponent(id)}/trades?${query}`);
}
