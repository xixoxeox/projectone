from pathlib import Path

import pytest

from screener.modules.market.infrastructure.universe import load_kospi_symbols


def test_load_universe_rejects_blank_malformed_and_duplicate_symbols(tmp_path: Path) -> None:
    for body in ("symbol\n\n", "symbol\n5930\n", "symbol\n005930\n005930\n"):
        path = tmp_path / "symbols.csv"
        path.write_text(body, encoding="utf-8")
        with pytest.raises(ValueError):
            load_kospi_symbols(path)


def test_repository_universe_is_deterministic() -> None:
    symbols = load_kospi_symbols()
    assert symbols
    assert all(len(symbol) == 6 and symbol.isascii() and symbol.isdigit() for symbol in symbols)
