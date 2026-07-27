import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from screener.config import get_settings
from screener.modules.identity.presentation.router import router as auth_router
from screener.modules.market.application import MarketDataService
from screener.modules.market.infrastructure.toss import TokenManager, TossMarketDataProvider
from screener.modules.market.presentation.router import router as market_router
from screener.modules.operations.presentation.router import router as health_router
from screener.shared.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    client = httpx.AsyncClient(
        base_url=settings.toss_api_base_url,
        timeout=httpx.Timeout(settings.toss_request_timeout_seconds),
    )
    tokens = None
    if settings.toss_client_id and settings.toss_client_secret:
        tokens = TokenManager(
            client,
            settings.toss_client_id,
            settings.toss_client_secret.get_secret_value(),
            skew_seconds=settings.toss_token_expiry_skew_seconds,
        )
    provider = TossMarketDataProvider(client, tokens, max_retries=settings.toss_max_retries)
    app.state.toss_http_client = client
    app.state.token_manager = tokens
    app.state.market_data_provider = provider
    app.state.market_data_service = MarketDataService(provider)
    try:
        yield
    finally:
        await client.aclose()


app = FastAPI(
    title="Swing Trading Screener API",
    version=settings.app_version,
    docs_url="/docs",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


app.include_router(auth_router, prefix=settings.api_base_path)
app.include_router(health_router, prefix=settings.api_base_path)
app.include_router(market_router, prefix=settings.api_base_path)
