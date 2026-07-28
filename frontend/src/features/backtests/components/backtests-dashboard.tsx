"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { getBacktest, listBacktests } from "../api";
import type { BacktestRun } from "../types";
import { BacktestComparison } from "./backtest-comparison";
import { BacktestAnalysis } from "./backtest-analysis";
import { BacktestCreateForm } from "./backtest-create-form";
import { BacktestRunDetail } from "./backtest-run-detail";
import { BacktestRunList } from "./backtest-run-list";
export function BacktestsDashboard() {
  const [runs, setRuns] = useState<BacktestRun[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [selected, setSelected] = useState<BacktestRun | null>(null);
  const [comparedIds, setComparedIds] = useState<string[]>([]);
  const loadRuns = useCallback(async () => {
    setState("loading");
    try {
      setRuns(
        (await listBacktests())
          .slice()
          .sort((a, b) => b.created_at.localeCompare(a.created_at)),
      );
      setState("ready");
    } catch {
      setState("error");
    }
  }, []);
  useEffect(() => {
    void loadRuns();
  }, [loadRuns]);
  async function select(run: BacktestRun) {
    setSelected(run);
    try {
      setSelected(await getBacktest(run.id));
    } catch {}
  }
  async function created(run: BacktestRun) {
    await loadRuns();
    setSelected(run);
  }
  function compare(id: string) {
    setComparedIds((current) =>
      current.includes(id)
        ? current.filter((value) => value !== id)
        : current.length < 2
          ? [...current, id]
          : [current[1], id],
    );
  }
  const compared = comparedIds
    .map((id) => runs.find((run) => run.id === id))
    .filter((run): run is BacktestRun => Boolean(run));
  return (
    <main className="backtest-shell">
      <nav aria-label="주요 메뉴">
        <Link href="/dashboard">대시보드</Link>
        <Link href="/watchlist">관심 종목</Link>
        <Link aria-current="page" href="/backtests">
          백테스트
        </Link>
      </nav>
      <header>
        <p className="eyebrow">SPRINT 17</p>
        <h1>백테스트</h1>
        <p className="muted">저장된 실행을 만들고 검토하며 비교합니다.</p>
      </header>
      <BacktestCreateForm onCreated={created} />
      <BacktestRunList
        runs={runs}
        state={state}
        selectedId={selected?.id}
        comparedIds={comparedIds}
        onSelect={(run) => void select(run)}
        onCompare={compare}
        onRetry={() => void loadRuns()}
      />
      {selected && <BacktestRunDetail run={selected} />}
      {selected?.status === "completed" && <BacktestAnalysis runId={selected.id} />}
      <BacktestComparison runs={compared} />
    </main>
  );
}
