import csv
import hashlib
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

import pytest

from screener.modules.market.infrastructure.krx_universe import (
    build_universe,
    convert_html_export,
    exclusion_category,
)
from screener.modules.market.infrastructure.universe import load_kospi_symbols


def test_load_universe_rejects_blank_malformed_and_duplicate_symbols(tmp_path: Path) -> None:
    for body in ("symbol\n\n", "symbol\n5930\n", "symbol\n005930\n005930\n"):
        path = tmp_path / "symbols.csv"
        path.write_text(body, encoding="utf-8")
        with pytest.raises(ValueError):
            load_kospi_symbols(path)


def test_repository_universe_is_deterministic() -> None:
    symbols = load_kospi_symbols()
    assert len(symbols) == 807
    assert "0126Z0" in symbols
    assert "000020" in symbols
    assert all(len(symbol) == 6 and symbol.isascii() and symbol.isalnum() for symbol in symbols)
    resource = Path(__file__).parents[2] / "src/screener/data/kospi_common_stock_symbols.csv"
    assert hashlib.sha256(resource.read_bytes()).hexdigest() == (
        "ff6051b921736aed59d3ac80706c8408acbf8d94879cd7b5b316d2948e689406"
    )
    metadata = files("screener.data").joinpath("kospi_common_stock_symbols_metadata.txt")
    assert "final_symbol_count=807" in metadata.read_text(encoding="utf-8")


def test_operating_fund_manager_is_included_but_fund_vehicle_is_excluded() -> None:
    symbols = load_kospi_symbols()
    assert "026890" in symbols  # 스틱인베스트먼트
    assert "094800" not in symbols  # 맵스리얼티


def test_regeneration_uses_cli_provenance_and_updates_identical_mirror(tmp_path: Path) -> None:
    source = tmp_path / "future.csv"
    source.write_text(
        "회사명,시장구분,종목코드,업종,주요제품\n회사,유가,005930,제조업,제품\n",
        encoding="utf-8",
    )
    output = tmp_path / "package" / "symbols.csv"
    metadata = tmp_path / "package" / "metadata.txt"
    mirror = tmp_path / "mirror"
    script = Path(__file__).parents[2] / "scripts/regenerate_kospi_universe.py"
    subprocess.run(
        [
            sys.executable,
            str(script),
            str(source),
            "--output",
            str(output),
            "--metadata",
            str(metadata),
            "--mirror-directory",
            str(mirror),
            "--processing-date",
            "2030-02-03",
            "--source-file",
            "future.xls",
        ],
        check=True,
    )
    assert output.read_bytes() == (mirror / output.name).read_bytes()
    assert metadata.read_bytes() == (mirror / metadata.name).read_bytes()
    provenance = metadata.read_text(encoding="utf-8")
    assert "processing_date=2030-02-03" in provenance
    assert "source_file=future.xls" in provenance


def test_html_xls_conversion_preserves_cp949_text_and_leading_zeroes(tmp_path: Path) -> None:
    source = tmp_path / "상장법인목록.xls"
    source.write_bytes(
        "<table><tr><th>회사명</th><th>종목코드</th></tr>"
        "<tr><td>삼성전자</td><td>005930</td></tr></table>".encode("cp949")
    )
    output = tmp_path / "normalized.csv"
    assert convert_html_export(source, output) == "cp949"
    with output.open(encoding="utf-8", newline="") as stream:
        assert list(csv.reader(stream)) == [["회사명", "종목코드"], ["삼성전자", "005930"]]


def test_builder_deduplicates_and_rejects_conflicting_duplicates(tmp_path: Path) -> None:
    header = "회사명,시장구분,종목코드,업종,주요제품\n"
    path = tmp_path / "source.csv"
    path.write_text(
        header + "회사,유가,00A001,제조업,제품\n회사,유가,00A001,제조업,제품\n", encoding="utf-8"
    )
    result = build_universe(path)
    assert result.symbols == ["00A001"]
    assert result.duplicate_rows == 1
    path.write_text(
        header + "회사,유가,005930,제조업,제품\n다른회사,유가,005930,제조업,제품\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="conflicting duplicate"):
        build_universe(path)


@pytest.mark.parametrize(
    ("name", "industry", "product", "category"),
    [
        ("샘플 ETF", "금융", "ETF", "etf"),
        ("샘플 ETN", "금융", "ETN", "etn"),
        ("샘플우", "제조", "제품", "preferred_share"),
        ("샘플스팩", "금융", "기업인수목적", "spac"),
        ("샘플리츠", "부동산 임대 및 공급업", "임대", "reit_or_real_estate_investment_company"),
        ("샘플홀딩스", "금융", "지주회사", None),
    ],
)
def test_documented_product_exclusions(
    name: str, industry: str, product: str, category: str | None
) -> None:
    row = {
        "회사명": name,
        "시장구분": "유가",
        "종목코드": "005930",
        "업종": industry,
        "주요제품": product,
    }
    assert exclusion_category(row) == category
