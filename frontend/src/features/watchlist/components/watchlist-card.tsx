import Link from "next/link";
import { formatDecimal } from "../format";
import type { WatchlistItem } from "../types";

export function WatchlistCard({ item, tradingDate }: { item: WatchlistItem; tradingDate: string }) {
  return <article className="watchlist-card">
    <Link className="card-link" href={`/watchlist/${encodeURIComponent(tradingDate)}/${encodeURIComponent(item.symbol)}`} aria-label={`${item.symbol} 상세 보기`}>
      <div className="rank" aria-label={`순위 ${item.rank}위`}><span>RANK</span>{item.rank}</div>
      <div className="candidate-main"><h2>{item.symbol}</h2><p className="score"><span>종합 점수</span>{formatDecimal(item.total_score)}</p></div>
      <dl className="component-grid">{Object.entries(item.component_scores).map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{formatDecimal(value)}</dd></div>)}</dl>
      <div className={item.warnings.length ? "warning warning-active" : "warning warning-clear"}>
        <strong>{item.warnings.length ? `⚠ 경고 ${item.warnings.length}건` : "✓ 경고 없음"}</strong>
        {item.warnings.length > 0 && <ul>{item.warnings.map((warning, index) => <li key={`${warning}-${index}`}>{warning}</li>)}</ul>}
      </div>
    </Link>
  </article>;
}
