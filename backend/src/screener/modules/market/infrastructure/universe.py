import csv
import re
from pathlib import Path

DEFAULT_UNIVERSE_PATH = (
    Path(__file__).resolve().parents[5] / "data" / "kospi_common_stock_symbols.csv"
)
SYMBOL_PATTERN = re.compile(r"^[0-9]{6}$")


def load_kospi_symbols(path: Path = DEFAULT_UNIVERSE_PATH) -> list[str]:
    """Load a deterministic symbol snapshot, failing closed on corrupt input."""
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["symbol"]:
            raise ValueError("universe CSV must have exactly one 'symbol' column")
        symbols = [row["symbol"].strip() for row in reader]
    if not symbols:
        raise ValueError("universe snapshot is empty")
    malformed = [symbol for symbol in symbols if not SYMBOL_PATTERN.fullmatch(symbol)]
    if malformed:
        raise ValueError(f"malformed universe symbol: {malformed[0]!r}")
    if len(symbols) != len(set(symbols)):
        raise ValueError("duplicate universe symbols")
    return symbols
