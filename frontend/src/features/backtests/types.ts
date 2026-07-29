export type DecimalString = string;
export type BacktestStatus = "pending" | "running" | "completed" | "failed";
export type ExecutionMode = "independent" | "portfolio";

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
  final_equity?: DecimalString;
  final_cash?: DecimalString;
  max_drawdown_pct?: DecimalString;
  maximum_open_positions_used?: number;
  average_capital_utilization?: DecimalString;
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
  execution_mode?: ExecutionMode;
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
  execution_mode: ExecutionMode;
  start_date: string;
  end_date: string;
  position_size: string;
  stop_loss_pct: string;
  take_profit_pct: string;
  max_holding_days: string;
  commission_rate: string;
  sell_tax_rate: string;
  slippage_rate: string;
  initial_capital: string;
  max_open_positions: string;
  position_size_pct: string;
  minimum_cash_buffer_pct: string;
}

export interface PortfolioSnapshot { trading_date:string;cash:DecimalString;market_value:DecimalString;realized_pnl:DecimalString;unrealized_pnl:DecimalString;total_equity:DecimalString;cumulative_return:DecimalString;running_peak_equity:DecimalString;drawdown:DecimalString;drawdown_pct:DecimalString;open_position_count:number }
export interface PortfolioResult { run_id:string;execution_mode:"portfolio";initial_capital:DecimalString;final_equity:DecimalString;final_cash:DecimalString;net_profit:DecimalString;total_return:DecimalString;max_drawdown:DecimalString;max_drawdown_pct:DecimalString;maximum_open_positions_used:number;average_capital_utilization:DecimalString;snapshots:PortfolioSnapshot[] }

export interface AnalysisStats {
  trade_count?: number;
  winning_trades: number; losing_trades: number; breakeven_trades: number;
  win_rate: DecimalString | null; gross_profit?: DecimalString; gross_loss?: DecimalString;
  net_profit: DecimalString; average_trade_pnl: DecimalString | null;
  average_holding_days: DecimalString | null;
  largest_win?: DecimalString | null; largest_loss?: DecimalString | null;
}
export interface BacktestAnalysisSummary extends AnalysisStats {
  average_win: DecimalString | null; average_loss: DecimalString | null;
  profit_factor: DecimalString | null; max_consecutive_wins: number;
  max_consecutive_losses: number; max_realized_pnl_drawdown: DecimalString;
}
export interface BacktestAnalysis {
  run_id: string; trade_count: number; summary: BacktestAnalysisSummary;
  cumulative_realized_pnl: Array<{sequence:number;trade_id:string;exit_date:string;symbol:string;exit_reason:string;net_pnl:DecimalString;cumulative_net_pnl:DecimalString;running_peak:DecimalString;realized_drawdown:DecimalString;realized_drawdown_pct:DecimalString|null}>;
  by_symbol: Array<AnalysisStats & {symbol:string;trade_count:number}>;
  by_exit_reason: Array<AnalysisStats & {exit_reason:string;trade_count:number;trade_share:DecimalString}>;
  by_month: Array<AnalysisStats & {month:string;trade_count:number}>;
}
