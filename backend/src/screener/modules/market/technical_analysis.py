"""Deterministic daily and intraday analysis for one live KOSPI instrument."""

from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from screener.modules.market.domain import (
    DailyBar,
    InstrumentSnapshot,
    MinuteBar,
    QuoteSnapshot,
    StockWarning,
)
from screener.modules.market.indicators.service import IndicatorService
from screener.modules.market.ranking.ranker import SwingCandidateRanker
from screener.modules.market.screening.swing import (
    MultiSetupSwingStrategy,
    SwingScreeningConfig,
)

ZERO = Decimal("0")
RATIO_QUANTUM = Decimal("0.0001")
PRICE_QUANTUM = Decimal("0.01")
KST = ZoneInfo("Asia/Seoul")
Timeframe = Literal["1m", "5m", "10m"]
Trend = Literal["bullish", "pullback", "neutral", "bearish", "insufficient"]


class SetupProgress(BaseModel):
    passed_rules: int = Field(ge=0)
    total_rules: int = Field(ge=0)


class DailyTechnicalSummary(BaseModel):
    screening_trading_date: date | None = None
    trend: Trend
    previous_close: Decimal | None = None
    change_pct: Decimal | None = None
    sma20: Decimal | None = None
    sma60: Decimal | None = None
    ema20: Decimal | None = None
    atr_pct: Decimal | None = None
    recent_high_20: Decimal | None = None
    recent_low_20: Decimal | None = None
    screening_passed: bool
    matched_setups: list[str]
    primary_setup: str | None = None
    total_score: Decimal | None = None
    score_threshold: Decimal = Field(ge=0, le=100)
    meets_score_threshold: bool
    common_failures: list[str]
    setup_progress: dict[str, SetupProgress]


class IntradayTechnicalSummary(BaseModel):
    timeframe: Timeframe
    trend: Trend
    candle_count: int = Field(ge=0)
    session_open: Decimal | None = None
    session_high: Decimal | None = None
    session_low: Decimal | None = None
    change_from_open_pct: Decimal | None = None
    sma5: Decimal | None = None
    sma20: Decimal | None = None
    vwap: Decimal | None = None
    momentum_5_pct: Decimal | None = None
    latest_volume_ratio: Decimal | None = None
    recent_high_20: Decimal | None = None
    recent_low_20: Decimal | None = None


class PriceLevel(BaseModel):
    price: Decimal = Field(ge=0)
    basis: list[str]


class TechnicalLevels(BaseModel):
    supports: list[PriceLevel]
    resistances: list[PriceLevel]


class RealtimeTechnicalAnalysis(BaseModel):
    instrument: InstrumentSnapshot
    quote: QuoteSnapshot
    as_of: datetime
    timezone: str = "Asia/Seoul"
    refresh_after_seconds: int = 60
    daily_bars: list[DailyBar]
    intraday_bars: dict[Timeframe, list[MinuteBar]]
    daily: DailyTechnicalSummary
    intraday: dict[Timeframe, IntradayTechnicalSummary]
    levels: TechnicalLevels
    verdict: str
    observations: list[str]
    entry_confirmation: str
    invalidation: str
    risk_flags: list[str]
    warnings: list[StockWarning]
    notes: list[str]


def _ratio(value: Decimal, base: Decimal) -> Decimal | None:
    if base <= ZERO:
        return None
    return ((value - base) / base).quantize(RATIO_QUANTUM, rounding=ROUND_HALF_UP)


def _mean(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, ZERO) / Decimal(len(values))


def _price(value: Decimal) -> str:
    rounded = value.quantize(PRICE_QUANTUM, rounding=ROUND_HALF_UP)
    return f"{rounded:,.0f}원" if rounded == rounded.to_integral() else f"{rounded:,f}원"


def _percent(value: Decimal | None) -> str:
    if value is None:
        return "계산 불가"
    return f"{(value * Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):f}%"


