# KOSPI common-share universe

`kospi_common_stock_symbols.csv` mirrors the production package resource in
`src/screener/data`. Toss resolves symbols but does not enumerate KOSPI.

- **Source:** Korea Exchange (KRX) Data Marketplace, *Listed corporation details*,
  <https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201020101>
- **Processed:** 2026-07-30
- **Source conversion:** 848 CP949 HTML-export rows normalized to UTF-8 CSV; 848
  KOSPI rows, 833 unique symbols, 15 duplicate rows, three alphanumeric symbols,
  and no malformed symbols.
- **Selection:** 806 KOSPI operating-company common shares. Excluded: 23 REIT or
  real-estate investment companies, two infrastructure funds, and two
  collective-investment/fund-like products. The same deterministic rules also
  recognize ETFs, ETNs, preferred shares, warrants, SPACs and delisted issues
  (none occurred in this source). Ordinary holding companies remain included.

Checksums, category counts, and processing rules are recorded in
`kospi_common_stock_symbols_metadata.txt`. To regenerate from a future normalized
KRX/KIND export and validate it:

```bash
cd backend
python scripts/regenerate_kospi_universe.py data/krx_listed_companies_source.csv
python scripts/validate_kospi_universe.py data/kospi_common_stock_symbols.csv
```
