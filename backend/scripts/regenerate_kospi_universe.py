"""Regenerate the packaged, reviewed universe from a normalized KRX export."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from screener.modules.market.infrastructure.krx_universe import (
    build_universe,
    sha256,
    write_symbols,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--output", type=Path, default=Path("src/screener/data/kospi_common_stock_symbols.csv")
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=Path("src/screener/data/kospi_common_stock_symbols_metadata.txt"),
    )
    args = parser.parse_args()
    result = build_universe(args.source)
    if result.malformed_symbols:
        raise SystemExit(f"refusing malformed symbols: {result.malformed_symbols}")
    write_symbols(result.symbols, args.output)
    original = args.source.with_name("krx_listed_companies_source_metadata.txt")
    source_file_sha = "unknown"
    if original.exists():
        for line in original.read_text(encoding="utf-8").splitlines():
            if line.startswith("source_sha256="):
                source_file_sha = line.partition("=")[2]
    lines = [
        "processing_date=2026-07-30",
        "source_file=상장법인목록.xls",
        f"source_file_sha256={source_file_sha}",
        f"source_csv={args.source.name}",
        f"source_csv_sha256={sha256(args.source)}",
        f"source_rows={result.source_rows}",
        f"kospi_rows={result.kospi_rows}",
        f"unique_symbols={result.unique_symbols}",
        f"duplicate_symbol_rows={result.duplicate_rows}",
        f"alphanumeric_symbols={result.alphanumeric_symbols}",
        f"malformed_symbols={result.malformed_symbols}",
    ]
    lines.extend(f"excluded_{key}={result.exclusions[key]}" for key in sorted(result.exclusions))
    lines.extend(
        (
            f"final_symbol_count={len(result.symbols)}",
            f"final_csv_sha256={sha256(args.output)}",
            "rules=KOSPI rows; uppercase ^[0-9A-Z]{6}$; deduplicate with name/market "
            "conflict failure; deterministic prioritized product exclusions; lexical symbol order",
        )
    )
    args.metadata.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"generated {len(result.symbols)} symbols")


if __name__ == "__main__":
    main()
