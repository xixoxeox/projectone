"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiRequestError, apiRequest } from "@/lib/api";

type Definitions = {
  screener_name: string;
  version: string;
  setup_keys: string[];
  setup_labels: Record<string, string>;
};

type Candidate = {
  rank: number;
  symbol: string;
  total_score: string;
  primary_setup?: string | null;
  matched_setups?: string[];
  average_trading_value_20?: string | null;
  atr_pct?: string | null;
  volume_ratio?: string | null;
  prior_short_volume_ratio?: string | null;
  breakout_volume_ratio?: string | null;
  warnings: string[];
};

type Execution = {
  trading_date: string;
  status: string;
  started_at: string;
  finished_at?: string | null;
  screened_count?: number | null;
  candidate_count?: number | null;
  qualified_count?: number | null;
  score_threshold?: string | null;
  persisted_count?: number | null;
  skipped_reason?: string | null;
  trigger_type?: string | null;
};

type ScreenerResults = {
  execution_id: string | null;
  trading_date: string;
  screened_count: number | null;
  setup_passed_count: number | null;
  score_qualified_count: number | null;
  score_threshold: string | null;
  result_count: number | null;
  items: Candidate[];
};

type Sort = "rank" | "score" | "value" | "symbol";

const fallbackLabels: Record<string, string> = {
  box_breakout: "박스권 돌파",
  trend_pullback: "추세 눌림목",
  volatility_contraction_breakout: "변동성 축소 돌파",
};

const digits = (value: string) => {
  const [whole, fraction = ""] = value.split(".");
  return [whole.replace(/^0+(?=\d)/, ""), fraction.replace(/0+$/, "")] as const;
};

export function compareDecimalStrings(left: string, right: string): number {
  const [leftWhole, leftFraction] = digits(left);
  const [rightWhole, rightFraction] = digits(right);
  if (leftWhole.length !== rightWhole.length) return leftWhole.length - rightWhole.length;
  const whole = leftWhole.localeCompare(rightWhole);
  if (whole) return whole;
  const size = Math.max(leftFraction.length, rightFraction.length);
  return leftFraction.padEnd(size, "0").localeCompare(rightFraction.padEnd(size, "0"));
}

export function formatPercent(value: string | null | undefined): string {
  if (value == null) return "—";
  const [whole, fraction = ""] = value.split(".");
  const combined = (whole + fraction.padEnd(2, "0")).replace(/^0+(?=\d)/, "");
  const split = Math.max(0, combined.length - Math.max(0, fraction.length - 2));
  const result = (
    split === combined.length
      ? combined
      : `${combined.slice(0, split) || "0"}.${combined.slice(split)}`
  ).replace(/\.0+$|(?<=\.[0-9]*)0+$/g, "");
  return `${result}%`;
}

function displayDecimal(value: string | null | undefined): string {
  if (value == null) return "—";
  const [whole, fraction = ""] = value.split(".");
  const trimmed = fraction.replace(/0+$/, "");
  return trimmed ? `${whole}.${trimmed}` : whole;
}

function setQuery(key: string, value: string, defaultValue = "") {
  const query = new URLSearchParams(window.location.search);
  if (value === "" || value === defaultValue) query.delete(key);
  else query.set(key, value);
  const suffix = query.toString();
  history.replaceState(null, "", `${location.pathname}${suffix ? `?${suffix}` : ""}`);
}

function EmptyResults({ summary }: { summary: ScreenerResults | null }) {
  if (
    summary?.screened_count != null &&
    summary.score_threshold != null &&
    summary.score_qualified_count === 0
  ) {
    return (
      <section className="state-card screening-empty" aria-live="polite">
        <h2>오늘 기준을 충족한 종목이 없습니다</h2>
        <p>
          총 <strong>{summary.screened_count.toLocaleString("ko-KR")}개</strong> 종목을
          검색했습니다.{" "}
          {summary.setup_passed_count != null && (
            <>
              그중 <strong>{summary.setup_passed_count.toLocaleString("ko-KR")}개</strong>가
              일봉 셋업을 통과했지만,{" "}
            </>
          )}
          종합점수 <strong>{displayDecimal(summary.score_threshold)}점 이상</strong>인
          종목은 <strong>0개</strong>입니다. 그래서 보여드릴 후보가 없습니다.
        </p>
        <p className="muted">
          오류가 아니라 기준에 못 미친 종목을 억지로 추천하지 않은 정상 결과입니다.
        </p>
      </section>
    );
  }
  return (
    <section className="state-card" aria-live="polite">
      <h2>선택한 날짜의 후보가 없습니다</h2>
      <p className="muted">이전 형식의 실행 결과라 상세 검색 건수는 제공되지 않습니다.</p>
    </section>
  );
}

