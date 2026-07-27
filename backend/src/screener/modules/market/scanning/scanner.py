"""Candidate scanning orchestration."""

from collections.abc import Sequence

from screener.modules.market.scanning.models import ScanInput
from screener.modules.market.screening.engine import ScreeningEngine
from screener.modules.market.screening.models import ScreeningResult


class CandidateScanner:
    """Evaluate a caller-provided batch and retain its passing results."""

    def __init__(self, engine: ScreeningEngine) -> None:
        self._engine = engine

    def scan(self, inputs: Sequence[ScanInput]) -> list[ScreeningResult]:
        """Return passing results in input order after validating the batch."""
        self._validate_request(inputs)

        candidates: list[ScreeningResult] = []
        for scan_input in inputs:
            result = self._evaluate(scan_input)
            if result.passed:
                candidates.append(result)
        return candidates

    @classmethod
    def _validate_request(cls, inputs: Sequence[ScanInput]) -> None:
        seen_symbols: set[str] = set()
        for scan_input in inputs:
            cls._validate_input(scan_input)
            if scan_input.symbol in seen_symbols:
                raise ValueError(f"Duplicate scan input symbol: {scan_input.symbol}")
            seen_symbols.add(scan_input.symbol)

    @staticmethod
    def _validate_input(scan_input: ScanInput) -> None:
        if not scan_input.symbol.strip():
            raise ValueError("Scan input symbol must not be blank")

        bar_symbols = {bar.symbol for bar in scan_input.bars}
        if len(bar_symbols) > 1:
            raise ValueError(
                f"Bars for {scan_input.symbol} contain multiple symbols: "
                f"{', '.join(sorted(bar_symbols))}"
            )
        if bar_symbols and scan_input.symbol not in bar_symbols:
            bar_symbol = next(iter(bar_symbols))
            raise ValueError(
                f"Bar symbol {bar_symbol} does not match scan input symbol {scan_input.symbol}"
            )

    def _evaluate(self, scan_input: ScanInput) -> ScreeningResult:
        result = self._engine.evaluate(scan_input.bars, scan_input.indicators)
        if result.symbol and result.symbol != scan_input.symbol:
            raise ValueError(
                f"Screening result symbol {result.symbol} does not match "
                f"scan input symbol {scan_input.symbol}"
            )
        if not result.symbol:
            return result.model_copy(update={"symbol": scan_input.symbol})
        return result
