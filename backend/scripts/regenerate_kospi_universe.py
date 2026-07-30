"""Regenerate the packaged, reviewed universe from a normalized KRX export."""

import argparse
import shutil
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from screener.modules.market.infrastructure.krx_universe import (
    build_universe,
    sha256,
    write_symbols,
)


def main() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=backend_root / "src/screener/data/kospi_common_stock_symbols.csv",
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=backend_root / "src/screener/data/kospi_common_stock_symbols_metadata.txt",
    )
    parser.add_argument("--mirror-directory", type=Path, default=backend_root / "data")
    parser.add_argument("--processing-date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--source-file")
    args = parser.parse_args()
    result = build_universe(args.source)
    if result.malformed_symbols:
        raise SystemExit(f"refusing malformed symbols: {result.malformed_symbols}")
    write_symbols(result.symbols, args.output)
    original = args.source.with_name("krx_listed_companies_source_metadata.txt")
    source_metadata: dict[str, str] = {}
    if original.exists():
        for line in original.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator:
                source_metadata[key] = value
    source_file = args.source_file or source_metadata.get("source_file")
    if not source_file:
        raise SystemExit("source_file is absent from source metadata; pass --source-file")
    source_file_sha = source_metadata.get("source_sha256", "unknown")
    lines = [
        f"processing_date={args.processing_date.isoformat()}",
        f"source_file={source_file}",
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
    args.mirror_directory.mkdir(parents=True, exist_ok=True)
    mirror_csv = args.mirror_directory / args.output.name
    mirror_metadata = args.mirror_directory / args.metadata.name
    shutil.copyfile(args.output, mirror_csv)
    shutil.copyfile(args.metadata, mirror_metadata)
    if args.output.read_bytes() != mirror_csv.read_bytes():
        raise SystemExit("generated universe mirror differs from package resource")
    if args.metadata.read_bytes() != mirror_metadata.read_bytes():
        raise SystemExit("generated metadata mirror differs from package resource")
    print(f"generated {len(result.symbols)} symbols")


if __name__ == "__main__":
    main()