export function ScreenerDashboard() {
  const initial = useMemo(
    () => new URLSearchParams(typeof window === "undefined" ? "" : window.location.search),
    [],
  );
  const [definitions, setDefinitions] = useState<Definitions | null>(null);
  const [historyDates, setHistoryDates] = useState<string[]>([]);
  const [items, setItems] = useState<Candidate[]>([]);
  const [selectedResult, setSelectedResult] = useState<ScreenerResults | null>(null);
  const [execution, setExecution] = useState<Execution | null>(null);
  const [date, setDate] = useState(initial.get("date") ?? "");
  const [setup, setSetup] = useState(initial.get("setup") ?? "");
  const [q, setQ] = useState(initial.get("q") ?? "");
  const [minScore, setMinScore] = useState(initial.get("minScore") ?? "");
  const [minValue, setMinValue] = useState(initial.get("minValue") ?? "");
  const [warningFree, setWarningFree] = useState(initial.get("warningFree") === "1");
  const [sort, setSort] = useState<Sort>((initial.get("sort") as Sort) || "rank");
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState<"normal" | "reanalysis" | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [operationError, setOperationError] = useState("");
  const [failedRequest, setFailedRequest] = useState<"bootstrap" | "date" | null>(null);
  const request = useRef(0);
  const operation = useRef(0);
  const mounted = useRef(true);

  const loadDate = useCallback(async (selected: string) => {
    const id = ++request.current;
    setLoading(true);
    setError("");
    setFailedRequest(null);
    try {
      const result = await apiRequest<ScreenerResults>(
        `/screener/results/${encodeURIComponent(selected)}`,
      );
      if (request.current === id) {
        setSelectedResult(result);
        setItems(result.items);
      }
    } catch {
      if (request.current === id) {
        setError("스크리너 결과를 불러오지 못했습니다.");
        setFailedRequest("date");
      }
    } finally {
      if (request.current === id) setLoading(false);
    }
  }, []);

  const bootstrap = useCallback(async () => {
    setLoading(true);
    setError("");
    setFailedRequest(null);
    try {
      const latest = apiRequest<Execution>("/admin/watchlist/executions/latest").catch(
        (value: unknown) => {
          if (value instanceof ApiRequestError && value.status === 404) return null;
          throw value;
        },
      );
      const [defs, dates, latestExecution] = await Promise.all([
        apiRequest<Definitions>("/screener/definitions"),
        apiRequest<string[]>("/watchlist/history"),
        latest,
      ]);
      setDefinitions(defs);
      setHistoryDates(dates);
      setExecution(latestExecution);
      setDate((current) => current || dates[0] || "");
      if (dates.length === 0) setLoading(false);
    } catch {
      setError("스크리너 정보를 불러오지 못했습니다.");
      setFailedRequest("bootstrap");
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void bootstrap();
    return () => {
      mounted.current = false;
      request.current += 1;
      operation.current += 1;
    };
  }, [bootstrap]);

  useEffect(() => {
    if (date) void loadDate(date);
  }, [date, loadDate]);

  useEffect(() => {
    const restore = () => {
      const query = new URLSearchParams(window.location.search);
      setDate(query.get("date") ?? "");
      setSetup(query.get("setup") ?? "");
      setQ(query.get("q") ?? "");
      setMinScore(query.get("minScore") ?? "");
      setMinValue(query.get("minValue") ?? "");
      setWarningFree(query.get("warningFree") === "1");
      setSort((query.get("sort") as Sort) || "rank");
    };
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, []);

  useEffect(() => setQuery("date", date), [date]);
  useEffect(() => setQuery("setup", setup), [setup]);
  useEffect(() => setQuery("q", q), [q]);
  useEffect(() => setQuery("minScore", minScore, "0"), [minScore]);
  useEffect(() => setQuery("minValue", minValue, "0"), [minValue]);
  useEffect(() => setQuery("warningFree", warningFree ? "1" : ""), [warningFree]);
  useEffect(() => setQuery("sort", sort, "rank"), [sort]);

  const execute = async (kind: "normal" | "reanalysis") => {
    if (running) return;
    if (kind === "reanalysis" && (!date || !historyDates.includes(date))) return;
    if (
      kind === "reanalysis" &&
      !window.confirm(`저장된 시장 데이터로 ${date} 결과를 다시 계산합니다.`)
    )
      return;
    const id = ++operation.current;
    setRunning(kind);
    setNotice("");
    setOperationError("");
    try {
      const result = await apiRequest<Execution>("/admin/watchlist/run", {
        method: "POST",
        body: JSON.stringify(
          kind === "reanalysis" ? { trading_date: date, force_reanalysis: true } : {},
        ),
      });
      if (!mounted.current || operation.current !== id) return;
      if (
        kind === "normal" &&
        result.status === "skipped" &&
        result.skipped_reason === "already_completed"
      ) {
        setNotice("이 날짜의 스크리닝은 이미 완료되었습니다.");
        const latestExecution = await apiRequest<Execution>(
          "/admin/watchlist/executions/latest",
        );
        if (!mounted.current || operation.current !== id) return;
        setExecution(latestExecution);
        if (date) await loadDate(date);
        return;
      }
      setExecution(result);
      const dates = await apiRequest<string[]>("/watchlist/history");
      if (!mounted.current || operation.current !== id) return;
      setHistoryDates(dates);
      if (result.trading_date === date) await loadDate(result.trading_date);
      else setDate(result.trading_date);
    } catch (value) {
      if (!mounted.current || operation.current !== id) return;
      const conflict = value instanceof ApiRequestError && value.status === 409;
      setOperationError(
        conflict
          ? kind === "reanalysis"
            ? "다른 분석이 실행 중이거나 이전 성공 이력이 없습니다."
            : "이미 스크리닝이 실행 중입니다."
          : kind === "reanalysis"
            ? "다시 분석에 실패했습니다. 이전 결과는 유지됩니다."
            : "스크리닝 실행에 실패했습니다.",
      );
    } finally {
      if (mounted.current && operation.current === id) setRunning(null);
    }
  };

  const shown = useMemo(
    () =>
      items
        .filter(
          (item) =>
            (!setup || item.matched_setups?.includes(setup)) &&
            (!q || item.symbol.includes(q)) &&
            (!minScore ||
              minScore === "0" ||
              compareDecimalStrings(item.total_score, minScore) >= 0) &&
            (!minValue ||
              minValue === "0" ||
              compareDecimalStrings(item.average_trading_value_20 ?? "0", minValue) >= 0) &&
            (!warningFree || item.warnings.length === 0),
        )
        .sort((a, b) =>
          sort === "rank"
            ? a.rank - b.rank
            : sort === "score"
              ? compareDecimalStrings(b.total_score, a.total_score)
              : sort === "value"
                ? compareDecimalStrings(
                    b.average_trading_value_20 ?? "0",
                    a.average_trading_value_20 ?? "0",
                  )
                : a.symbol.localeCompare(b.symbol),
        ),
    [items, setup, q, minScore, minValue, warningFree, sort],
  );

  const resetFilters = () => {
    setSetup("");
    setQ("");
    setMinScore("");
    setMinValue("");
    setWarningFree(false);
    setSort("rank");
  };
  const labels = definitions?.setup_labels ?? fallbackLabels;
  const hasFunnel = execution?.screened_count != null;

  return (
    <main className="shell screener-shell">
      <nav>
        <Link href="/dashboard">대시보드</Link> · <Link href="/watchlist">관심 종목</Link> ·{" "}
        <Link href="/analysis">종목 분석</Link> · <strong>스크리너</strong>
      </nav>
      <h1>멀티 셋업 스윙 스크리너</h1>
      <p>
        {definitions
          ? `${definitions.screener_name} v${definitions.version}`
          : "정의 로딩 중"}
      </p>
      <section className="panel" aria-label="실행 정보">
        <p>선택 결과일: {date || "—"}</p>
        <p>
          {execution ? (
            <>
              최근 실행일: {execution.trading_date} / 상태: {execution.status}
            </>
          ) : (
            "실행 이력 없음"
          )}
        </p>
        <p>
          시작: {execution?.started_at ?? "—"} / 종료: {execution?.finished_at ?? "—"}
        </p>
        {hasFunnel ? (
          <p>
            분석: {execution?.screened_count ?? "—"} / 셋업 통과:{" "}
            {execution?.candidate_count ?? "—"} /{" "}
            {displayDecimal(execution?.score_threshold)}점 이상:{" "}
            {execution?.qualified_count ?? "—"} / 최종: {execution?.persisted_count ?? "—"}
          </p>
        ) : (
          <p>
            후보: {execution?.candidate_count ?? "—"} / 저장:{" "}
            {execution?.persisted_count ?? "—"}
          </p>
        )}
        <div className="action-row">
          <button onClick={() => void execute("normal")} disabled={running !== null}>
            {running === "normal" ? "실행 중…" : "오늘 스크리닝"}
          </button>
          <button
            onClick={() => void execute("reanalysis")}
            disabled={running !== null || !date || !historyDates.includes(date)}
          >
            {running === "reanalysis" ? "다시 분석 중…" : "선택 날짜 다시 분석"}
          </button>
        </div>
      </section>
      {notice && <p role="status">{notice}</p>}
      {operationError && <div role="alert">{operationError}</div>}
      <p>기술적 조건은 미래 수익을 보장하지 않으며 투자 자문이 아닙니다.</p>

      <section className="filters panel" aria-label="필터">
        <label>
          날짜
          <select value={date} onChange={(event) => setDate(event.target.value)}>
            {historyDates.map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          셋업
          <select value={setup} onChange={(event) => setSetup(event.target.value)}>
            <option value="">전체</option>
            {Object.entries(labels).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          최소 점수
          <input value={minScore} onChange={(event) => setMinScore(event.target.value)} />
        </label>
        <label>
          최소 거래대금
          <input value={minValue} onChange={(event) => setMinValue(event.target.value)} />
        </label>
        <label>
          종목
          <input value={q} onChange={(event) => setQ(event.target.value)} />
        </label>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={warningFree}
            onChange={(event) => setWarningFree(event.target.checked)}
          />{" "}
          경고 없음
        </label>
        <label>
          정렬
          <select value={sort} onChange={(event) => setSort(event.target.value as Sort)}>
            <option value="rank">순위</option>
            <option value="score">점수</option>
            <option value="value">거래대금</option>
            <option value="symbol">종목</option>
          </select>
        </label>
      </section>

      {loading ? (
        <p>불러오는 중…</p>
      ) : error ? (
        <div role="alert">
          <p>{error}</p>
          <button
            onClick={() =>
              void (failedRequest === "date" && date ? loadDate(date) : bootstrap())
            }
          >
            다시 시도
          </button>
        </div>
      ) : items.length === 0 ? (
        <EmptyResults summary={selectedResult} />
      ) : shown.length === 0 ? (
        <section className="state-card">
          <h2>현재 필터에 맞는 종목이 없습니다</h2>
          <p className="muted">저장된 후보 {items.length}개는 유지되어 있습니다.</p>
          <button onClick={resetFilters}>필터 초기화</button>
        </section>
      ) : (
        <div className="screener-results">
          {shown.map((item) => (
            <article className="panel" key={item.symbol}>
              <h2>
                <Link href={`/watchlist/${date}/${item.symbol}`}>{item.symbol}</Link>
              </h2>
              <p>
                {item.rank}위 · {displayDecimal(item.total_score)}점 ·{" "}
                {item.primary_setup ? labels[item.primary_setup] : "기존 결과"}
              </p>
              <p>
                평균 거래대금: {item.average_trading_value_20 ?? "—"} / ATR:{" "}
                {formatPercent(item.atr_pct)}
              </p>
              <p>
                <Link href={`/analysis?symbol=${encodeURIComponent(item.symbol)}`}>
                  이 종목 실시간 분석
                </Link>
              </p>
              {item.primary_setup === "box_breakout" && (
                <p>돌파 거래량 배수: {item.volume_ratio ?? "—"}</p>
              )}
              {item.primary_setup === "trend_pullback" && (
                <p>직전 단기 거래량 비율: {item.prior_short_volume_ratio ?? "—"}</p>
              )}
              {item.primary_setup === "volatility_contraction_breakout" && (
                <>
                  <p>돌파 거래량 배수: {item.breakout_volume_ratio ?? "—"}</p>
                  <p>직전 단기 거래량 비율: {item.prior_short_volume_ratio ?? "—"}</p>
                </>
              )}
            </article>
          ))}
        </div>
      )}
    </main>
  );
}
