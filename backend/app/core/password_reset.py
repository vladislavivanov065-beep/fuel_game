import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.password_reset_token import PasswordResetToken

settings = get_settings()


async def create_reset_token(db: AsyncSession, user_id: uuid.UUID) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.password_reset_ttl_seconds)
    db.add(PasswordResetToken(token=token, user_id=user_id, expires_at=expires_at))
    await db.commit()
    return token


async def consume_reset_token(db: AsyncSession, token: str) -> uuid.UUID | None:
    """Atomically marks the token used and returns its user_id, or None if it
    doesn't exist / is expired / was already used — a single UPDATE...RETURNING
    so two concurrent reset attempts with the same token can't both succeed."""
    result = await db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.token == token,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > datetime.now(UTC),
        )
        .values(used_at=datetime.now(UTC))
        .returning(PasswordResetToken.user_id)
    )
    user_id = result.scalar_one_or_none()
    await db.commit()
    return user_id
