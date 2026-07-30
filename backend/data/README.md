# KOSPI common-share universe

`kospi_common_stock_symbols.csv` is the version-controlled input universe used by the
market sync. Toss resolves symbols but does not enumerate KOSPI.

- **Source:** Korea Exchange (KRX) Data Marketplace, *Listed corporation details*,
  <https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0201020101>
- **As of:** 2026-07-29
- **Selection:** KOSPI (`STK`), listed ordinary/common shares only. ETFs, ETNs,
  preferred shares, warrants and delisted issues are excluded.

This repository snapshot is intentionally reviewed and versioned. To replace it,
export the official KRX report, select its six-digit ordinary-share codes, write a
single `symbol` column, update the metadata above, and validate it with:

```bash
cd backend
python scripts/validate_kospi_universe.py data/kospi_common_stock_symbols.csv
```
