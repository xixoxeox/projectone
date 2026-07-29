/** Decimal API fields intentionally remain strings to preserve precision. */
export type DecimalString = string;

export interface WatchlistItem {
  rank: number;
  symbol: string;
  total_score: DecimalString;
  component_scores: Record<string, DecimalString>;
  warnings: string[];
  primary_setup?: string | null;
  matched_setups?: string[];
  screener_name?: string | null;
  screener_version?: string | null;
}

export interface ScreeningSnapshot {
  symbol: string;
  passed: boolean;
  metrics: Record<string, DecimalString>;
  reasons: string[];
  warnings: string[];
  primary_setup?: string | null;
  matched_setups?: string[];
  screener_name?: string | null;
  screener_version?: string | null;
  setup_scores?: Record<string, DecimalString>;
  configuration_snapshot?: Record<string, string | number>;
  setup_metrics?: Record<string, Record<string, DecimalString>>;
  rule_evaluations?: Record<string, boolean>;
}

export interface WatchlistDetail extends WatchlistItem {
  trading_date: string;
  snapshot: ScreeningSnapshot;
  metrics: Record<string, DecimalString>;
  reasons: string[];
  setup_scores?: Record<string, DecimalString>;
  configuration_snapshot?: Record<string, string | number>;
  setup_metrics?: Record<string, Record<string, DecimalString>>;
  rule_evaluations?: Record<string, boolean>;
}
