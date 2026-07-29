"""Typed outputs produced by the indicator and screening layers."""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class IndicatorSnapshot(BaseModel):
    """Latest values for the reusable indicators, or ``None`` without enough bars."""

    sma5: Decimal | None = None
    sma20: Decimal | None = None
    sma60: Decimal | None = None
    sma120: Decimal | None = None
    ema20: Decimal | None = None
    atr14: Decimal | None = None
    avg_volume20: Decimal | None = None
    highest20: Decimal | None = None
    lowest20: Decimal | None = None
    highest60: Decimal | None = None
    lowest60: Decimal | None = None


class ScreeningResult(BaseModel):
    """Strategy-neutral result for evaluating one symbol."""

    symbol: str
    passed: bool
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, Decimal] = Field(default_factory=dict)
    matched_setups: list[str] = Field(default_factory=list)
    primary_setup: str | None = None
    setup_scores: dict[str, Decimal] = Field(default_factory=dict)
    screener_name: str | None = None
    screener_version: str | None = None
    configuration_snapshot: dict[str, Any] = Field(default_factory=dict)
    setup_metrics: dict[str, dict[str, Decimal]] = Field(default_factory=dict)
    rule_evaluations: dict[str, bool] = Field(default_factory=dict)
