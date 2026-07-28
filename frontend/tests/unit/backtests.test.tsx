import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BacktestApiError, listBacktestTrades } from "@/features/backtests/api";
import { BacktestComparison } from "@/features/backtests/components/backtest-comparison";
import {
  BacktestTradesTable,
  TRADE_PAGE_LIMIT,
} from "@/features/backtests/components/backtest-trades-table";
import { BacktestsDashboard } from "@/features/backtests/components/backtests-dashboard";
import { displayDecimal, money, percent } from "@/features/backtests/format";
import type {
  BacktestRun,
  BacktestStatus,
  BacktestTrade,
} from "@/features/backtests/types";
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
const json = (body: unknown, status = 200) =>
  Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
const result = {
  total_signals: 3,
  entered_trades: 2,
  skipped_signals: 1,
  winning_trades: 1,
  losing_trades: 1,
  win_rate: "0.50000000",
  gross_profit: "12345678901234567890.12345678",
  gross_loss: "-2.00000000",
  net_profit: "10.00000000",
  total_return: "0.00000200",
  average_trade_return: "0.1234567890123456789",
  average_holding_days: "2.00000000",
  profit_factor: null,
  max_drawdown: "0.01000000",
  max_consecutive_wins: 1,
  max_consecutive_losses: 1,
};
function run(
  id: string,
  status: BacktestStatus = "completed",
  created = `2026-07-0${id}T00:00:00Z`,
): BacktestRun {
  return {
    id,
    strategy_name: "watchlist_entry",
    strategy_version: "1",
    parameters: { position_size: "500000.00000000", max_holding_days: 10 },
    start_date: "2026-01-01",
    end_date: "2026-06-01",
    data_as_of: "2026-06-02T00:00:00Z",
    status,
    created_at: created,
    started_at: "2026-07-01T01:00:00Z",
    completed_at: status === "completed" ? "2026-07-01T02:00:00Z" : null,
    result: status === "completed" ? result : null,
    failure_code: status === "failed" ? "DATA_ERROR" : null,
    failure_message: status === "failed" ? "No market data" : null,
  };
}
function trade(index: number, pnl = "1.00000000"): BacktestTrade {
  return {
    id: `trade-${index}`,
    run_id: "1",
    symbol: index % 2 ? "005930" : "000660",
    signal_date: "2026-01-01",
    entry_date: "2026-01-02",
    entry_price: "100.12345678",
    quantity: 3,
    exit_date: "2026-01-03",
    exit_price: "101.12345678",
    exit_reason: "take_profit",
    gross_pnl: "3.00000000",
    commission: "0.10000000",
    tax: "0.20000000",
    slippage_cost: "0.30000000",
    net_pnl: pnl,
    holding_days: 1,
    created_at: "2026-01-03T00:00:00Z",
  };
}
const urls = (mock: {
  mock: { calls: Array<[RequestInfo | URL, RequestInit?]> };
}) => mock.mock.calls.map(([url]) => String(url));
beforeEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
afterEach(cleanup);

