import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from screener.config import Settings, get_settings
from screener.modules.identity.application.security import (
    create_access_token,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)
from screener.modules.identity.infrastructure.models import RefreshSession, User
from screener.modules.identity.presentation.dependencies import CurrentUser
from screener.modules.identity.presentation.schemas import (
    AccessTokenResponse,
    LoginRequest,
    UserResponse,
)
from screener.shared.database import get_db_session

router = APIRouter(prefix="/auth", tags=["authentication"])
DbSession = Annotated[AsyncSession, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        "refresh_token",
        token,
        max_age=settings.refresh_ttl_days * 86400,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="lax",
        path=f"{settings.api_base_path}/auth",
    )


@router.post("/login", response_model=AccessTokenResponse)
async def login(
    payload: LoginRequest, response: Response, session: DbSession, settings: AppSettings
) -> AccessTokenResponse:
    user = await session.scalar(select(User).where(User.username == payload.username))
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password"
        )
    raw_token = new_refresh_token()
    session.add(
        RefreshSession(
            user_id=user.id,
            family_id=uuid.uuid4(),
            token_hash=hash_refresh_token(raw_token, settings.refresh_token_pepper),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_ttl_days),
        )
    )
    set_refresh_cookie(response, raw_token, settings)
    token, ttl = create_access_token(user.id, user.role, settings)
    return AccessTokenResponse(access_token=token, expires_in=ttl)


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(
    response: Response,
    session: DbSession,
    settings: AppSettings,
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> AccessTokenResponse:
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token required")
    token_hash = hash_refresh_token(refresh_token, settings.refresh_token_pepper)
    stored = await session.scalar(
        select(RefreshSession).where(RefreshSession.token_hash == token_hash)
    )
    now = datetime.now(UTC)
    if stored is None or stored.revoked_at is not None or stored.expires_at <= now:
        raise HTTPException(status_code=401, detail="Invalid refresh session")
    user = await session.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid refresh session")
    stored.revoked_at = now
    raw_token = new_refresh_token()
    session.add(
        RefreshSession(
            user_id=user.id,
            family_id=stored.family_id,
            token_hash=hash_refresh_token(raw_token, settings.refresh_token_pepper),
            expires_at=now + timedelta(days=settings.refresh_ttl_days),
        )
    )
    set_refresh_cookie(response, raw_token, settings)
    token, ttl = create_access_token(user.id, user.role, settings)
    return AccessTokenResponse(access_token=token, expires_in=ttl)


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    session: DbSession,
    settings: AppSettings,
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> None:
    if refresh_token:
        await session.execute(
            update(RefreshSession)
            .where(
                RefreshSession.token_hash
                == hash_refresh_token(refresh_token, settings.refresh_token_pepper),
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
    response.delete_cookie("refresh_token", path=f"{settings.api_base_path}/auth")


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse(id=user.id, username=user.username, role=user.role)
