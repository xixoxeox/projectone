import { useEffect, useState } from "react";
import { listBacktestTrades } from "../api";
import { money } from "../format";
import type { BacktestTrade } from "../types";
export const TRADE_PAGE_LIMIT = 25;
export function BacktestTradesTable({ runId }: { runId: string }) {
  const [offset, setOffset] = useState(0);
  const [symbol, setSymbol] = useState("");
  const [exitReason, setExitReason] = useState("");
  const [trades, setTrades] = useState<BacktestTrade[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    setOffset(0);
    setSymbol("");
    setExitReason("");
  }, [runId]);
  useEffect(() => {
    setState("loading");
    void listBacktestTrades(runId, {
      limit: TRADE_PAGE_LIMIT,
      offset,
      symbol,
      exit_reason: exitReason,
    })
      .then((result) => {
        setTrades(result);
        setState("ready");
      })
      .catch(() => setState("error"));
  }, [runId, offset, symbol, exitReason, attempt]);
  const filter = (setter: (value: string) => void, value: string) => {
    setter(value);
    setOffset(0);
  };
  return (
    <section>
      <h3>거래 내역</h3>
      <div className="filters">
        <label>
          종목
          <input
            value={symbol}
            onChange={(event) => filter(setSymbol, event.target.value)}
          />
        </label>
        <label>
          청산 사유
          <select
            value={exitReason}
            onChange={(event) => filter(setExitReason, event.target.value)}
          >
            <option value="">전체</option>
            {[
              "stop_loss",
              "take_profit",
              "max_holding_days",
              "end_of_period",
            ].map((reason) => (
              <option key={reason}>{reason}</option>
            ))}
          </select>
        </label>
      </div>
      {state === "loading" && <p role="status">거래 내역을 불러오는 중…</p>}
      {state === "error" && (
        <div role="alert">
          거래 내역을 불러오지 못했습니다.{" "}
          <button onClick={() => setAttempt((value) => value + 1)}>
            다시 시도
          </button>
        </div>
      )}
      {state === "ready" && trades.length === 0 && (
        <p>조건에 맞는 거래가 없습니다.</p>
      )}
      {state === "ready" && trades.length > 0 && (
        <div className="table-scroll">
          <table>
            <caption className="sr-only">선택한 실행의 거래 내역</caption>
            <thead>
              <tr>
                {[
                  "종목",
                  "신호일",
                  "진입일",
                  "진입가",
                  "수량",
                  "청산일",
                  "청산가",
                  "청산 사유",
                  "총손익",
                  "수수료",
                  "세금",
                  "슬리피지",
                  "순손익",
                  "보유일",
                ].map((heading) => (
                  <th key={heading}>{heading}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {trades.map((trade) => (
                <tr key={trade.id}>
                  <td>{trade.symbol}</td>
                  <td>{trade.signal_date}</td>
                  <td>{trade.entry_date}</td>
                  <td>{money(trade.entry_price)}</td>
                  <td>{trade.quantity}</td>
                  <td>{trade.exit_date}</td>
                  <td>{money(trade.exit_price)}</td>
                  <td>{trade.exit_reason}</td>
                  <td>{money(trade.gross_pnl)}</td>
                  <td>{money(trade.commission)}</td>
                  <td>{money(trade.tax)}</td>
                  <td>{money(trade.slippage_cost)}</td>
                  <td>
                    {trade.net_pnl.startsWith("-") ? "손실" : "수익"}:{" "}
                    {money(trade.net_pnl)}
                  </td>
                  <td>{trade.holding_days}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="pager">
        <button
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - TRADE_PAGE_LIMIT))}
        >
          이전
        </button>
        <span>{offset + 1}번째부터</span>
        <button
          disabled={trades.length !== TRADE_PAGE_LIMIT}
          onClick={() => setOffset(offset + TRADE_PAGE_LIMIT)}
        >
          다음
        </button>
      </div>
    </section>
  );
}