describe("run creation", () => {
  it("posts the exact typed payload, refreshes, selects, and displays success", async () => {
    const created = run("9", "pending");
    let listCalls = 0;
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation((url, init) => {
        if (init?.method === "POST") return json(created, 201);
        if (String(url).endsWith("/backtests"))
          return json(listCalls++ ? [created] : []);
        if (String(url).includes("/trades?")) return json([]);
        return json(created);
      });
    render(<BacktestsDashboard />);
    await screen.findByText("저장된 백테스트 실행이 없습니다.");
    fireEvent.change(screen.getByLabelText("포지션 크기"), {
      target: { value: "500000.12345678" },
    });
    fireEvent.click(screen.getByRole("button", { name: /watchlist_entry/ }));
    expect(
      await screen.findByText("백테스트 실행을 생성했습니다."),
    ).toBeVisible();
    const post = fetch.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(String(post[0])).toBe("/api/v1/backtests");
    expect(JSON.parse(String(post[1]?.body))).toEqual({
      strategy_name: "watchlist_entry",
      strategy_version: "1",
      start_date: expect.any(String),
      end_date: expect.any(String),
      parameters: {
        position_size: "500000.12345678",
        stop_loss_pct: "0.05",
        take_profit_pct: "0.10",
        max_holding_days: 10,
        commission_rate: "0.00015",
        sell_tax_rate: "0.0015",
        slippage_rate: "0.001",
      },
    });
    expect(listCalls).toBe(2);
    expect(await screen.findByText("실행 상세")).toBeVisible();
    expect(screen.getAllByText("9").length).toBeGreaterThan(0);
  });
  it("disables submit and prevents duplicate posts while pending", async () => {
    let resolve!: (value: Response) => void;
    const pending = new Promise<Response>((done) => {
      resolve = done;
    });
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation((url, init) =>
        init?.method === "POST" ? pending : json([]),
      );
    render(<BacktestsDashboard />);
    await screen.findByText("저장된 백테스트 실행이 없습니다.");
    const button = screen.getByRole("button", { name: /watchlist_entry/ });
    fireEvent.click(button);
    expect(
      await screen.findByRole("button", { name: "생성 중…" }),
    ).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "생성 중…" }));
    expect(
      fetch.mock.calls.filter(([, init]) => init?.method === "POST"),
    ).toHaveLength(1);
    resolve(new Response(JSON.stringify(run("4")), { status: 201 }));
  });
  it.each([
    [422, { detail: "position_size is invalid" }, "position_size is invalid"],
    [
      422,
      { detail: [{ loc: ["body", "start_date"], msg: "invalid date" }] },
      "start_date: invalid date",
    ],
  ])("shows backend validation details", async (status, body, expected) => {
    vi.spyOn(globalThis, "fetch").mockImplementation((url, init) =>
      init?.method === "POST" ? json(body, status) : json([]),
    );
    render(<BacktestsDashboard />);
    await screen.findByText("저장된 백테스트 실행이 없습니다.");
    fireEvent.click(screen.getByRole("button", { name: /watchlist_entry/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(expected);
  });
  it("shows network failure", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((url, init) =>
      init?.method === "POST" ? Promise.reject(new Error("offline")) : json([]),
    );
    render(<BacktestsDashboard />);
    await screen.findByText("저장된 백테스트 실행이 없습니다.");
    fireEvent.click(screen.getByRole("button", { name: /watchlist_entry/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "백테스트 요청을 처리하지 못했습니다.",
    );
  });
});

describe("run list and details", () => {
  it("loads, sorts newest first, renders all statuses and placeholders", async () => {
    const runs = [
      run("1", "pending"),
      run("4", "failed"),
      run("2", "running"),
      run("3"),
    ];
    vi.spyOn(globalThis, "fetch").mockReturnValue(json(runs));
    render(<BacktestsDashboard />);
    expect(screen.getByRole("status")).toHaveTextContent("실행 목록");
    const table = await screen.findByRole("table", {
      name: "저장된 백테스트 실행",
    });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(
      rows.map((row) => within(row).getByRole("button").textContent),
    ).toHaveLength(4);
    expect(rows[0]).toHaveTextContent("failed");
    for (const status of ["pending", "running", "completed", "failed"])
      expect(within(table).getByText(status)).toBeVisible();
    expect(within(rows[1]).getAllByText("—").length).toBeGreaterThan(0);
  });
  it("renders empty and retries errors", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockReturnValueOnce(json({}, 500))
      .mockReturnValue(json([]));
    render(<BacktestsDashboard />);
    fireEvent.click(await screen.findByRole("button", { name: "다시 시도" }));
    expect(
      await screen.findByText("저장된 백테스트 실행이 없습니다."),
    ).toBeVisible();
    expect(fetch).toHaveBeenCalledTimes(2);
  });
  it("GETs selected run and renders persisted metadata, metrics, and failure details", async () => {
    const complete = run("1"),
      failed = run("2", "failed");
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation((url) =>
        String(url).includes("/trades?")
          ? json([])
          : String(url).endsWith("/backtests/1")
            ? json(complete)
            : String(url).endsWith("/backtests/2")
              ? json(failed)
              : json([complete, failed]),
      );
    render(<BacktestsDashboard />);
    const buttons = await screen.findAllByRole("button", { name: /2026/ });
    fireEvent.click(buttons[1]);
    expect(
      await screen.findByText("12345678901234567890.12345678 원"),
    ).toBeVisible();
    expect(urls(fetch)).toContain("/api/v1/backtests/1");
    expect(screen.getAllByText("2026-01-01 – 2026-06-01").length).toBeGreaterThan(0);
    fireEvent.click(buttons[0]);
    expect(await screen.findByText("No market data")).toBeVisible();
    expect(screen.getAllByText("DATA_ERROR").length).toBeGreaterThan(0);
  });
});

describe("trades", () => {
  it("renders every field and textual profit/loss indicators", async () => {
    vi.spyOn(globalThis, "fetch").mockReturnValue(
      json([trade(1), trade(2, "-1.25000000")]),
    );
    render(<BacktestTradesTable runId="1" />);
    const table = await screen.findByRole("table", {
      name: "선택한 실행의 거래 내역",
    });
    for (const text of [
      "005930",
      "2026-01-01",
      "100.12345678 원",
      "3",
      "take_profit",
      "0.1 원",
      "0.2 원",
      "0.3 원",
      "수익: 1 원",
      "손실: -1.25 원",
    ])
      expect(within(table).getAllByText(text).length).toBeGreaterThan(0);
  });
  it("paginates next and previous with preserved filters", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockReturnValue(
        json(Array.from({ length: TRADE_PAGE_LIMIT }, (_, i) => trade(i))),
      );
    render(<BacktestTradesTable runId="1" />);
    await screen.findByRole("table");
    fireEvent.change(screen.getByLabelText("종목"), {
      target: { value: "005930" },
    });
    fireEvent.change(screen.getByLabelText("청산 사유"), {
      target: { value: "take_profit" },
    });
    await waitFor(() =>
      expect(urls(fetch).at(-1)).toContain(
        "offset=0&symbol=005930&exit_reason=take_profit",
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: "다음" }));
    await waitFor(() =>
      expect(urls(fetch).at(-1)).toContain(
        "offset=25&symbol=005930&exit_reason=take_profit",
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: "이전" }));
    await waitFor(() =>
      expect(urls(fetch).at(-1)).toContain(
        "offset=0&symbol=005930&exit_reason=take_profit",
      ),
    );
  });
  it("resets filters and pagination for another run and disables next for a short page", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockReturnValue(json([trade(1)]));
    const view = render(<BacktestTradesTable runId="1" />);
    await screen.findByRole("table");
    expect(screen.getByRole("button", { name: "다음" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("종목"), {
      target: { value: "005930" },
    });
    view.rerender(<BacktestTradesTable runId="2" />);
    await waitFor(() => expect(screen.getByLabelText("종목")).toHaveValue(""));
    expect(urls(fetch).at(-1)).toContain(
      "/backtests/2/trades?limit=25&offset=0",
    );
  });
  it("renders loading, empty, failure, and retry", async () => {
    let resolve!: (value: Response) => void;
    const pending = new Promise<Response>((done) => {
      resolve = done;
    });
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockReturnValueOnce(pending)
      .mockReturnValueOnce(json({}, 500))
      .mockReturnValue(json([]));
    render(<BacktestTradesTable runId="1" />);
    expect(screen.getByRole("status")).toHaveTextContent("거래 내역");
    resolve(new Response(JSON.stringify([])));
    expect(
      await screen.findByText("조건에 맞는 거래가 없습니다."),
    ).toBeVisible();
    fireEvent.change(screen.getByLabelText("종목"), { target: { value: "x" } });
    fireEvent.click(await screen.findByRole("button", { name: "다시 시도" }));
    expect(
      await screen.findByText("조건에 맞는 거래가 없습니다."),
    ).toBeVisible();
    expect(fetch).toHaveBeenCalledTimes(3);
  });
});

