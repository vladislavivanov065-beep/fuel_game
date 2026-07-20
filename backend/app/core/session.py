import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.session import Session

settings = get_settings()


async def create_session(db: AsyncSession, user_id: uuid.UUID) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.session_ttl_seconds)
    db.add(Session(token=token, user_id=user_id, expires_at=expires_at))
    await db.commit()
    return token


async def get_session_user_id(db: AsyncSession, token: str) -> uuid.UUID | None:
    result = await db.execute(select(Session).where(Session.token == token))
    session = result.scalar_one_or_none()
    if session is None:
        return None
    if session.expires_at < datetime.now(UTC):
        return None
    return session.user_id


async def delete_session(db: AsyncSession, token: str) -> None:
    await db.execute(delete(Session).where(Session.token == token))
    await db.commit()


async def delete_all_sessions_for_user(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(delete(Session).where(Session.user_id == user_id))
    await db.commit()
