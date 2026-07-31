import type { DailyBar, MinuteBar } from "../types";

type Candle = {
  time: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: number;
};

const money = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 2 });

function compactTime(value: string, daily: boolean): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    month: "numeric",
    day: "numeric",
    ...(daily ? {} : { hour: "2-digit", minute: "2-digit", hour12: false }),
  }).format(date);
}

function normalize(
  candles: DailyBar[] | MinuteBar[],
  daily: boolean,
): Candle[] {
  return candles.map((candle) => ({
    time: daily ? `${(candle as DailyBar).trading_date}T00:00:00+09:00` : (candle as MinuteBar).timestamp,
    open: candle.open,
    high: candle.high,
    low: candle.low,
    close: candle.close,
    volume: candle.volume,
  }));
}

export function CandlestickChart({
  candles,
  daily,
  title,
}: {
  candles: DailyBar[] | MinuteBar[];
  daily: boolean;
  title: string;
}) {
  const source = normalize(candles, daily).slice(daily ? -80 : -60);
  const parsed = source.map((candle) => ({
    ...candle,
    o: Number(candle.open),
    h: Number(candle.high),
    l: Number(candle.low),
    c: Number(candle.close),
  }));
  if (
    parsed.length < 2 ||
    parsed.some(
      (candle) =>
        ![candle.o, candle.h, candle.l, candle.c, candle.volume].every(Number.isFinite),
    )
  ) {
    return (
      <section className="chart-empty" role="status">
        차트를 안전하게 표시할 데이터가 부족합니다.
      </section>
    );
  }

  const width = 720;
  const height = 340;
  const left = 58;
  const right = 16;
  const top = 18;
  const priceHeight = 235;
  const volumeTop = 275;
  const volumeHeight = 45;
  const plotWidth = width - left - right;
  const low = Math.min(...parsed.map((candle) => candle.l));
  const high = Math.max(...parsed.map((candle) => candle.h));
  const range = Math.max(high - low, Math.abs(high) * 0.001, 1);
  const maxVolume = Math.max(...parsed.map((candle) => candle.volume), 1);
  const step = plotWidth / parsed.length;
  const candleWidth = Math.max(2, Math.min(step * 0.62, 8));
  const y = (price: number) => top + ((high - price) / range) * priceHeight;
  const labelIndexes = Array.from(
    new Set([0, Math.floor((parsed.length - 1) / 2), parsed.length - 1]),
  );
  const description = parsed
    .slice(-5)
    .map(
      (candle) =>
        `${compactTime(candle.time, daily)} 시가 ${candle.open}, 고가 ${candle.high}, 저가 ${candle.low}, 종가 ${candle.close}`,
    )
    .join("; ");

  return (
    <figure className="candle-chart" aria-label={title}>
      <figcaption>
        <strong>{title}</strong>
        <span>
          <i className="legend-up" /> 상승·보합 <i className="legend-down" /> 하락
        </span>
      </figcaption>
      <svg role="img" aria-label={title} viewBox={`0 0 ${width} ${height}`}>
        <title>{title}</title>
        <desc>{description}</desc>
        {[0, 1, 2, 3, 4].map((index) => {
          const price = high - (range * index) / 4;
          const gridY = top + (priceHeight * index) / 4;
          return (
            <g key={index}>
              <line
                x1={left}
                x2={width - right}
                y1={gridY}
                y2={gridY}
                className="chart-grid"
              />
              <text x={left - 6} y={gridY + 4} textAnchor="end" className="chart-label">
                {money.format(price)}
              </text>
            </g>
          );
        })}
        {parsed.map((candle, index) => {
          const center = left + step * index + step / 2;
          const rising = candle.c >= candle.o;
          const bodyTop = Math.min(y(candle.o), y(candle.c));
          const bodyHeight = Math.max(1.8, Math.abs(y(candle.o) - y(candle.c)));
          const volume = (candle.volume / maxVolume) * volumeHeight;
          return (
            <g key={`${candle.time}-${index}`} className={rising ? "candle-up" : "candle-down"}>
              <line x1={center} x2={center} y1={y(candle.h)} y2={y(candle.l)} />
              <rect
                x={center - candleWidth / 2}
                y={bodyTop}
                width={candleWidth}
                height={bodyHeight}
                rx="0.6"
              />
              <rect
                className="volume-bar"
                x={center - candleWidth / 2}
                y={volumeTop + volumeHeight - volume}
                width={candleWidth}
                height={Math.max(volume, 1)}
              />
            </g>
          );
        })}
        <line
          x1={left}
          x2={width - right}
          y1={volumeTop + volumeHeight}
          y2={volumeTop + volumeHeight}
          className="chart-axis"
        />
        {labelIndexes.map((index) => {
          const center = left + step * index + step / 2;
          return (
            <text
              key={index}
              x={center}
              y={height - 5}
              textAnchor={index === 0 ? "start" : index === parsed.length - 1 ? "end" : "middle"}
              className="chart-label"
            >
              {compactTime(parsed[index].time, daily)}
            </text>
          );
        })}
      </svg>
    </figure>
  );
}
