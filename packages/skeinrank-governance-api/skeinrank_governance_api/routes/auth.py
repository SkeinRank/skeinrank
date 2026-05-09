"""Local auth, users, and role management endpoints."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from skeinrank_governance.models import (
    USER_ROLES,
    GovernanceApiToken,
    GovernanceAuthToken,
    GovernanceServiceAccount,
    GovernanceUser,
    normalize_profile_name,
    utc_now,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import (
    AuthContext,
    create_access_token,
    create_personal_api_token,
    create_service_account_api_token,
    get_current_user,
    hash_password,
    normalize_username,
    require_roles,
    verify_password,
)
from ..config import GovernanceApiConfig
from ..dependencies import get_session
from ..schemas import (
    ApiTokenCreateRequest,
    ApiTokenCreateResponse,
    ApiTokenResponse,
    AuthTokenResponse,
    LoginRequest,
    ServiceAccountCreateRequest,
    ServiceAccountResponse,
    ServiceAccountUpdateRequest,
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


@router.get("/api-tokens", response_model=list[ApiTokenResponse])
def list_personal_api_tokens(
    current_user: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[ApiTokenResponse]:
    """List masked personal API tokens for the current user."""

    if current_user.id <= 0:
        return []
    tokens = list(
        session.scalars(
            select(GovernanceApiToken)
            .where(GovernanceApiToken.user_id == current_user.id)
            .order_by(GovernanceApiToken.created_at.desc())
        )
    )
    return [_api_token_response(token) for token in tokens]


@router.post(
    "/api-tokens",
    response_model=ApiTokenCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_personal_token(
    request: ApiTokenCreateRequest,
    current_user: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ApiTokenCreateResponse:
    """Create a personal API token for the current human user."""

    if current_user.id <= 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Local development users cannot create persisted API tokens.",
        )
    user = session.get(GovernanceUser, current_user.id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Current user no longer exists.",
        )
    expires_at = _expires_at_from_days(request.expires_in_days)
    plain_token, token = create_personal_api_token(
        session,
        user,
        name=request.name,
        scopes=request.scopes,
        expires_at=expires_at,
        created_by=current_user.username,
    )
    session.commit()
    session.refresh(token)
    return _api_token_create_response(token, plain_token)


@router.delete("/api-tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_personal_api_token(
    token_id: int,
    current_user: AuthContext = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    """Revoke one personal API token owned by the current user."""

    token = session.get(GovernanceApiToken, token_id)
    if token is None or token.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API token not found: {token_id}",
        )
    token.revoked_at = utc_now()
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/service-accounts",
    response_model=list[ServiceAccountResponse],
)
def list_service_accounts(
    _admin: AuthContext = Depends(require_roles("admin")),
    session: Session = Depends(get_session),
) -> list[ServiceAccountResponse]:
    """List service accounts. Admin role required."""

    accounts = list(
        session.scalars(
            select(GovernanceServiceAccount).order_by(
                GovernanceServiceAccount.normalized_name
            )
        )
    )
    return [_service_account_response(account) for account in accounts]


@router.post(
    "/service-accounts",
    response_model=ServiceAccountResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_service_account(
    request: ServiceAccountCreateRequest,
    current_user: AuthContext = Depends(require_roles("admin")),
    session: Session = Depends(get_session),
) -> ServiceAccountResponse:
    """Create a non-human service account. Admin role required."""

    _validate_role(request.role)
    existing = session.scalar(
        select(GovernanceServiceAccount).where(
            GovernanceServiceAccount.normalized_name
            == normalize_profile_name(request.name)
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Service account already exists: {request.name}",
        )
    service_account = GovernanceServiceAccount(
        name=request.name,
        display_name=request.display_name,
        description=request.description,
        role=request.role,
        is_active=request.is_active,
        created_by=current_user.username,
    )
    session.add(service_account)
    try:
        session.commit()
        session.refresh(service_account)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Service account already exists: {request.name}",
        ) from exc
    return _service_account_response(service_account)


@router.patch(
    "/service-accounts/{account_name}",
    response_model=ServiceAccountResponse,
)
def update_service_account(
    account_name: str,
    request: ServiceAccountUpdateRequest,
    _admin: AuthContext = Depends(require_roles("admin")),
    session: Session = Depends(get_session),
) -> ServiceAccountResponse:
    """Update a service account. Admin role required."""

    service_account = _get_service_account_or_404(session, account_name)
    fields = request.model_fields_set
    if "role" in fields and request.role is not None:
        _validate_role(request.role)
        service_account.role = request.role
    if "name" in fields and request.name is not None:
        normalized = normalize_profile_name(request.name)
        existing = session.scalar(
            select(GovernanceServiceAccount).where(
                GovernanceServiceAccount.normalized_name == normalized,
                GovernanceServiceAccount.id != service_account.id,
            )
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Service account already exists: {request.name}",
            )
        service_account.name = request.name
    if "display_name" in fields:
        service_account.display_name = request.display_name
    if "description" in fields:
        service_account.description = request.description
    if "is_active" in fields and request.is_active is not None:
        service_account.is_active = request.is_active
        if not request.is_active:
            _revoke_service_account_tokens(session, service_account.id)
    session.commit()
    session.refresh(service_account)
    return _service_account_response(service_account)


@router.delete(
    "/service-accounts/{account_name}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_service_account(
    account_name: str,
    _admin: AuthContext = Depends(require_roles("admin")),
    session: Session = Depends(get_session),
) -> Response:
    """Delete a service account and cascade its tokens. Admin role required."""

    service_account = _get_service_account_or_404(session, account_name)
    session.delete(service_account)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/service-accounts/{account_name}/tokens",
    response_model=list[ApiTokenResponse],
)
def list_service_account_tokens(
    account_name: str,
    _admin: AuthContext = Depends(require_roles("admin")),
    session: Session = Depends(get_session),
) -> list[ApiTokenResponse]:
    """List masked tokens for a service account. Admin role required."""

    service_account = _get_service_account_or_404(session, account_name)
    tokens = list(
        session.scalars(
            select(GovernanceApiToken)
            .where(GovernanceApiToken.service_account_id == service_account.id)
            .order_by(GovernanceApiToken.created_at.desc())
        )
    )
    return [_api_token_response(token) for token in tokens]


@router.post(
    "/service-accounts/{account_name}/tokens",
    response_model=ApiTokenCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_service_account_token(
    account_name: str,
    request: ApiTokenCreateRequest,
    current_user: AuthContext = Depends(require_roles("admin")),
    session: Session = Depends(get_session),
) -> ApiTokenCreateResponse:
    """Create a copy-once bearer token for a service account."""

    service_account = _get_service_account_or_404(session, account_name)
    if not service_account.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Service account is disabled: {account_name}",
        )
    plain_token, token = create_service_account_api_token(
        session,
        service_account,
        name=request.name,
        scopes=request.scopes,
        expires_at=_expires_at_from_days(request.expires_in_days),
        created_by=current_user.username,
    )
    session.commit()
    session.refresh(token)
    return _api_token_create_response(token, plain_token)


@router.delete(
    "/service-accounts/{account_name}/tokens/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_service_account_token(
    account_name: str,
    token_id: int,
    _admin: AuthContext = Depends(require_roles("admin")),
    session: Session = Depends(get_session),
) -> Response:
    """Revoke one service account token. Admin role required."""

    service_account = _get_service_account_or_404(session, account_name)
    token = session.get(GovernanceApiToken, token_id)
    if token is None or token.service_account_id != service_account.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API token not found: {token_id}",
        )
    token.revoked_at = utc_now()
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


def _service_account_response(
    service_account: GovernanceServiceAccount,
) -> ServiceAccountResponse:
    return ServiceAccountResponse(
        id=service_account.id,
        name=service_account.name,
        normalized_name=service_account.normalized_name,
        display_name=service_account.display_name,
        description=service_account.description,
        role=service_account.role,
        is_active=service_account.is_active,
        created_by=service_account.created_by,
        last_used_at=service_account.last_used_at,
        created_at=service_account.created_at,
        updated_at=service_account.updated_at,
    )


def _api_token_response(token: GovernanceApiToken) -> ApiTokenResponse:
    owner_type, owner_name = _api_token_owner(token)
    return ApiTokenResponse(
        id=token.id,
        name=token.name,
        token_prefix=token.token_prefix,
        scopes=list(token.scopes or []),
        owner_type=owner_type,
        owner_name=owner_name,
        expires_at=token.expires_at,
        revoked_at=token.revoked_at,
        last_used_at=token.last_used_at,
        created_by=token.created_by,
        created_at=token.created_at,
        updated_at=token.updated_at,
    )


def _api_token_create_response(
    token: GovernanceApiToken, plain_token: str
) -> ApiTokenCreateResponse:
    base = _api_token_response(token).model_dump()
    return ApiTokenCreateResponse(**base, access_token=plain_token)


def _api_token_owner(token: GovernanceApiToken) -> tuple[str, str]:
    if token.user is not None:
        return "personal", token.user.username
    if token.service_account is not None:
        return "service_account", token.service_account.name
    return "unknown", "unknown"


def _get_service_account_or_404(
    session: Session, account_name: str
) -> GovernanceServiceAccount:
    service_account = session.scalar(
        select(GovernanceServiceAccount).where(
            GovernanceServiceAccount.normalized_name
            == normalize_profile_name(account_name)
        )
    )
    if service_account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service account not found: {account_name}",
        )
    return service_account


def _revoke_service_account_tokens(session: Session, service_account_id: int) -> None:
    now = utc_now()
    tokens = list(
        session.scalars(
            select(GovernanceApiToken).where(
                GovernanceApiToken.service_account_id == service_account_id,
                GovernanceApiToken.revoked_at.is_(None),
            )
        )
    )
    for token in tokens:
        token.revoked_at = now


def _expires_at_from_days(expires_in_days: int | None):
    if expires_in_days is None:
        return None
    return utc_now() + timedelta(days=expires_in_days)


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
    login_tokens = list(
        session.scalars(
            select(GovernanceAuthToken).where(
                GovernanceAuthToken.user_id == user_id,
                GovernanceAuthToken.revoked_at.is_(None),
            )
        )
    )
    api_tokens = list(
        session.scalars(
            select(GovernanceApiToken).where(
                GovernanceApiToken.user_id == user_id,
                GovernanceApiToken.revoked_at.is_(None),
            )
        )
    )
    for token in [*login_tokens, *api_tokens]:
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