describe("comparison", () => {
  it("allows only completed runs, compares exactly two, and replaces the first with a third", async () => {
    const runs = [run("1"), run("2"), run("3"), run("4", "failed")];
    vi.spyOn(globalThis, "fetch").mockReturnValue(json(runs));
    render(<BacktestsDashboard />);
    expect(await screen.findByLabelText("4 비교 선택")).toBeDisabled();
    fireEvent.click(screen.getByLabelText("1 비교 선택"));
    fireEvent.click(screen.getByLabelText("2 비교 선택"));
    expect(screen.getAllByText("position_size")).toHaveLength(2);
    fireEvent.click(screen.getByLabelText("3 비교 선택"));
    expect(screen.getByLabelText("1 비교 선택")).not.toBeChecked();
    expect(screen.getByLabelText("2 비교 선택")).toBeChecked();
    expect(screen.getByLabelText("3 비교 선택")).toBeChecked();
  });
  it("shows higher/lower/equal descriptively and placeholders for missing metrics", () => {
    const a = run("1"),
      b = run("2");
    a.result = { ...result, total_signals: 4, entered_trades: 2 };
    b.result = { ...result, total_signals: 3, entered_trades: 2 };
    render(<BacktestComparison runs={[a, b]} />);
    expect(screen.getAllByText(/더 높음; 설명적 비교/).length).toBeGreaterThan(
      0,
    );
    expect(screen.getAllByText(/더 낮음; 설명적 비교/).length).toBeGreaterThan(
      0,
    );
    expect(screen.getAllByText(/같음; 설명적 비교/).length).toBeGreaterThan(0);
    expect(
      screen.getAllByText(/비교 불가; 설명적 비교/).length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.getAllByText("평균 보유일")).toHaveLength(2);
  });
});

describe("API and formatting", () => {
  it("caps trade limits at 500", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockReturnValue(json([]));
    await listBacktestTrades("run", { limit: 999, offset: 0 });
    expect(urls(fetch)[0]).toContain("limit=500");
  });
  it("reports network errors as typed errors", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("offline"));
    await expect(
      listBacktestTrades("run", { limit: 1, offset: 0 }),
    ).rejects.toEqual(
      expect.objectContaining<Partial<BacktestApiError>>({
        status: null,
        message: "백테스트 요청을 처리하지 못했습니다.",
      }),
    );
  });
  it.each([
    [
      money,
      "12345678901234567890.12345678",
      "12345678901234567890.12345678 원",
    ],
    [percent, "0.1234567890123456789", "12.34567890123456789%"],
    [money, "-0.12345678", "-0.12345678 원"],
    [percent, "-0.12345678", "-12.345678%"],
  ] as const)(
    "formats precise and negative decimals",
    (formatter, input, expected) => expect(formatter(input)).toBe(expected),
  );
  it("uses placeholders for null and undefined", () => {
    expect(displayDecimal(null)).toBe("—");
    expect(money(undefined)).toBe("—");
    expect(percent(null)).toBe("—");
  });
});
