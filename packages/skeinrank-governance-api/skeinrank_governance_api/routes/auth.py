"""Local auth, users, and role management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from skeinrank_governance.models import (
    USER_ROLES,
    GovernanceAuthToken,
    GovernanceUser,
    utc_now,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import (
    AuthContext,
    create_access_token,
    get_current_user,
    hash_password,
    normalize_username,
    require_roles,
    verify_password,
)
from ..config import GovernanceApiConfig
from ..dependencies import get_session
from ..schemas import (
    AuthTokenResponse,
    LoginRequest,
    UserCreateRequest,
    UserResponse,
    UserUpdateRequest,
)

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/login", response_model=AuthTokenResponse)
def login(
    request_body: LoginRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> AuthTokenResponse:
    """Exchange username/password credentials for a bearer token."""

    config: GovernanceApiConfig = request.app.state.config
    user = session.scalar(
        select(GovernanceUser).where(
            GovernanceUser.normalized_username
            == normalize_username(request_body.username)
        )
    )
    if user is None or not user.is_active:
        raise _invalid_credentials()
    if not verify_password(request_body.password, user.password_hash):
        raise _invalid_credentials()

    token, token_model = create_access_token(
        session,
        user,
        ttl_hours=config.token_ttl_hours,
        user_agent=request.headers.get("user-agent"),
    )
    session.commit()
    session.refresh(user)
    session.refresh(token_model)
    return AuthTokenResponse(
        access_token=token,
        expires_at=token_model.expires_at,
        user=_user_response(user),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    current_user: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    """Revoke the current bearer token when auth is enabled."""

    if current_user.token_hash is not None:
        token = session.scalar(
            select(GovernanceAuthToken).where(
                GovernanceAuthToken.token_hash == current_user.token_hash,
                GovernanceAuthToken.revoked_at.is_(None),
            )
        )
        if token is not None:
            token.revoked_at = utc_now()
            session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserResponse)
def read_me(current_user: AuthContext = Depends(get_current_user)) -> UserResponse:
    """Return the current API user and role."""

    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        normalized_username=normalize_username(current_user.username),
        display_name=current_user.display_name,
        role=current_user.role,
        is_active=current_user.is_active,
    )


@router.get("/users", response_model=list[UserResponse])
def list_users(
    _admin: AuthContext = Depends(require_roles("admin")),
    session: Session = Depends(get_session),
) -> list[UserResponse]:
    """List local governance API users. Admin role required when auth is enabled."""

    users = list(
        session.scalars(
            select(GovernanceUser).order_by(GovernanceUser.normalized_username)
        )
    )
    return [_user_response(user) for user in users]


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    request: UserCreateRequest,
    _admin: AuthContext = Depends(require_roles("admin")),
    session: Session = Depends(get_session),
) -> UserResponse:
    """Create a local governance API user. Admin role required when auth is enabled."""

    _validate_role(request.role)
    existing = session.scalar(
        select(GovernanceUser).where(
            GovernanceUser.normalized_username == normalize_username(request.username)
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User already exists: {request.username}",
        )
    user = GovernanceUser(
        username=request.username,
        display_name=request.display_name,
        password_hash=hash_password(request.password),
        role=request.role,
        is_active=request.is_active,
    )
    session.add(user)
    try:
        session.commit()
        session.refresh(user)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User already exists: {request.username}",
        ) from exc
    return _user_response(user)


@router.patch("/users/{username}", response_model=UserResponse)
def update_user(
    username: str,
    request: UserUpdateRequest,
    _admin: AuthContext = Depends(require_roles("admin")),
    session: Session = Depends(get_session),
) -> UserResponse:
    """Update a local governance API user. Admin role required when auth is enabled."""

    user = _get_user_or_404(session, username)
    fields = request.model_fields_set

    if "role" in fields and request.role is not None:
        _validate_role(request.role)
        user.role = request.role
    if "username" in fields and request.username is not None:
        normalized = normalize_username(request.username)
        existing = session.scalar(
            select(GovernanceUser).where(
                GovernanceUser.normalized_username == normalized,
                GovernanceUser.id != user.id,
            )
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"User already exists: {request.username}",
            )
        user.username = request.username
    if "display_name" in fields:
        user.display_name = request.display_name
    if "password" in fields and request.password is not None:
        user.password_hash = hash_password(request.password)
        _revoke_user_tokens(session, user.id)
    if "is_active" in fields and request.is_active is not None:
        user.is_active = request.is_active
        if not request.is_active:
            _revoke_user_tokens(session, user.id)

    try:
        session.commit()
        session.refresh(user)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User update conflicts with an existing username",
        ) from exc
    return _user_response(user)


@router.delete("/users/{username}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    username: str,
    _admin: AuthContext = Depends(require_roles("admin")),
    session: Session = Depends(get_session),
) -> Response:
    """Delete a local governance API user. Admin role required when auth is enabled."""

    user = _get_user_or_404(session, username)
    session.delete(user)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _user_response(user: GovernanceUser) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        normalized_username=user.normalized_username,
        display_name=user.display_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login_at=user.last_login_at,
    )


def _get_user_or_404(session: Session, username: str) -> GovernanceUser:
    user = session.scalar(
        select(GovernanceUser).where(
            GovernanceUser.normalized_username == normalize_username(username)
        )
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User not found: {username}",
        )
    return user


def _revoke_user_tokens(session: Session, user_id: int) -> None:
    now = utc_now()
    tokens = list(
        session.scalars(
            select(GovernanceAuthToken).where(
                GovernanceAuthToken.user_id == user_id,
                GovernanceAuthToken.revoked_at.is_(None),
            )
        )
    )
    for token in tokens:
        token.revoked_at = now


def _validate_role(role: str) -> None:
    if role not in USER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid user role: {role}",
        )


def _invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid username or password",
        headers={"WWW-Authenticate": "Bearer"},
    )
