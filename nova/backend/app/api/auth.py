from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.security import decode_token, hash_password, hash_refresh_token, verify_password
from app.db.models import RefreshToken, User
from app.db.session import get_db
from app.services.auth import issue_token_pair, parse_user_id, utc_now


router = APIRouter(prefix="/auth", tags=["auth"])
bearer_scheme = HTTPBearer(auto_error=False)


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


def normalize_email(email: str) -> str:
    return email.strip().lower()


def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=refresh_token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.secure_cookies,
        samesite=settings.cookie_samesite,
        path="/auth",
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=settings.refresh_cookie_name, path="/auth")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise ValueError("Wrong token type")
        user_id = parse_user_id(payload)
        if user_id is None:
            raise ValueError("Invalid subject")
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def build_token_response(db: AsyncSession, user: User, response: Response) -> TokenResponse:
    access_token, refresh_token, expires_in = await issue_token_pair(db, user)
    await db.commit()
    set_refresh_cookie(response, refresh_token)
    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        user=UserResponse.model_validate(user),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(credentials: Credentials, response: Response, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    email = normalize_email(str(credentials.email))
    existing_user = await db.scalar(select(User).where(User.email == email))
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered")

    hashed_password = await run_in_threadpool(hash_password, credentials.password)
    user = User(email=email, hashed_password=hashed_password)
    db.add(user)
    try:
        await db.flush()
        result = await build_token_response(db, user, response)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered") from None
    return result


@router.post("/login", response_model=TokenResponse)
async def login(credentials: Credentials, response: Response, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    email = normalize_email(str(credentials.email))
    user = await db.scalar(select(User).where(User.email == email))
    password_is_valid = (
        user is not None
        and await run_in_threadpool(verify_password, credentials.password, user.hashed_password)
    )
    if not password_is_valid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    return await build_token_response(db, user, response)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=settings.refresh_cookie_name),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token is required")

    try:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh" or not isinstance(payload.get("jti"), str):
            raise ValueError("Invalid refresh token claims")
        user_id = parse_user_id(payload)
        if user_id is None:
            raise ValueError("Invalid refresh token subject")
    except (JWTError, ValueError):
        clear_refresh_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token") from None

    token_record = await db.scalar(
        select(RefreshToken).where(
            RefreshToken.id == payload["jti"],
            RefreshToken.token_hash == hash_refresh_token(refresh_token),
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
    )
    if token_record is None:
        clear_refresh_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked refresh token")

    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None:
        clear_refresh_cookie(response)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists")

    token_record.revoked_at = utc_now()
    return await build_token_response(db, user, response)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=settings.refresh_cookie_name),
    db: AsyncSession = Depends(get_db),
) -> None:
    if refresh_token:
        try:
            payload = decode_token(refresh_token)
            token_id = payload.get("jti")
            if isinstance(token_id, str):
                token_record = await db.scalar(
                    select(RefreshToken).where(
                        RefreshToken.id == token_id,
                        RefreshToken.token_hash == hash_refresh_token(refresh_token),
                        RefreshToken.revoked_at.is_(None),
                    )
                )
                if token_record is not None:
                    token_record.revoked_at = utc_now()
                    await db.commit()
        except JWTError:
            pass
    clear_refresh_cookie(response)


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)
