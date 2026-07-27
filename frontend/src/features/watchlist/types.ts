/** Decimal API fields intentionally remain strings to preserve precision. */
export type DecimalString = string;

export interface WatchlistItem {
  rank: number;
  symbol: string;
  total_score: DecimalString;
  component_scores: Record<string, DecimalString>;
  warnings: string[];
}

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
