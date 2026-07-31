"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { ApiRequestError } from "@/lib/api";

import { getRealtimeAnalysis } from "../api";
import type {
  ChartView,
  IntradaySummary,
  PriceLevel,
  RealtimeAnalysis,
  Timeframe,
  Trend,
} from "../types";
import { CandlestickChart } from "./candlestick-chart";

const priceFormatter = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 2 });
const setupLabels: Record<string, string> = {
  box_breakout: "박스권 돌파",
  trend_pullback: "추세 눌림목",
  volatility_contraction_breakout: "변동성 축소 돌파",
};
const trendLabels: Record<Trend, string> = {
  bullish: "상승 우위",
  pullback: "상승 추세 내 눌림",
  neutral: "혼조",
  bearish: "하락 우위",
  insufficient: "데이터 부족",
};

function price(value: string | null | undefined): string {
  if (value == null) return "—";
  const number = Number(value);
  return Number.isFinite(number) ? `${priceFormatter.format(number)}원` : value;
}

function decimal(value: string | null | undefined, suffix = ""): string {
  if (value == null) return "—";
  const [whole, fraction = ""] = value.split(".");
  const trimmed = fraction.replace(/0+$/, "");
  return `${trimmed ? `${whole}.${trimmed}` : whole}${suffix}`;
}

function percent(value: string | null | undefined): string {
  if (value == null) return "—";
  const number = Number(value) * 100;
  if (!Number.isFinite(number)) return value;
  const sign = number > 0 ? "+" : "";
  return `${sign}${number.toLocaleString("ko-KR", { maximumFractionDigits: 2 })}%`;
}

function kst(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
}

function errorMessage(value: unknown): string {
  if (!(value instanceof ApiRequestError)) return "실시간 분석을 불러오지 못했습니다.";
  if (value.status === 404) return "해당 종목을 찾을 수 없습니다.";
  if (value.status === 422) return "현재는 상장된 KOSPI 보통주만 분석할 수 있습니다.";
  if (value.status === 503) return "시세 공급자가 일시적으로 응답하지 않습니다.";
  return "실시간 분석을 불러오지 못했습니다.";
}

