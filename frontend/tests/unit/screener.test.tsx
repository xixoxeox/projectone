import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ScreenerDashboard } from "@/features/watchlist/components/screener-dashboard";
import type { WatchlistItem } from "@/features/watchlist/types";

const push = vi.fn();
let query = "";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(query),
}));
vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...props
  }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={String(href)} {...props}>
      {children}
    </a>
  ),
}));

const definitions = {
  screener_name: "multi_setup_swing",
  screener_version: "1",
  setups: [
    { key: "box_breakout", label: "박스권 돌파", description: "box" },
    { key: "trend_pullback", label: "추세 눌림목", description: "pullback" },
    {
      key: "volatility_contraction_breakout",
      label: "변동성 축소 돌파",
      description: "vcp",
    },
  ],
  defaults: {},
  limitations: [],
};
const execution = {
  trading_date: "2026-07-29",
  status: "succeeded",
  started_at: "start",
  finished_at: "finish",
  candidate_count: 3,
  persisted_count: 3,
};
const items: WatchlistItem[] = [
  {
    rank: 1,
    symbol: "BOX",
    total_score: "80.00000000000000000001",
    component_scores: {},
    warnings: [],
    primary_setup: "box_breakout",
    matched_setups: ["box_breakout"],
    average_trading_value_20: "999999999999999999999.01",
    volume_ratio: "1.25",
    atr_pct: "0.03",
  },
  {
    rank: 2,
    symbol: "PULL",
    total_score: "70",
    component_scores: {},
    warnings: ["주의"],
    primary_setup: "trend_pullback",
    matched_setups: ["trend_pullback"],
    average_trading_value_20: "2000",
    prior_short_volume_ratio: "0.55",
    atr_pct: "0.00125",
  },
  {
    rank: 3,
    symbol: "VCP",
    total_score: "60",
    component_scores: {},
    warnings: [],
    primary_setup: "volatility_contraction_breakout",
    matched_setups: ["volatility_contraction_breakout"],
    average_trading_value_20: "1000",
    prior_short_volume_ratio: "0.4",
    breakout_volume_ratio: "2.5",
    atr_pct: "0.02",
  },
];
const response = (body: unknown, status = 200) =>
  Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
function mockApi(rows: WatchlistItem[] = items) {
  return vi.spyOn(globalThis, "fetch").mockImplementation((url) => {
    const value = String(url);
    if (value.endsWith("/watchlist/history")) return response(["2026-07-28"]);
    if (value.endsWith("/screener/definitions")) return response(definitions);
    if (value.endsWith("/executions/latest")) return response(execution);
    return response(rows);
  });
}

describe("screener dashboard", () => {
  beforeEach(() => {
    cleanup();
    push.mockReset();
    query = "";
    vi.restoreAllMocks();
  });
  it("loads definitions, history and separate latest execution metadata", async () => {
    mockApi();
    render(<ScreenerDashboard />);
    expect(
      await screen.findByText("multi_setup_swing v1 · 기준일 2026-07-28"),
    ).toBeVisible();
    expect(screen.getByLabelText("가장 최근 실행")).toHaveTextContent(
      "2026-07-29",
    );
  });
  it("uses setup-specific volume labels and exact ATR percentages", async () => {
    mockApi();
    render(<ScreenerDashboard />);
    await screen.findByRole("heading", { name: "1. BOX" });
    expect(screen.getAllByText("돌파 거래량 배수")).toHaveLength(2);
    expect(screen.getAllByText("직전 단기 거래량 비율")).toHaveLength(2);
    expect(screen.getByText("2.5")).toBeVisible();
    expect(screen.getByText("3%")).toBeVisible();
    expect(screen.getByText("0.125%")).toBeVisible();
  });
  it("restores filters from the query and filters exact large decimals", async () => {
    query =
      "setup=box_breakout&minScore=80.00000000000000000000&minValue=999999999999999999999.00&q=BOX&warningFree=1&sort=score";
    mockApi();
    render(<ScreenerDashboard />);
    await screen.findByRole("heading", { name: "1. BOX" });
    expect(screen.queryByText("PULL")).not.toBeInTheDocument();
    expect(screen.getByLabelText("설정")).toHaveValue("box_breakout");
    expect(screen.getByLabelText("최소 점수")).toHaveValue(
      "80.00000000000000000000",
    );
    expect(screen.getByLabelText("정렬")).toHaveValue("score");
  });
  it("represents a successful empty date and synchronizes date selection", async () => {
    mockApi([]);
    render(<ScreenerDashboard />);
    expect(
      await screen.findByText(
        "이 날짜 또는 필터 조건에 맞는 저장 후보가 없습니다.",
      ),
    ).toBeVisible();
    fireEvent.change(screen.getByLabelText("날짜"), {
      target: { value: "2026-07-28" },
    });
    expect(push).toHaveBeenCalledWith("/screener?date=2026-07-28");
  });
  it("prevents duplicate run submissions and navigates to the completed date", async () => {
    let resolveRun!: (value: Response) => void;
    const fetch = mockApi();
    fetch.mockImplementation((url) =>
      String(url).endsWith("/admin/watchlist/run")
        ? new Promise((resolve) => {
            resolveRun = resolve;
          })
        : String(url).endsWith("/watchlist/history")
          ? response(["2026-07-28"])
          : String(url).endsWith("/screener/definitions")
            ? response(definitions)
            : String(url).endsWith("/executions/latest")
              ? response(execution)
              : response(items),
    );
    render(<ScreenerDashboard />);
    const button = await screen.findByRole("button", {
      name: "오늘 스크리닝 실행",
    });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(button).toBeDisabled();
    expect(
      fetch.mock.calls.filter(([url]) =>
        String(url).endsWith("/admin/watchlist/run"),
      ),
    ).toHaveLength(1);
    resolveRun(
      new Response(
        JSON.stringify({ ...execution, trading_date: "2026-07-30" }),
        { status: 200 },
      ),
    );
    await waitFor(() =>
      expect(push).toHaveBeenCalledWith("/screener?date=2026-07-30"),
    );
  });
});
