import { dateTime } from "../format";
import type { BacktestRun } from "../types";
import { BacktestTradesTable } from "./backtest-trades-table";
import { METRIC_LABELS, metricValue, type ResultValue } from "./metrics";
export function BacktestRunDetail({ run }: { run: BacktestRun }) {
  const metadata = [
    ["ID", run.id],
    ["전략", `${run.strategy_name} v${run.strategy_version ?? "—"}`],
    ["실행 모드", run.execution_mode === "portfolio" ? "포트폴리오" : "독립 거래"],
    ["기간", `${run.start_date} – ${run.end_date}`],
    ["데이터 기준", dateTime(run.data_as_of)],
    ["생성", dateTime(run.created_at)],
    ["시작", dateTime(run.started_at)],
    ["완료", dateTime(run.completed_at)],
    ["상태", run.status],
    ["실패 코드", run.failure_code ?? "—"],
    ["실패 메시지", run.failure_message ?? "—"],
  ];
  return (
    <section className="panel">
      <h2>실행 상세</h2>
      <dl className="metric-grid">
        {metadata.map(([key, value]) => (
          <div key={key}>
            <dt>{key}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      {run.result && (
        <>
          <h3>결과 지표</h3>
          <dl className="metric-grid">
            {Object.entries(METRIC_LABELS)
              .filter(([key]) => key in run.result!)
              .map(([key, label]) => (
                <div key={key}>
                  <dt>{label}</dt>
                  <dd>
                    {metricValue(
                      key,
                      run.result?.[
                        key as keyof typeof run.result
                      ] as ResultValue,
                    )}
                  </dd>
                </div>
              ))}
          </dl>
        </>
      )}
      <BacktestTradesTable runId={run.id} />
    </section>
  );
}
