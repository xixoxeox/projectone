"""Validate a reviewed KRX universe snapshot before committing it."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from screener.modules.market.infrastructure.universe import load_kospi_symbols


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    symbols = load_kospi_symbols(args.path)
    print(f"valid KOSPI common-share universe: {len(symbols)} symbols")


if __name__ == "__main__":
    main()
