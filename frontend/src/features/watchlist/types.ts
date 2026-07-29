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
  latest_close?: DecimalString | null;
  average_trading_value_20?: DecimalString | null;
  latest_volume_ratio?: DecimalString | null;
  prior5_volume_ratio?: DecimalString | null;
  breakout_volume_ratio?: DecimalString | null;
  atr_pct?: DecimalString | null;
}

export interface ScreenerDefinitions { screener_name:string;screener_version:string;setups:Array<{key:string;label:string;description:string}>;defaults:Record<string,string|number>;limitations:string[] }
export interface ScreeningExecution { execution_id?:string;trading_date:string;status:string;started_at:string;finished_at:string|null;candidate_count:number|null;persisted_count:number|null;error_code?:string|null }

export interface ScreeningSnapshot {
  symbol: string;
  passed: boolean;
  metrics: Record<string, DecimalString>;
  reasons: string[];
  warnings: string[];
  matched_setups?: string[];
  primary_setup?: string | null;
  setup_scores?: Record<string, DecimalString>;
  screener_name?: string | null;
  screener_version?: string | null;
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
