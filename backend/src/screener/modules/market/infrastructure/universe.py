import csv
import re
from importlib.resources import files
from pathlib import Path
from typing import IO

SYMBOL_PATTERN = re.compile(r"^[0-9A-Z]{6}$", re.ASCII)


def _read_symbols(stream: IO[str]) -> list[str]:
    reader = csv.DictReader(stream)
    if reader.fieldnames != ["symbol"]:
        raise ValueError("universe CSV must have exactly one 'symbol' column")
    return [row["symbol"].strip() for row in reader]


def load_kospi_symbols(path: Path | None = None) -> list[str]:
    """Load a deterministic symbol snapshot, failing closed on corrupt input."""
    if path is None:
        resource = files("screener.data").joinpath("kospi_common_stock_symbols.csv")
        with resource.open("r", encoding="utf-8") as stream:
            symbols = _read_symbols(stream)
    else:
        with path.open(encoding="utf-8", newline="") as stream:
            symbols = _read_symbols(stream)
    if not symbols:
        raise ValueError("universe snapshot is empty")
    malformed = [symbol for symbol in symbols if not SYMBOL_PATTERN.fullmatch(symbol)]
    if malformed:
        raise ValueError(f"malformed universe symbol: {malformed[0]!r}")
    if len(symbols) != len(set(symbols)):
        raise ValueError("duplicate universe symbols")
    return symbols