function Levels({ title, values }: { title: string; values: PriceLevel[] }) {
  return (
    <section>
      <h3>{title}</h3>
      {values.length ? (
        <ol className="level-list">
          {values.map((level) => (
            <li key={`${title}-${level.price}`}>
              <strong>{price(level.price)}</strong>
              <span>{level.basis.join(" · ")}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted">현재가 주변에서 계산 가능한 레벨이 없습니다.</p>
      )}
    </section>
  );
}

function IntradayMetrics({ summary }: { summary: IntradaySummary }) {
  return (
    <dl className="metric-grid">
      <div>
        <dt>단기 추세</dt>
        <dd>{trendLabels[summary.trend]}</dd>
      </div>
      <div>
        <dt>장중 시가 대비</dt>
        <dd>{percent(summary.change_from_open_pct)}</dd>
      </div>
      <div>
        <dt>VWAP</dt>
        <dd>{price(summary.vwap)}</dd>
      </div>
      <div>
        <dt>SMA5 / SMA20</dt>
        <dd>
          {price(summary.sma5)} / {price(summary.sma20)}
        </dd>
      </div>
      <div>
        <dt>최근 5봉 모멘텀</dt>
        <dd>{percent(summary.momentum_5_pct)}</dd>
      </div>
      <div>
        <dt>최근 봉 거래량 배수</dt>
        <dd>{decimal(summary.latest_volume_ratio, "배")}</dd>
      </div>
    </dl>
  );
}

export function InstrumentAnalysis() {
  const [input, setInput] = useState("");
  const [symbol, setSymbol] = useState("");
  const [data, setData] = useState<RealtimeAnalysis | null>(null);
  const [view, setView] = useState<ChartView>("5m");
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [loading, setLoading] = useState(Boolean(symbol));
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const request = useRef(0);

  useEffect(() => {
    const initial = (
      new URLSearchParams(window.location.search).get("symbol") ?? ""
    )
      .trim()
      .toUpperCase();
    setInput(initial);
    if (/^[0-9A-Z]{6}$/.test(initial)) setSymbol(initial);
  }, []);

  const load = useCallback(async (selected: string, silent = false) => {
    const id = ++request.current;
    if (silent) setRefreshing(true);
    else setLoading(true);
    setError("");
    try {
      const result = await getRealtimeAnalysis(selected);
      if (request.current === id) setData(result);
    } catch (value) {
      if (request.current === id) setError(errorMessage(value));
    } finally {
      if (request.current === id) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, []);

  useEffect(() => {
    if (symbol) void load(symbol);
    return () => {
      request.current += 1;
    };
  }, [symbol, load]);

  useEffect(() => {
    if (!symbol || !autoRefresh) return;
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") void load(symbol, true);
    }, Math.max(60, data?.refresh_after_seconds ?? 60) * 1000);
    return () => window.clearInterval(interval);
  }, [autoRefresh, data?.refresh_after_seconds, load, symbol]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const clean = input.trim().toUpperCase();
    if (!/^[0-9A-Z]{6}$/.test(clean)) {
      setError("KOSPI 종목코드 6자리를 입력해 주세요.");
      return;
    }
    setInput(clean);
    const query = new URLSearchParams(window.location.search);
    query.set("symbol", clean);
    history.replaceState(null, "", `${location.pathname}?${query.toString()}`);
    if (clean === symbol) void load(clean);
    else {
      setData(null);
      setSymbol(clean);
    }
  };

  const selectedCandles =
    view === "daily" ? (data?.daily_bars ?? []) : (data?.intraday_bars[view] ?? []);
  const selectedIntraday: IntradaySummary | null =
    view === "daily" || !data ? null : data.intraday[view as Timeframe];

  return (
    <main className="analysis-shell">
      <nav>
        <Link href="/dashboard">대시보드</Link>
        <Link href="/screener">스크리너</Link>
        <Link href="/watchlist">관심 종목</Link>
        <strong>종목 분석</strong>
      </nav>
      <header className="analysis-header">
        <p className="eyebrow">LIVE TECHNICAL VIEW</p>
        <h1>개별 종목 실시간 차트 분석</h1>
        <p className="muted">
          KOSPI 종목의 최신 현재가·일봉·1분봉을 조회해 일봉과 1·5·10분봉 흐름을 함께
          분석합니다.
        </p>
      </header>

      <form className="analysis-search panel" noValidate onSubmit={submit}>
        <label>
          종목코드
          <input
            aria-label="KOSPI 종목코드 6자리"
            autoCapitalize="characters"
            maxLength={6}
            pattern="[0-9A-Za-z]{6}"
            placeholder="예: 005930"
            value={input}
            onChange={(event) => setInput(event.target.value.toUpperCase())}
          />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "분석 중…" : "실시간 분석"}
        </button>
      </form>

      {error && (
        <section className="panel error-state" role="alert">
          <p>{error}</p>
          {symbol && <button onClick={() => void load(symbol)}>다시 시도</button>}
        </section>
      )}
      {!data && !loading && !error && (
        <section className="state-card">
          <h2>궁금한 종목을 바로 확인하세요</h2>
          <p className="muted">종목코드 6자리를 입력하면 최신 차트와 분석을 불러옵니다.</p>
        </section>
      )}
      {loading && !data && (
        <section className="panel" aria-busy="true">
          <h2>시장 데이터를 분석하고 있습니다</h2>
          <p className="muted">현재가, 일봉, 최근 200개 1분봉을 확인하는 중입니다.</p>
        </section>
      )}

      {data && (
        <>
          <section className="analysis-hero panel">
            <div>
              <p>
                {data.instrument.market} · {data.instrument.symbol}
              </p>
              <h2>{data.instrument.name}</h2>
            </div>
            <div className="live-price">
              <strong>{price(data.quote.price)}</strong>
              <span className={(Number(data.daily.change_pct) || 0) >= 0 ? "positive" : "negative"}>
                {percent(data.daily.change_pct)}
              </span>
            </div>
            <p className="as-of">
              데이터 기준 {kst(data.as_of)}
              {data.quote.delayed === true ? " · 지연 시세" : " · 최신 요청 시세"}
            </p>
            <div className="refresh-controls">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={autoRefresh}
                  onChange={(event) => setAutoRefresh(event.target.checked)}
                />{" "}
                60초 자동 갱신
              </label>
              <button
                className="secondary-button"
                onClick={() => void load(data.instrument.symbol, true)}
                disabled={refreshing}
              >
                {refreshing ? "갱신 중…" : "지금 새로고침"}
              </button>
            </div>
          </section>

          <section className="panel verdict-card">
            <p className="eyebrow">현재 판단</p>
            <h2>{data.verdict}</h2>
            <ul>
              {data.observations.map((observation) => (
                <li key={observation}>{observation}</li>
              ))}
            </ul>
          </section>

          <section className="panel chart-panel">
            <div className="timeframe-tabs" role="group" aria-label="차트 봉 선택">
              {(
                [
                  ["daily", "일봉"],
                  ["1m", "1분"],
                  ["5m", "5분"],
                  ["10m", "10분"],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  className={view === key ? "active" : "secondary-button"}
                  aria-pressed={view === key}
                  onClick={() => setView(key)}
                >
                  {label}
                </button>
              ))}
            </div>
            <CandlestickChart
              candles={selectedCandles}
              daily={view === "daily"}
              title={`${data.instrument.name} ${view === "daily" ? "일봉" : view} 캔들 차트`}
            />
            {selectedIntraday ? (
              <IntradayMetrics summary={selectedIntraday} />
            ) : (
              <dl className="metric-grid">
                <div>
                  <dt>일봉 추세</dt>
                  <dd>{trendLabels[data.daily.trend]}</dd>
                </div>
                <div>
                  <dt>SMA20 / SMA60</dt>
                  <dd>
                    {price(data.daily.sma20)} / {price(data.daily.sma60)}
                  </dd>
                </div>
                <div>
                  <dt>ATR</dt>
                  <dd>{percent(data.daily.atr_pct)}</dd>
                </div>
                <div>
                  <dt>직전 20일 고가 / 저가</dt>
                  <dd>
                    {price(data.daily.recent_high_20)} / {price(data.daily.recent_low_20)}
                  </dd>
                </div>
              </dl>
            )}
          </section>

          <section className="decision-grid">
            <article className="panel confirmation-card">
              <h2>확인 조건</h2>
              <p>{data.entry_confirmation}</p>
            </article>
            <article className="panel invalidation-card">
              <h2>무효화 조건</h2>
              <p>{data.invalidation}</p>
            </article>
          </section>

          <section className="panel">
            <h2>
              일봉 스크리너 상태
              {data.daily.screening_trading_date
                ? ` · ${data.daily.screening_trading_date}`
                : ""}
            </h2>
            <dl className="metric-grid">
              <div>
                <dt>셋업 통과</dt>
                <dd>{data.daily.screening_passed ? "통과" : "미통과"}</dd>
              </div>
              <div>
                <dt>대표 셋업</dt>
                <dd>
                  {data.daily.primary_setup
                    ? setupLabels[data.daily.primary_setup]
                    : "완성된 셋업 없음"}
                </dd>
              </div>
              <div>
                <dt>종합점수</dt>
                <dd>{decimal(data.daily.total_score, "점")}</dd>
              </div>
              <div>
                <dt>{decimal(data.daily.score_threshold)}점 기준</dt>
                <dd>{data.daily.meets_score_threshold ? "충족" : "미충족"}</dd>
              </div>
            </dl>
            {!data.daily.screening_passed && (
              <p className="muted">
                일봉 셋업이 완성되지 않은 종목에는 오해를 막기 위해 종합점수를 부여하지
                않습니다.
              </p>
            )}
          </section>

          <section className="panel levels-panel">
            <h2>가격 레벨</h2>
            <p className="muted">5분봉·장중 VWAP·일봉 기준으로 현재가와 가까운 순서입니다.</p>
            <div className="level-grid">
              <Levels title="지지 후보" values={data.levels.supports} />
              <Levels title="저항 후보" values={data.levels.resistances} />
            </div>
          </section>

          <section className="panel risk-panel">
            <h2>주의할 점</h2>
            <ul>
              {data.risk_flags.map((flag) => (
                <li key={flag}>{flag}</li>
              ))}
            </ul>
          </section>

          <details className="panel notes-panel">
            <summary>데이터와 해석 기준</summary>
            <ul>
              {data.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </details>
        </>
      )}
    </main>
  );
}
