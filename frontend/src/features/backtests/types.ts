export type DecimalString = string;
export type BacktestStatus = "pending" | "running" | "completed" | "failed";

export interface BacktestResult {
  initial_capital?: DecimalString;
  total_signals?: number;
  entered_trades?: number;
  skipped_signals?: number;
  winning_trades?: number;
  losing_trades?: number;
  win_rate?: DecimalString;
  gross_profit?: DecimalString;
  gross_loss?: DecimalString;
  net_profit?: DecimalString;
  total_return?: DecimalString;
  average_trade_return?: DecimalString;
  average_holding_days?: DecimalString;
  profit_factor?: DecimalString | null;
  max_drawdown?: DecimalString;
  max_consecutive_wins?: number;
  max_consecutive_losses?: number;
}

export interface BacktestRun {
  id: string;
  strategy_name: string;
  strategy_version: string | null;
  parameters: Record<string, string | number>;
  start_date: string;
  end_date: string;
  data_as_of: string | null;
  status: BacktestStatus;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  result: BacktestResult | null;
  failure_code: string | null;
  failure_message: string | null;
}

export interface BacktestTrade {
  id: string;
  run_id: string;
  symbol: string;
  signal_date: string;
  entry_date: string;
  entry_price: DecimalString;
  quantity: number;
  exit_date: string;
  exit_price: DecimalString;
  exit_reason: string;
  gross_pnl: DecimalString;
  commission: DecimalString;
  tax: DecimalString;
  slippage_cost: DecimalString;
  net_pnl: DecimalString;
  holding_days: number;
  created_at: string;
}

export interface BacktestFormValues {
  start_date: string;
  end_date: string;
  position_size: string;
  stop_loss_pct: string;
  take_profit_pct: string;
  max_holding_days: string;
  commission_rate: string;
  sell_tax_rate: string;
  slippage_rate: string;
}
