import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { InstrumentAnalysis } from "@/features/analysis/components/instrument-analysis";

const minute = (timestamp: string, price: string) => ({
  symbol: "005930",
  timestamp,
  open: price,
  high: String(Number(price) + 100),
  low: String(Number(price) - 100),
  close: String(Number(price) + 50),
  volume: 1000,
  currency: "KRW",
  source: "toss",
  as_of: timestamp,
});

const daily = (trading_date: string, price: string) => ({
  symbol: "005930",
  trading_date,
  open: price,
  high: String(Number(price) + 100),
  low: String(Number(price) - 100),
  close: String(Number(price) + 50),
  volume: 1000,
  source: "toss",
  as_of: `${trading_date}T09:00:00+09:00`,
});

const intradaySummary = (timeframe: "1m" | "5m" | "10m") => ({
  timeframe,
  trend: "bullish",
  candle_count: 2,
  session_open: "70000",
  session_high: "72500",
  session_low: "69800",
  change_from_open_pct: "0.0286",
  sma5: "71800",
  sma20: "71000",
  vwap: "71200",
  momentum_5_pct: "0.01",
  latest_volume_ratio: "1.5",
  recent_high_20: "72500",
  recent_low_20: "69800",
});

const analysis = {
  instrument: {
    symbol: "005930",
    name: "삼성전자",
    market: "KOSPI",
    currency: "KRW",
    source: "toss",
    as_of: "2026-07-31T05:00:00Z",
  },
  quote: {
    symbol: "005930",
    price: "72000",
    currency: "KRW",
    source: "toss",
    as_of: "2026-07-31T14:00:00+09:00",
    delayed: false,
  },
  as_of: "2026-07-31T14:00:00+09:00",
  timezone: "Asia/Seoul",
  refresh_after_seconds: 60,
  daily_bars: [daily("2026-07-30", "70000"), daily("2026-07-31", "71000")],
  intraday_bars: {
    "1m": [
      minute("2026-07-31T13:58:00+09:00", "71000"),
      minute("2026-07-31T13:59:00+09:00", "71900"),
    ],
    "5m": [
      minute("2026-07-31T13:50:00+09:00", "71000"),
      minute("2026-07-31T13:55:00+09:00", "71900"),
    ],
    "10m": [
      minute("2026-07-31T13:40:00+09:00", "70500"),
      minute("2026-07-31T13:50:00+09:00", "71900"),
    ],
  },
  daily: {
    screening_trading_date: "2026-07-31",
    trend: "bullish",
    previous_close: "70000",
    change_pct: "0.0286",
    sma20: "71000",
    sma60: "69000",
    ema20: "71100",
    atr_pct: "0.03",
    recent_high_20: "72500",
    recent_low_20: "68000",
    screening_passed: true,
    matched_setups: ["box_breakout"],
    primary_setup: "box_breakout",
    total_score: "88.50",
    score_threshold: "80",
    meets_score_threshold: true,
    common_failures: [],
    setup_progress: { box_breakout: { passed_rules: 6, total_rules: 6 } },
  },
  intraday: {
    "1m": intradaySummary("1m"),
    "5m": intradaySummary("5m"),
    "10m": intradaySummary("10m"),
  },
  levels: {
    supports: [{ price: "71200", basis: ["장중 VWAP"] }],
    resistances: [{ price: "72500", basis: ["당일 고가"] }],
  },
  verdict: "일봉 상승 구조와 장중 흐름이 함께 우세합니다.",
  observations: ["현재가 72,000원, 전일 종가 대비 2.86%입니다."],
  entry_confirmation: "72,500원 위 안착과 5분 거래량 증가를 함께 확인하세요.",
  invalidation: "71,200원 이탈 시 현재 단기 시나리오를 재검토하세요.",
  risk_flags: ["현재 데이터에서 별도의 정량 경고는 감지되지 않았습니다."],
  warnings: [],
  notes: ["실시간 웹소켓이 아닌 최신 데이터입니다."],
};

const json = (body: unknown, status = 200) =>
  Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );

describe("InstrumentAnalysis", () => {
  beforeEach(() => history.replaceState(null, "", "/analysis"));
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("validates a six digit KOSPI symbol before requesting data", async () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    render(<InstrumentAnalysis />);

    fireEvent.change(screen.getByLabelText("KOSPI 종목코드 6자리"), {
      target: { value: "5930" },
    });
    fireEvent.click(screen.getByRole("button", { name: "실시간 분석" }));

    expect(await screen.findByText("KOSPI 종목코드 6자리를 입력해 주세요.")).toBeVisible();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("loads the live analysis, charts, levels and decision conditions", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockReturnValue(json(analysis));
    render(<InstrumentAnalysis />);

    fireEvent.change(screen.getByLabelText("KOSPI 종목코드 6자리"), {
      target: { value: "005930" },
    });
    fireEvent.click(screen.getByRole("button", { name: "실시간 분석" }));

    expect(await screen.findByRole("heading", { name: "삼성전자" })).toBeVisible();
    expect(screen.getByText("72,000원")).toBeVisible();
    expect(screen.getByText(analysis.verdict)).toBeVisible();
    expect(screen.getByText(analysis.entry_confirmation)).toBeVisible();
    expect(screen.getByText(analysis.invalidation)).toBeVisible();
    expect(screen.getByText("장중 VWAP")).toBeVisible();
    expect(screen.getAllByRole("img", { name: "삼성전자 5m 캔들 차트" })).toHaveLength(1);
    expect(location.search).toBe("?symbol=005930");
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/instruments/005930/analysis"),
      expect.any(Object),
    );

    fireEvent.click(screen.getByRole("button", { name: "10분" }));
    expect(screen.getAllByRole("img", { name: "삼성전자 10m 캔들 차트" })).toHaveLength(1);
  });

  it("loads a symbol supplied in the URL", async () => {
    history.replaceState(null, "", "/analysis?symbol=005930");
    const fetch = vi.spyOn(globalThis, "fetch").mockReturnValue(json(analysis));

    render(<InstrumentAnalysis />);

    expect(await screen.findByRole("heading", { name: "삼성전자" })).toBeVisible();
    expect(screen.getByLabelText("KOSPI 종목코드 6자리")).toHaveValue("005930");
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("keeps the previous result visible when a manual refresh fails", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockReturnValueOnce(json(analysis))
      .mockReturnValueOnce(json({}, 503));
    render(<InstrumentAnalysis />);
    fireEvent.change(screen.getByLabelText("KOSPI 종목코드 6자리"), {
      target: { value: "005930" },
    });
    fireEvent.click(screen.getByRole("button", { name: "실시간 분석" }));
    await screen.findByRole("heading", { name: "삼성전자" });

    fireEvent.click(screen.getByRole("button", { name: "지금 새로고침" }));

    expect(await screen.findByText("시세 공급자가 일시적으로 응답하지 않습니다.")).toBeVisible();
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "삼성전자" })).toBeVisible(),
    );
  });
});
