from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, create_refresh_token, hash_refresh_token
from app.db.models import RefreshToken, User


async def issue_token_pair(db: AsyncSession, user: User) -> tuple[str, str, int]:
    access_token, expires_in = create_access_token(user.id)
    refresh_token, token_id, expires_at = create_refresh_token(user.id)
    db.add(
        RefreshToken(
            id=token_id,
            user_id=user.id,
            token_hash=hash_refresh_token(refresh_token),
            expires_at=expires_at,
        )
    )
    return access_token, refresh_token, expires_in


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_user_id(payload: dict) -> UUID | None:
    subject = payload.get("sub")
    if not isinstance(subject, str):
        return None
    try:
        return UUID(subject)
    except ValueError:
        return None
