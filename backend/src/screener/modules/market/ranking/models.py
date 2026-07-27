"""Output models for candidate ranking."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from screener.modules.market.screening.models import ScreeningResult

ZERO = Decimal("0")
HUNDRED = Decimal("100")


class RankedCandidate(BaseModel):
    """A passing screening result with an explainable, bounded score."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    rank: int = Field(ge=1)
    total_score: Decimal = Field(ge=ZERO, le=HUNDRED)
    component_scores: dict[str, Decimal]
    source_result: ScreeningResult
    warnings: list[str] = Field(default_factory=list)

    @field_validator("component_scores")
    @classmethod
    def validate_component_scores(cls, component_scores: dict[str, Decimal]) -> dict[str, Decimal]:
        """Ensure every public component score has the documented bounds."""
        for name, score in component_scores.items():
            if not score.is_finite() or not ZERO <= score <= HUNDRED:
                raise ValueError(f"component score {name!r} must be between 0 and 100")
        return component_scores


__all__ = ["RankedCandidate"]
