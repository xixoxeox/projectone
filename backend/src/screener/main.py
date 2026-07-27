import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from screener.config import get_settings
from screener.modules.identity.presentation.router import router as auth_router
from screener.modules.market.presentation.router import router as market_router
from screener.modules.operations.presentation.router import router as health_router
from screener.shared.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)
app = FastAPI(
    title="Swing Trading Screener API",
    version=settings.app_version,
    docs_url="/docs",
    openapi_url="/openapi.json",
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