def aggregate_minute_bars(bars: Sequence[MinuteBar], minutes: int) -> list[MinuteBar]:
    if minutes <= 0:
        raise ValueError("minutes must be positive")
    if minutes == 1:
        return list(bars)
    groups: dict[datetime, list[MinuteBar]] = defaultdict(list)
    for bar in sorted(bars, key=lambda value: value.timestamp):
        local = bar.timestamp.astimezone(KST)
        bucket = local.replace(
            minute=(local.minute // minutes) * minutes,
            second=0,
            microsecond=0,
        )
        groups[bucket].append(bar)
    aggregated: list[MinuteBar] = []
    for bucket, values in sorted(groups.items()):
        currencies = {value.currency for value in values}
        symbols = {value.symbol for value in values}
        if len(currencies) != 1 or len(symbols) != 1:
            raise ValueError("minute bars cannot mix symbols or currencies")
        aggregated.append(
            MinuteBar(
                symbol=values[0].symbol,
                timestamp=bucket,
                open=values[0].open,
                high=max(value.high for value in values),
                low=min(value.low for value in values),
                close=values[-1].close,
                volume=sum(value.volume for value in values),
                currency=values[0].currency,
                source=values[0].source,
                as_of=max(value.as_of for value in values),
            )
        )
    return aggregated


def _vwap(bars: Sequence[MinuteBar]) -> Decimal | None:
    total_volume = sum((bar.volume for bar in bars), 0)
    if total_volume <= 0:
        return None
    weighted = sum(
        ((bar.high + bar.low + bar.close) / Decimal("3") * Decimal(bar.volume) for bar in bars),
        ZERO,
    )
    return weighted / Decimal(total_volume)


def _intraday_summary(
    timeframe: Timeframe,
    bars: Sequence[MinuteBar],
    current_price: Decimal,
) -> IntradayTechnicalSummary:
    if not bars:
        return IntradayTechnicalSummary(
            timeframe=timeframe,
            trend="insufficient",
            candle_count=0,
        )
    latest_date = bars[-1].timestamp.astimezone(KST).date()
    session = [bar for bar in bars if bar.timestamp.astimezone(KST).date() == latest_date]
    closes = [bar.close for bar in bars]
    sma5 = _mean(closes[-5:])
    sma20 = _mean(closes[-20:]) if len(closes) >= 20 else None
    session_vwap = _vwap(session)
    if (
        sma5 is not None
        and sma20 is not None
        and current_price >= sma5 >= sma20
        and (session_vwap is None or current_price >= session_vwap)
    ):
        trend: Trend = "bullish"
    elif (
        sma5 is not None
        and sma20 is not None
        and current_price <= sma5 <= sma20
        and (session_vwap is None or current_price <= session_vwap)
    ):
        trend = "bearish"
    elif sma20 is None:
        trend = "insufficient"
    else:
        trend = "neutral"
    prior_volumes = [Decimal(bar.volume) for bar in bars[-21:-1]]
    average_prior_volume = _mean(prior_volumes)
    volume_ratio = (
        Decimal(bars[-1].volume) / average_prior_volume
        if average_prior_volume is not None and average_prior_volume > ZERO
        else None
    )
    recent = bars[-20:]
    return IntradayTechnicalSummary(
        timeframe=timeframe,
        trend=trend,
        candle_count=len(bars),
        session_open=session[0].open if session else None,
        session_high=max((bar.high for bar in session), default=None),
        session_low=min((bar.low for bar in session), default=None),
        change_from_open_pct=_ratio(current_price, session[0].open) if session else None,
        sma5=sma5,
        sma20=sma20,
        vwap=session_vwap,
        momentum_5_pct=_ratio(current_price, bars[-6].close) if len(bars) >= 6 else None,
        latest_volume_ratio=volume_ratio,
        recent_high_20=max((bar.high for bar in recent), default=None),
        recent_low_20=min((bar.low for bar in recent), default=None),
    )


def _daily_summary(
    bars: Sequence[DailyBar],
    quote: QuoteSnapshot,
    config: SwingScreeningConfig,
) -> DailyTechnicalSummary:
    indicators = IndicatorService().calculate(bars)
    current = quote.price
    if indicators.sma20 is None or indicators.sma60 is None:
        trend: Trend = "insufficient"
    elif current >= indicators.sma20 > indicators.sma60:
        trend = "bullish"
    elif indicators.sma20 > indicators.sma60 and current >= indicators.sma60:
        trend = "pullback"
    elif current <= indicators.sma20 < indicators.sma60:
        trend = "bearish"
    else:
        trend = "neutral"

    previous_close: Decimal | None
    quote_date = quote.as_of.astimezone(KST).date()
    if bars and bars[-1].trading_date == quote_date and len(bars) >= 2:
        previous_close = bars[-2].close
    else:
        previous_close = bars[-1].close if bars else None
    prior = list(bars[-21:-1]) if len(bars) >= 2 else list(bars)
    if not prior:
        prior = list(bars[-20:])

    screening = MultiSetupSwingStrategy(config).evaluate(bars, indicators)
    total_score = None
    if screening.passed:
        total_score = SwingCandidateRanker(config).rank([screening])[0].total_score
    progress: dict[str, SetupProgress] = {}
    grouped: dict[str, list[bool]] = defaultdict(list)
    for key, passed in screening.rule_evaluations.items():
        setup, _, _ = key.partition(":")
        grouped[setup].append(passed)
    for setup, rules in grouped.items():
        progress[setup] = SetupProgress(
            passed_rules=sum(1 for passed in rules if passed),
            total_rules=len(rules),
        )
    atr_pct = (
        indicators.atr14 / current if indicators.atr14 is not None and current > ZERO else None
    )
    return DailyTechnicalSummary(
        screening_trading_date=bars[-1].trading_date if bars else None,
        trend=trend,
        previous_close=previous_close,
        change_pct=_ratio(current, previous_close) if previous_close is not None else None,
        sma20=indicators.sma20,
        sma60=indicators.sma60,
        ema20=indicators.ema20,
        atr_pct=atr_pct,
        recent_high_20=max((bar.high for bar in prior[-20:]), default=None),
        recent_low_20=min((bar.low for bar in prior[-20:]), default=None),
        screening_passed=screening.passed,
        matched_setups=screening.matched_setups,
        primary_setup=screening.primary_setup,
        total_score=total_score,
        score_threshold=config.minimum_candidate_score,
        meets_score_threshold=(
            total_score is not None and total_score >= config.minimum_candidate_score
        ),
        common_failures=screening.reasons,
        setup_progress=progress,
    )


def _levels(
    current_price: Decimal,
    daily: DailyTechnicalSummary,
    intraday: IntradayTechnicalSummary,
) -> TechnicalLevels:
    values: list[tuple[Decimal | None, str]] = [
        (intraday.vwap, "장중 VWAP"),
        (intraday.sma20, f"{intraday.timeframe} SMA20"),
        (intraday.session_low, "당일 저가"),
        (intraday.session_high, "당일 고가"),
        (intraday.recent_low_20, f"최근 20개 {intraday.timeframe}봉 저가"),
        (intraday.recent_high_20, f"최근 20개 {intraday.timeframe}봉 고가"),
        (daily.sma20, "일봉 SMA20"),
        (daily.recent_low_20, "직전 20일 저가"),
        (daily.recent_high_20, "직전 20일 고가"),
    ]
    grouped: dict[Decimal, list[str]] = defaultdict(list)
    for value, basis in values:
        if value is not None and value >= ZERO and basis not in grouped[value]:
            grouped[value].append(basis)
    supports = [
        PriceLevel(price=price, basis=basis)
        for price, basis in sorted(
            ((price, basis) for price, basis in grouped.items() if price <= current_price),
            reverse=True,
        )[:3]
    ]
    resistances = [
        PriceLevel(price=price, basis=basis)
        for price, basis in sorted(
            ((price, basis) for price, basis in grouped.items() if price >= current_price)
        )[:3]
    ]
    return TechnicalLevels(supports=supports, resistances=resistances)


def _narrative(
    quote: QuoteSnapshot,
    daily: DailyTechnicalSummary,
    intraday: IntradayTechnicalSummary,
    levels: TechnicalLevels,
    warnings: Sequence[StockWarning],
) -> tuple[str, list[str], str, str, list[str]]:
    if daily.trend in {"bullish", "pullback"} and intraday.trend == "bullish":
        verdict = "일봉 상승 구조와 장중 흐름이 함께 우세합니다."
    elif daily.trend in {"bullish", "pullback"} and intraday.trend == "bearish":
        verdict = "일봉 상승 구조 안에서 장중 조정이 진행 중입니다."
    elif daily.trend == "bearish":
        verdict = "일봉 하락 구조로, 추세 회복 확인이 먼저 필요합니다."
    else:
        verdict = "일봉과 장중 방향이 엇갈려 추가 확인이 필요합니다."

    observations = [
        f"현재가 {_price(quote.price)}, 전일 종가 대비 {_percent(daily.change_pct)}입니다.",
        (
            f"{intraday.timeframe} 기준 장중 시가 대비 "
            f"{_percent(intraday.change_from_open_pct)}, "
            f"VWAP {_price(intraday.vwap)}입니다."
            if intraday.vwap is not None
            else f"{intraday.timeframe} 장중 VWAP을 계산할 데이터가 부족합니다."
        ),
    ]
    if daily.screening_passed and daily.total_score is not None:
        observations.append(
            f"일봉 셋업은 {daily.primary_setup or '복수 셋업'}으로 통과했고 "
            f"종합점수는 {daily.total_score}점입니다."
        )
    else:
        observations.append("현재 일봉은 스크리너의 완성된 진입 셋업을 통과하지 않았습니다.")

    if levels.resistances:
        nearest_resistance = levels.resistances[0]
        entry_confirmation = (
            f"{_price(nearest_resistance.price)} 위 안착과 "
            f"{intraday.timeframe} 거래량 증가를 함께 확인하세요."
        )
    elif intraday.vwap is not None:
        entry_confirmation = (
            f"돌파 상태를 유지하면서 {_price(intraday.vwap)} 부근의 VWAP 지지를 확인하세요."
        )
    else:
        entry_confirmation = "가격 돌파와 거래량 증가가 동시에 확인될 때까지 관찰하세요."

    if levels.supports:
        invalidation = (
            f"가장 가까운 지지 후보 {_price(levels.supports[0].price)} 이탈 시 "
            "현재 단기 시나리오를 재검토하세요."
        )
    else:
        invalidation = "명확한 지지 후보가 없어 신규 판단을 보류하는 편이 안전합니다."

    risk_flags: list[str] = []
    active_warnings = [warning for warning in warnings if warning.active]
    risk_flags.extend(
        warning.description or f"종목 경고: {warning.warning_type}" for warning in active_warnings
    )
    if quote.delayed is True:
        risk_flags.append("공급자가 지연 시세로 표시한 데이터입니다.")
    if daily.trend == "bearish":
        risk_flags.append("현재가는 일봉 하락 정렬 구간에 있습니다.")
    if (
        intraday.vwap is not None
        and intraday.vwap > ZERO
        and _ratio(quote.price, intraday.vwap) is not None
        and (_ratio(quote.price, intraday.vwap) or ZERO) >= Decimal("0.03")
    ):
        risk_flags.append("현재가가 장중 VWAP보다 3% 이상 높아 추격 변동성에 유의해야 합니다.")
    if intraday.latest_volume_ratio is not None and intraday.latest_volume_ratio < Decimal("0.70"):
        risk_flags.append("최근 봉 거래량이 직전 평균의 70% 미만이라 확인 강도가 약합니다.")
    if not risk_flags:
        risk_flags.append("현재 데이터에서 별도의 정량 경고는 감지되지 않았습니다.")
    return verdict, observations, entry_confirmation, invalidation, risk_flags


def analyze_realtime(
    instrument: InstrumentSnapshot,
    quote: QuoteSnapshot,
    daily_bars: Sequence[DailyBar],
    minute_bars: Sequence[MinuteBar],
    warnings: Sequence[StockWarning],
    config: SwingScreeningConfig | None = None,
) -> RealtimeTechnicalAnalysis:
    config = config or SwingScreeningConfig()
    frames: dict[Timeframe, list[MinuteBar]] = {
        "1m": aggregate_minute_bars(minute_bars, 1),
        "5m": aggregate_minute_bars(minute_bars, 5),
        "10m": aggregate_minute_bars(minute_bars, 10),
    }
    intraday = {
        timeframe: _intraday_summary(timeframe, bars, quote.price)
        for timeframe, bars in frames.items()
    }
    daily = _daily_summary(daily_bars, quote, config)
    primary_intraday = intraday["5m"]
    levels = _levels(quote.price, daily, primary_intraday)
    verdict, observations, entry_confirmation, invalidation, risk_flags = _narrative(
        quote,
        daily,
        primary_intraday,
        levels,
        warnings,
    )
    as_of = max(
        [quote.as_of, *(bar.as_of for bar in minute_bars), *(bar.as_of for bar in daily_bars)]
    )
    return RealtimeTechnicalAnalysis(
        instrument=instrument,
        quote=quote,
        as_of=as_of,
        daily_bars=list(daily_bars[-120:]),
        intraday_bars=frames,
        daily=daily,
        intraday=intraday,
        levels=levels,
        verdict=verdict,
        observations=observations,
        entry_confirmation=entry_confirmation,
        invalidation=invalidation,
        risk_flags=risk_flags,
        warnings=list(warnings),
        notes=[
            "실시간 웹소켓이 아닌 최신 1분봉과 현재가를 요청 시점에 조회한 결과입니다.",
            "5분봉과 10분봉은 Toss 1분봉을 Asia/Seoul 기준으로 합성했습니다.",
            "일봉 스크리너 판정은 응답에 포함된 마지막 일봉 거래일을 기준으로 합니다.",
            "가장 최근 분봉은 진행 중일 수 있어 거래량과 고가·저가가 바뀔 수 있습니다.",
            "기술적 분석은 미래 수익을 보장하지 않으며 주문이나 투자 자문이 아닙니다.",
        ],
    )


__all__ = [
    "RealtimeTechnicalAnalysis",
    "aggregate_minute_bars",
    "analyze_realtime",
]
