from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from screener.modules.market.domain import (
    DailyBar,
    InstrumentSnapshot,
    MinuteBar,
    QuoteSnapshot,
)
from screener.modules.market.technical_analysis import (
    aggregate_minute_bars,
    analyze_realtime,
)

KST = ZoneInfo("Asia/Seoul")


def minute_bars(count: int = 120) -> list[MinuteBar]:
    start = datetime(2026, 7, 31, 9, 0, tzinfo=KST)
    result = []
    for index in range(count):
        open_price = Decimal("10000") + Decimal(index)
        result.append(
            MinuteBar(
                symbol="005930",
                timestamp=start + timedelta(minutes=index),
                open=open_price,
                high=open_price + 20,
                low=open_price - 10,
                close=open_price + 10,
                volume=100 + index,
                currency="KRW",
                source="test",
                as_of=start + timedelta(minutes=index),
            )
        )
    return result


def daily_bars(count: int = 80) -> list[DailyBar]:
    start = date(2026, 4, 1)
    result = []
    for index in range(count):
        close = Decimal("9000") + Decimal(index * 15)
        result.append(
            DailyBar(
                symbol="005930",
                trading_date=start + timedelta(days=index),
                open=close - 10,
                high=close + 30,
                low=close - 30,
                close=close,
                volume=200_000,
                source="test",
                as_of=datetime(2026, 4, 1, tzinfo=UTC) + timedelta(days=index),
            )
        )
    return result


def instrument() -> InstrumentSnapshot:
    return InstrumentSnapshot(
        symbol="005930",
        name="삼성전자",
        market="KOSPI",
        currency="KRW",
        security_type="common_stock",
        listing_status="listed",
        source="test",
        as_of=datetime(2026, 7, 31, tzinfo=UTC),
    )


def quote() -> QuoteSnapshot:
    return QuoteSnapshot(
        symbol="005930",
        price=Decimal("10150"),
        currency="KRW",
        source="test",
        as_of=datetime(2026, 7, 31, 10, 59, tzinfo=KST),
    )


def test_five_minute_aggregation_preserves_ohlcv_and_bucket_boundaries() -> None:
    source = minute_bars(10)

    aggregated = aggregate_minute_bars(source, 5)

    assert len(aggregated) == 2
    assert aggregated[0].timestamp.minute == 0
    assert aggregated[0].open == source[0].open
    assert aggregated[0].close == source[4].close
    assert aggregated[0].high == max(bar.high for bar in source[:5])
    assert aggregated[0].volume == sum(bar.volume for bar in source[:5])


def test_realtime_analysis_combines_daily_and_all_intraday_timeframes() -> None:
    result = analyze_realtime(instrument(), quote(), daily_bars(), minute_bars(), [])

    assert len(result.intraday_bars["1m"]) == 120
    assert len(result.intraday_bars["5m"]) == 24
    assert len(result.intraday_bars["10m"]) == 12
    assert result.intraday["5m"].trend == "bullish"
    assert result.intraday["5m"].vwap is not None
    assert result.daily.sma20 is not None
    assert result.daily.screening_trading_date == daily_bars()[-1].trading_date
    assert result.daily.score_threshold == Decimal("80")
    assert result.levels.supports
    assert result.verdict
    assert "웹소켓" in result.notes[0]
    assert result.as_of == quote().as_of


def test_realtime_analysis_does_not_invent_score_for_incomplete_setup() -> None:
    flat = daily_bars()
    flat = [
        bar.model_copy(
            update={
                "open": Decimal("10000"),
                "high": Decimal("10100"),
                "low": Decimal("9900"),
                "close": Decimal("10000"),
            }
        )
        for bar in flat
    ]

    result = analyze_realtime(instrument(), quote(), flat, minute_bars(), [])

    assert result.daily.screening_passed is False
    assert result.daily.total_score is None
    assert result.daily.meets_score_threshold is False
