"""Deterministically build the reviewed KOSPI operating-company universe."""

import csv
import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from screener.modules.market.infrastructure.universe import SYMBOL_PATTERN

REQUIRED_COLUMNS = ("회사명", "시장구분", "종목코드", "업종", "주요제품")
PREFERRED = re.compile(r"(?:우|우B|우C|[1-9]우)$")
SPAC = re.compile(r"스팩|기업인수목적")
REIT = re.compile(r"리츠")
WARRANT = re.compile(r"워런트|신주인수권")
ETF = re.compile(r"(?:^|\s)ETF(?:$|\s)|상장지수펀드", re.IGNORECASE)
ETN = re.compile(r"(?:^|\s)ETN(?:$|\s)|상장지수증권", re.IGNORECASE)
DELISTED = re.compile(r"상장폐지|폐지종목")
INFRASTRUCTURE_FUND = re.compile(r"인프라")
FUND_LIKE = re.compile(r"맵스리얼티|사모펀드|증권투자회사|집합투자")


@dataclass(frozen=True)
class BuildResult:
    symbols: list[str]
    source_rows: int
    kospi_rows: int
    unique_symbols: int
    duplicate_rows: int
    alphanumeric_symbols: int
    malformed_symbols: int
    exclusions: Counter[str]


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "tr":
            self._row = []
        elif tag.lower() in {"th", "td"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"th", "td"} and self._cell is not None and self._row is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None
        elif tag.lower() == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def convert_html_export(source: Path, destination: Path) -> str:
    """Convert KRX's HTML-with-.xls-suffix export to a normalized UTF-8 CSV."""
    raw = source.read_bytes()
    encoding = next(
        (candidate for candidate in ("cp949", "euc-kr") if _can_decode(raw, candidate)), None
    )
    if encoding is None:
        raise ValueError("KRX export is not valid CP949/EUC-KR")
    parser = _TableParser()
    parser.feed(raw.decode(encoding))
    if not parser.rows:
        raise ValueError("KRX HTML export contains no table rows")
    width = len(parser.rows[0])
    if any(len(row) != width for row in parser.rows):
        raise ValueError("KRX HTML export has inconsistent table rows")
    with destination.open("w", encoding="utf-8", newline="") as stream:
        csv.writer(stream, lineterminator="\n").writerows(parser.rows)
    return encoding


def _can_decode(raw: bytes, encoding: str) -> bool:
    try:
        raw.decode(encoding)
    except UnicodeDecodeError:
        return False
    return True


def exclusion_category(row: dict[str, str]) -> str | None:
    name = row["회사명"].strip()
    text = " ".join((name, row["업종"], row["주요제품"]))
    # Priority makes category counts stable when a product matches multiple rules.
    if (
        REIT.search(name) and row["업종"] in {"신탁업 및 집합투자업", "부동산 임대 및 공급업"}
    ) or "부동산투자회사" in row["주요제품"]:
        return "reit_or_real_estate_investment_company"
    if INFRASTRUCTURE_FUND.search(name):
        return "infrastructure_fund"
    for category, pattern in (
        ("etf", ETF),
        ("etn", ETN),
        ("preferred_share", PREFERRED),
        ("warrant", WARRANT),
        ("spac", SPAC),
        ("delisted", DELISTED),
        ("collective_investment_or_fund_like", FUND_LIKE),
    ):
        target = name if category == "preferred_share" else text
        if category == "collective_investment_or_fund_like":
            target = f"{name} {row['주요제품']}"
        if pattern.search(target):
            return category
    return None


def build_universe(source: Path) -> BuildResult:
    with source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or any(
            column not in reader.fieldnames for column in REQUIRED_COLUMNS
        ):
            raise ValueError("normalized KRX CSV is missing required columns")
        rows = list(reader)
    kospi = [row for row in rows if row["시장구분"].strip() in {"유가", "KOSPI", "STK"}]
    by_symbol: dict[str, dict[str, str]] = {}
    duplicates = malformed = alphanumeric = 0
    for row in kospi:
        symbol = row["종목코드"].strip().upper()
        if not SYMBOL_PATTERN.fullmatch(symbol):
            malformed += 1
            continue
        if not symbol.isdigit():
            alphanumeric += 1
        previous = by_symbol.get(symbol)
        if previous is not None:
            duplicates += 1
            if (previous["회사명"].strip(), previous["시장구분"].strip()) != (
                row["회사명"].strip(),
                row["시장구분"].strip(),
            ):
                raise ValueError(f"conflicting duplicate symbol: {symbol}")
        else:
            by_symbol[symbol] = row
    exclusions: Counter[str] = Counter()
    symbols: list[str] = []
    for symbol, row in by_symbol.items():
        category = exclusion_category(row)
        if category is None:
            symbols.append(symbol)
        else:
            exclusions[category] += 1
    return BuildResult(
        symbols=sorted(symbols),
        source_rows=len(rows),
        kospi_rows=len(kospi),
        unique_symbols=len(by_symbol),
        duplicate_rows=duplicates,
        alphanumeric_symbols=alphanumeric,
        malformed_symbols=malformed,
        exclusions=exclusions,
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_symbols(symbols: list[str], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        "symbol\n" + "".join(f"{symbol}\n" for symbol in symbols), encoding="utf-8"
    )
