from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_current_user
from app.core.config import get_settings
from app.core.rate_limit import AuthRateLimiter
from app.db.models.user import User
from app.db.session import get_db_session
from app.schemas.auth import LoginRequest, RegisterRequest, UserResponse
from app.services import auth_service

settings = get_settings()

router = APIRouter(prefix="/api/auth", tags=["auth"])

_register_rate_limiter = AuthRateLimiter("register")
_login_rate_limiter = AuthRateLimiter("login")


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        secure=settings.session_cookie_secure,
        # Browsers reject SameSite=None without Secure, and frontend/backend
        # sit on different subdomains in production, so a cross-site fetch
        # would never carry a Lax cookie back — tie the two together instead
        # of hardcoding "lax", which broke sessions on split-domain deploys.
        samesite="none" if settings.session_cookie_secure else "lax",
        max_age=settings.session_ttl_seconds,
        path="/",
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_register_rate_limiter)],
)
async def register(
    data: RegisterRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
    try:
        user, token = await auth_service.register_user(db, data)
    except auth_service.EmailAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        ) from exc

    _set_session_cookie(response, token)
    return user


@router.post(
    "/login",
    response_model=UserResponse,
    dependencies=[Depends(_login_rate_limiter)],
)
async def login(
    data: LoginRequest,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
    try:
        user, token = await auth_service.login_user(db, data)
    except auth_service.InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        ) from exc

    _set_session_cookie(response, token)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    session_id: Annotated[str | None, Cookie(alias=settings.session_cookie_name)] = None,
) -> None:
    if session_id is not None:
        await auth_service.logout_user(db, session_id)
    response.delete_cookie(key=settings.session_cookie_name, path="/")


@router.get("/me", response_model=UserResponse)
async def me(user: Annotated[User, Depends(require_current_user)]) -> User:
    return user
