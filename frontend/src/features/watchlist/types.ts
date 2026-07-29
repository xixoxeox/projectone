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

export interface ScreeningSnapshot {
  symbol: string;
  passed: boolean;
  metrics: Record<string, DecimalString>;
  reasons: string[];
  warnings: string[];
}

export interface WatchlistDetail extends WatchlistItem {
  trading_date: string;
  snapshot: ScreeningSnapshot;
  metrics: Record<string, DecimalString>;
  reasons: string[];
}
