export type Instrument = {
  symbol: string;
  name: string;
  market: string;
  currency: string;
  source: string;
  as_of: string;
};

export type Quote = {
  symbol: string;
  price: string;
  currency: string;
  source: string;
  as_of: string;
  delayed: boolean | null;
};

export type DailyBar = {
  symbol: string;
  trading_date: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: number;
  source: string;
  as_of: string;
};

export type MinuteBar = {
  symbol: string;
  timestamp: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: number;
  currency: string;
  source: string;
  as_of: string;
};

export type Timeframe = "1m" | "5m" | "10m";
export type ChartView = "daily" | Timeframe;
export type Trend = "bullish" | "pullback" | "neutral" | "bearish" | "insufficient";

export type DailySummary = {
  screening_trading_date: string | null;
  trend: Trend;
  previous_close: string | null;
  change_pct: string | null;
  sma20: string | null;
  sma60: string | null;
  ema20: string | null;
  atr_pct: string | null;
  recent_high_20: string | null;
  recent_low_20: string | null;
  screening_passed: boolean;
  matched_setups: string[];
  primary_setup: string | null;
  total_score: string | null;
  score_threshold: string;
  meets_score_threshold: boolean;
  common_failures: string[];
  setup_progress: Record<string, { passed_rules: number; total_rules: number }>;
};

export type IntradaySummary = {
  timeframe: Timeframe;
  trend: Trend;
  candle_count: number;
  session_open: string | null;
  session_high: string | null;
  session_low: string | null;
  change_from_open_pct: string | null;
  sma5: string | null;
  sma20: string | null;
  vwap: string | null;
  momentum_5_pct: string | null;
  latest_volume_ratio: string | null;
  recent_high_20: string | null;
  recent_low_20: string | null;
};

export type PriceLevel = { price: string; basis: string[] };

export type StockWarning = {
  warning_type: string;
  active: boolean;
  description: string | null;
};

export type RealtimeAnalysis = {
  instrument: Instrument;
  quote: Quote;
  as_of: string;
  timezone: string;
  refresh_after_seconds: number;
  daily_bars: DailyBar[];
  intraday_bars: Record<Timeframe, MinuteBar[]>;
  daily: DailySummary;
  intraday: Record<Timeframe, IntradaySummary>;
  levels: { supports: PriceLevel[]; resistances: PriceLevel[] };
  verdict: string;
  observations: string[];
  entry_confirmation: string;
  invalidation: string;
  risk_flags: string[];
  warnings: StockWarning[];
  notes: string[];
};
