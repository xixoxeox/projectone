import { displayDecimal, money, percent } from "../format";
import type { BacktestResult } from "../types";

export const METRIC_LABELS: Record<string, string> = {
  total_signals: "전체 신호",
  entered_trades: "진입 거래",
  skipped_signals: "건너뛴 신호",
  winning_trades: "수익 거래",
  losing_trades: "손실 거래",
  win_rate: "승률",
  gross_profit: "총수익",
  gross_loss: "총손실",
  net_profit: "순이익",
  total_return: "총수익률",
  average_trade_return: "평균 거래 수익률",
  average_holding_days: "평균 보유일",
  profit_factor: "수익 계수",
  max_drawdown: "최대 낙폭",
  max_consecutive_wins: "최대 연속 수익",
  max_consecutive_losses: "최대 연속 손실",
  maximum_gain: "최대 이익",
  maximum_loss: "최대 손실",
};
const RATE_KEYS = new Set([
  "win_rate",
  "total_return",
  "average_trade_return",
  "max_drawdown",
]);
const MONEY_KEYS = new Set([
  "gross_profit",
  "gross_loss",
  "net_profit",
  "maximum_gain",
  "maximum_loss",
]);
export function metricValue(
  key: string,
  value: string | number | null | undefined,
): string {
  if (RATE_KEYS.has(key)) return percent(value);
  if (MONEY_KEYS.has(key)) return money(value);
  return displayDecimal(value);
}
export type ResultValue = BacktestResult[keyof BacktestResult];
