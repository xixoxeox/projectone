import { compareDecimal } from "../format";
import type { BacktestRun } from "../types";
import { METRIC_LABELS, metricValue, type ResultValue } from "./metrics";
const KEYS = [
  "total_signals",
  "entered_trades",
  "skipped_signals",
  "win_rate",
  "net_profit",
  "total_return",
  "average_holding_days",
  "maximum_gain",
  "maximum_loss",
];
function relation(own: ResultValue, other: ResultValue): string {
  if (own == null || other == null) return "비교 불가";
  const order = compareDecimal(own, other);
  return order === 0 ? "같음" : order > 0 ? "더 높음" : "더 낮음";
}
export function BacktestComparison({ runs }: { runs: BacktestRun[] }) {
  return (
    <section className="panel">
      <h2>실행 비교</h2>
      {runs.length < 2 ? (
        <p>완료된 서로 다른 실행 두 개를 선택하세요.</p>
      ) : (
        <div className="comparison">
          {runs.map((run, index) => (
            <article key={run.id}>
              <h3>실행 {index + 1}</h3>
              <p>
                {run.start_date} – {run.end_date}
              </p>
              <h4>파라미터</h4>
              <dl>
                {Object.entries(run.parameters).map(([key, value]) => (
                  <div key={key}>
                    <dt>{key}</dt>
                    <dd>{String(value)}</dd>
                  </div>
                ))}
              </dl>
              <h4>지표</h4>
              <dl>
                {KEYS.map((key) => {
                  const own = run.result?.[key as keyof typeof run.result];
                  const other =
                    runs[1 - index].result?.[key as keyof typeof run.result];
                  return (
                    <div key={key}>
                      <dt>{METRIC_LABELS[key]}</dt>
                      <dd>
                        {metricValue(key, own)}{" "}
                        <small>({relation(own, other)}; 설명적 비교)</small>
                      </dd>
                    </div>
                  );
                })}
              </dl>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
