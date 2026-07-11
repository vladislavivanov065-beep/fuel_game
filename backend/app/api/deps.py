from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.user import User
from app.db.session import get_db_session
from app.services.auth_service import get_current_user

settings = get_settings()


async def get_optional_current_user(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    session_id: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None,
) -> User | None:
    return await get_current_user(db, session_id)


async def require_current_user(
    user: Annotated[User | None, Depends(get_optional_current_user)],
) -> User:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user
