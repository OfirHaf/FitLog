"""
Authentication router for FitLog.
Handles user registration, login, and JWT token management.
"""

import logging
import time
from collections import defaultdict
from threading import Lock
from typing import Optional

from fastapi import APIRouter, status, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.database import get_session
from app.db import User
from app.exceptions import AuthError, ConflictError, DomainValidationError, NotFoundError, RateLimitError
from app.models import UserRegister, UserLogin, TokenResponse, UserResponse
from app.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
    verify_token,
    validate_password_strength,
)

logger = logging.getLogger(__name__)

# ─── Login rate limiter ────────────────────────────────────────────────────
_login_attempts: dict[str, list[float]] = defaultdict(list)
_login_lock = Lock()
_MAX_ATTEMPTS = 10
_WINDOW_SECONDS = 60.0


def _check_rate_limit(identifier: str) -> None:
    """Raise 429 if identifier exceeded login attempt rate limit."""
    now = time.monotonic()
    with _login_lock:
        attempts = _login_attempts[identifier]
        _login_attempts[identifier] = [t for t in attempts if now - t < _WINDOW_SECONDS]
        if len(_login_attempts[identifier]) >= _MAX_ATTEMPTS:
            raise RateLimitError(
                "Too many login attempts. Please wait before trying again.",
                retry_after=int(_WINDOW_SECONDS),
            )
        _login_attempts[identifier].append(now)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="Create a new user account with email and password",
)
async def register(body: UserRegister, session: AsyncSession = Depends(get_session)):
    """Register a new user."""
    is_valid, error_msg = validate_password_strength(body.password)
    if not is_valid:
        raise DomainValidationError(
            f"Password validation failed: {error_msg}. Please ensure your password has at least 8 characters, one uppercase, one lowercase, one number, and one special character."
        )

    stmt = select(User).where(User.email == body.email)
    result = await session.execute(stmt)
    existing_user = result.scalars().first()

    if existing_user:
        raise ConflictError("An account with those details already exists.")

    hashed_password = hash_password(body.password)

    new_user = User(
        email=body.email,
        name=body.name,
        hashed_password=hashed_password,
    )

    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)

    token = create_access_token({"user_id": str(new_user.id), "email": new_user.email})
    refresh_token = create_refresh_token({"user_id": str(new_user.id), "email": new_user.email})

    return TokenResponse(
        access_token=token,
        refresh_token=refresh_token,
        user_id=str(new_user.id),
        name=new_user.name,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login user",
    description="Authenticate user with email and password, returns JWT token",
)
async def login(body: UserLogin, session: AsyncSession = Depends(get_session)):
    """Login user and return JWT token."""
    _check_rate_limit(body.email)
    # Find user by email
    stmt = select(User).where(User.email == body.email)
    result = await session.execute(stmt)
    user = result.scalars().first()

    if not user:
        raise AuthError("Invalid email or password")

    # Verify password
    if not verify_password(body.password, user.hashed_password):
        raise AuthError("Invalid email or password")

    # Create JWT token
    token = create_access_token({"user_id": str(user.id), "email": user.email})
    refresh_token = create_refresh_token({"user_id": str(user.id), "email": user.email})

    return TokenResponse(
        access_token=token,
        refresh_token=refresh_token,
        user_id=str(user.id),
        name=user.name,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user",
    description="Get the profile of the logged-in user",
)
async def get_current_user(
    authorization: str = Header(None),
    session: AsyncSession = Depends(get_session),
):
    """Get current logged-in user."""
    if not authorization:
        raise AuthError("Missing authorization header")

    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthError("Invalid authorization header format. Expected 'Bearer <token>'")

    token = parts[1]

    payload = verify_token(token)
    if not payload:
        raise AuthError("Invalid or expired token")

    user_id = payload.get("user_id")
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalars().first()

    if not user:
        raise NotFoundError("User not found")

    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
    )


@router.post("/logout", summary="Logout user")
async def logout():
    """Logout user (client should discard token)."""
    return {"message": "Logged out successfully. Please discard your token."}


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
    description="Exchange a valid refresh token for a new access token",
)
async def refresh_token(
    authorization: str = Header(None),
    session: AsyncSession = Depends(get_session),
):
    """Refresh an access token using a refresh token."""
    if not authorization:
        raise AuthError("Missing authorization header")
    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthError("Invalid authorization header format. Expected 'Bearer <token>'")

    payload = verify_refresh_token(parts[1])
    if not payload:
        raise AuthError("Invalid or expired refresh token")

    user_id = payload.get("user_id")
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalars().first()
    if not user:
        raise NotFoundError("User not found")

    new_access = create_access_token({"user_id": str(user.id), "email": user.email})
    new_refresh = create_refresh_token({"user_id": str(user.id), "email": user.email})
    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        user_id=str(user.id),
        name=user.name,
    )


# ─────────────────────────────────────────────
# Dependency: Get current authenticated user
# ─────────────────────────────────────────────


async def get_current_user_from_header(
    authorization: Optional[str] = Header(None),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Extract and verify user from JWT token in Authorization header."""
    if not authorization:
        raise AuthError("Missing authorization header")

    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthError("Invalid authorization header format. Expected 'Bearer <token>'")

    token = parts[1]

    payload = verify_token(token)
    if not payload:
        raise AuthError("Invalid or expired token")

    user_id = payload.get("user_id")
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalars().first()

    if not user:
        raise NotFoundError("User not found")

    return user
