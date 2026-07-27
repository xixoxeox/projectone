"""Explicit, manual, read-only Toss market-data connectivity check."""

import argparse
import asyncio
import os
from datetime import date, timedelta

import httpx

from screener.config import Settings
from screener.modules.market.infrastructure.toss import TokenManager, TossMarketDataProvider


async def verify(symbol: str) -> None:
    settings = Settings()
    if os.getenv("ALLOW_LIVE_TOSS_SMOKE_TEST") != "true":
        raise RuntimeError("Set ALLOW_LIVE_TOSS_SMOKE_TEST=true to enable this read-only check")
    if not settings.toss_client_id or not settings.toss_client_secret:
        raise RuntimeError("Toss credentials are not configured")
    async with httpx.AsyncClient(
        base_url=settings.toss_api_base_url, timeout=settings.toss_request_timeout_seconds
    ) as client:
        tokens = TokenManager(
            client,
            settings.toss_client_id,
            settings.toss_client_secret.get_secret_value(),
            skew_seconds=settings.toss_token_expiry_skew_seconds,
        )
        provider = TossMarketDataProvider(client, tokens, max_retries=settings.toss_max_retries)
        instrument = await provider.instrument(symbol)
        quotes = await provider.prices([symbol])
        today = date.today()
        bars = await provider.daily_bars(symbol, today - timedelta(days=7), today)
        warnings = await provider.warnings(symbol)
        print("READ-ONLY Toss smoke test succeeded")
        print(
            f"instrument={instrument.symbol} quotes={len(quotes)} "
            f"bars={len(bars)} warnings={len(warnings)}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Toss market-data smoke test")
    parser.add_argument("--symbol", default="005930")
    args = parser.parse_args()
    asyncio.run(verify(args.symbol))


if __name__ == "__main__":
    main()
