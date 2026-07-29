import { dateTime, displayDecimal, money, percent } from "../format";
import type { BacktestRun } from "../types";

export function BacktestRunList({
  runs,
  state,
  selectedId,
  comparedIds,
  onSelect,
  onCompare,
  onRetry,
}: {
  runs: BacktestRun[];
  state: "loading" | "ready" | "error";
  selectedId?: string;
  comparedIds: string[];
  onSelect: (run: BacktestRun) => void;
  onCompare: (id: string) => void;
  onRetry: () => void;
}) {
  return (
    <section className="panel">
      <h2>저장된 실행</h2>
      {state === "loading" && <p role="status">실행 목록을 불러오는 중…</p>}
      {state === "error" && (
        <div role="alert">
          실행 목록을 불러오지 못했습니다.{" "}
          <button onClick={onRetry}>다시 시도</button>
        </div>
      )}
      {state === "ready" && runs.length === 0 && (
        <p>저장된 백테스트 실행이 없습니다.</p>
      )}
      {runs.length > 0 && (
        <div className="table-scroll">
          <table>
            <caption className="sr-only">저장된 백테스트 실행</caption>
            <thead>
              <tr>
                {[
                  "비교",
                  "생성",
                  "전략",
                  "실행 모드",
                  "기간",
                  "상태",
                  "진입",
                  "건너뜀",
                  "순이익",
                  "수익률",
                  "실패 코드",
                ].map((heading) => (
                  <th key={heading}>{heading}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr
                  key={run.id}
                  className={selectedId === run.id ? "selected" : ""}
                >
                  <td>
                    <input
                      aria-label={`${run.id} 비교 선택`}
                      type="checkbox"
                      disabled={run.status !== "completed"}
                      checked={comparedIds.includes(run.id)}
                      onChange={() => onCompare(run.id)}
                    />
                  </td>
                  <td>
                    <button
                      className="link-button"
                      onClick={() => onSelect(run)}
                    >
                      {dateTime(run.created_at)}
                    </button>
                  </td>
                  <td>
                    {run.strategy_name} {run.strategy_version ?? "—"}
                  </td>
                  <td>{run.execution_mode === "portfolio" ? "포트폴리오" : "독립 거래"}</td>
                  <td>
                    {run.start_date} – {run.end_date}
                  </td>
                  <td>
                    <span className={`status ${run.status}`}>{run.status}</span>
                  </td>
                  <td>{displayDecimal(run.result?.entered_trades)}</td>
                  <td>{displayDecimal(run.result?.skipped_signals)}</td>
                  <td>{money(run.result?.net_profit)}</td>
                  <td>{percent(run.result?.total_return)}</td>
                  <td>{run.failure_code ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
