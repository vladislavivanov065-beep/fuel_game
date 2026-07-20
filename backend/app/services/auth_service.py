from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.password_reset import consume_reset_token, create_reset_token
from app.core.security import hash_password, verify_password
from app.core.session import (
    create_session,
    delete_all_sessions_for_user,
    delete_session,
    get_session_user_id,
)
from app.db.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest


class EmailAlreadyExistsError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class PasswordResetTokenInvalidError(Exception):
    pass


async def register_user(db: AsyncSession, data: RegisterRequest) -> tuple[User, str]:
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        display_name=data.display_name,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise EmailAlreadyExistsError from exc
    await db.refresh(user)

    session_token = await create_session(db, user.id)
    return user, session_token


async def login_user(db: AsyncSession, data: LoginRequest) -> tuple[User, str]:
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(data.password, user.password_hash):
        raise InvalidCredentialsError

    session_token = await create_session(db, user.id)
    return user, session_token


async def logout_user(db: AsyncSession, session_token: str) -> None:
    await delete_session(db, session_token)


async def get_current_user(db: AsyncSession, session_token: str | None) -> User | None:
    if session_token is None:
        return None

    user_id = await get_session_user_id(db, session_token)
    if user_id is None:
        return None

    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def request_password_reset(db: AsyncSession, email: str) -> tuple[User, str] | None:
    """Looks up the user by email; if found, issues a reset token. Returns
    None if no account matches — callers must not let that distinction leak
    into an inconsistent HTTP status, only into the optional token field of
    the response body (see Этап 15 known limitation about email enumeration)."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        return None

    token = await create_reset_token(db, user.id)
    return user, token


async def reset_password(db: AsyncSession, token: str, new_password: str) -> User:
    user_id = await consume_reset_token(db, token)
    if user_id is None:
        raise PasswordResetTokenInvalidError

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()
    user.password_hash = hash_password(new_password)
    await db.commit()
    await db.refresh(user)

    await delete_all_sessions_for_user(db, user.id)
    return user
