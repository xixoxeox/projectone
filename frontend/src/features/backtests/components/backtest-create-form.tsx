import { FormEvent, useState } from "react";
import { BacktestApiError, createBacktest } from "../api";
import type { BacktestFormValues, BacktestRun } from "../types";

const today = new Date().toISOString().slice(0, 10);
export const DEFAULT_FORM_VALUES: BacktestFormValues = {
  execution_mode: "independent",
  start_date: `${today.slice(0, 4)}-01-01`,
  end_date: today,
  position_size: "500000",
  stop_loss_pct: "0.05",
  take_profit_pct: "0.10",
  max_holding_days: "10",
  commission_rate: "0.00015",
  sell_tax_rate: "0.0015",
  slippage_rate: "0.001",
  initial_capital: "5000000",
  max_open_positions: "5",
  position_size_pct: "0.1",
  minimum_cash_buffer_pct: "0.05",
};
const FIELD_LABELS: Record<keyof BacktestFormValues, string> = {
  execution_mode: "실행 모드",
  start_date: "시작일",
  end_date: "종료일",
  position_size: "포지션 크기",
  stop_loss_pct: "손절 비율",
  take_profit_pct: "익절 비율",
  max_holding_days: "최대 보유일",
  commission_rate: "수수료율",
  sell_tax_rate: "매도세율",
  slippage_rate: "슬리피지율",
  initial_capital: "초기 자본",
  max_open_positions: "최대 동시 보유 수",
  position_size_pct: "포지션 크기 비율",
  minimum_cash_buffer_pct: "최소 현금 버퍼 비율",
};

function validate(values: BacktestFormValues): string[] {
  const errors: string[] = [];
  if (values.start_date > values.end_date)
    errors.push("시작일은 종료일보다 늦을 수 없습니다.");
  if (values.execution_mode === "independent" && Number(values.position_size) <= 0)
    errors.push("포지션 크기는 0보다 커야 합니다.");
  const rates: Array<keyof BacktestFormValues> = [
    "stop_loss_pct",
    "take_profit_pct",
    "commission_rate",
    "sell_tax_rate",
    "slippage_rate",
  ];
  if (rates.some((key) => Number(values[key]) < 0))
    errors.push("비율과 요율은 음수일 수 없습니다.");
  if (
    !/^\d+$/.test(values.max_holding_days) ||
    Number(values.max_holding_days) < 1
  ) {
    errors.push("최대 보유일은 양의 정수여야 합니다.");
  }
  if (values.execution_mode === "portfolio") {
    if (Number(values.initial_capital) <= 0) errors.push("초기 자본은 0보다 커야 합니다.");
    if (!/^\d+$/.test(values.max_open_positions) || Number(values.max_open_positions) < 1) errors.push("최대 동시 보유 수는 양의 정수여야 합니다.");
    if (!(Number(values.position_size_pct) > 0 && Number(values.position_size_pct) <= 1)) errors.push("포지션 크기 비율은 0보다 크고 1 이하여야 합니다.");
    if (!(Number(values.minimum_cash_buffer_pct) >= 0 && Number(values.minimum_cash_buffer_pct) < 1)) errors.push("현금 버퍼 비율은 0 이상 1 미만이어야 합니다.");
  }
  return errors;
}

export function BacktestCreateForm({
  onCreated,
}: {
  onCreated: (run: BacktestRun) => Promise<void>;
}) {
  const [values, setValues] = useState(DEFAULT_FORM_VALUES);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (submitting) return;
    setSuccess("");
    const errors = validate(values);
    if (errors.length) {
      setError(errors.join(" "));
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const run = await createBacktest(values);
      await onCreated(run);
      setSuccess("백테스트 실행을 생성했습니다.");
    } catch (caught) {
      setError(
        caught instanceof BacktestApiError
          ? caught.message
          : "백테스트를 생성하지 못했습니다.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="panel">
      <h2>새 실행</h2>
      {error && (
        <p className="error" role="alert">
          <strong>입력을 확인하세요:</strong> {error}
        </p>
      )}
      {success && (
        <p className="success" role="status">
          {success}
        </p>
      )}
      <form onSubmit={submit} className="run-form">
        <label>실행 모드<select value={values.execution_mode} onChange={event=>setValues({...values,execution_mode:event.target.value as BacktestFormValues["execution_mode"]})}><option value="independent">독립 거래</option><option value="portfolio">포트폴리오</option></select></label>
        <p className="muted">{values.execution_mode === "independent" ? "각 거래를 독립된 고정금액 거래로 계산합니다." : "하나의 현금 잔고와 동시 보유 한도를 공유합니다."}</p>
        {(Object.keys(values) as Array<keyof BacktestFormValues>).filter(key => key !== "execution_mode" && (values.execution_mode === "portfolio" ? key !== "position_size" : !["initial_capital","max_open_positions","position_size_pct","minimum_cash_buffer_pct"].includes(key))).map((key) => (
          <label key={key}>
            {FIELD_LABELS[key]}
            <input
              type={key.includes("date") ? "date" : "number"}
              step={key === "max_holding_days" ? "1" : "any"}
              value={values[key]}
              onChange={(event) =>
                setValues({ ...values, [key]: event.target.value })
              }
            />
          </label>
        ))}
        <button disabled={submitting}>
          {submitting ? "생성 중…" : "watchlist_entry v1 실행"}
        </button>
      </form>
    </section>
  );
}
