"""Authentication and role helpers for the governance API."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException, Request, status
from skeinrank_governance.models import (
    USER_ROLES,
    USER_STATUSES,
    GovernanceApiToken,
    GovernanceAuthToken,
    GovernanceServiceAccount,
    GovernanceUser,
    normalize_profile_name,
    utc_now,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .config import GovernanceApiConfig
from .dependencies import get_session

PASSWORD_SCHEME = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 260_000
DEV_USERNAME = "local_dev"
DEV_ROLE = "admin"


@dataclass(frozen=True)
class AuthContext:
    """Authenticated user context returned by API dependencies."""

    id: int
    username: str
    display_name: str | None
    role: str
    status: str
    is_active: bool
    token_hash: str | None = None
    scopes: frozenset[str] | None = None
    auth_type: str = "session"
    service_account_id: int | None = None


def hash_password(password: str) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256 with a random salt."""

    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return "$".join(
        (
            PASSWORD_SCHEME,
            str(PASSWORD_ITERATIONS),
            _b64encode(salt),
            _b64encode(digest),
        )
    )


def verify_password(password: str, password_hash: str) -> bool:
    """Return true when the password matches the stored password hash."""

    try:
        scheme, iterations_raw, salt_raw, digest_raw = password_hash.split("$", 3)
        if scheme != PASSWORD_SCHEME:
            return False
        iterations = int(iterations_raw)
        salt = _b64decode(salt_raw)
        expected_digest = _b64decode(digest_raw)
    except (ValueError, TypeError):
        return False

    actual_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual_digest, expected_digest)


def create_plain_token() -> str:
    """Create a bearer token suitable for returning to the caller once."""

    return secrets.token_urlsafe(32)


def create_plain_api_token(*, service_account: bool = False) -> str:
    """Create a copy-once API token with a readable token family prefix."""

    prefix = "sk_sat" if service_account else "sk_pat"
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def hash_token(token: str) -> str:
    """Hash a bearer token for database storage."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def bootstrap_admin_if_needed(
    session_factory: sessionmaker[Session],
    config: GovernanceApiConfig,
) -> None:
    """Create the first admin user when explicit bootstrap config is enabled."""

    if not config.bootstrap_admin:
        return
    if not config.admin_password:
        raise RuntimeError(
            "SKEINRANK_GOVERNANCE_API_BOOTSTRAP_ADMIN requires "
            "SKEINRANK_GOVERNANCE_API_ADMIN_PASSWORD"
        )

    with session_factory() as session:
        existing_count = session.scalar(select(GovernanceUser.id).limit(1))
        if existing_count is not None:
            return
        admin = GovernanceUser(
            username=config.admin_username,
            display_name=config.admin_display_name,
            password_hash=hash_password(config.admin_password),
            role="admin",
            status="active",
            is_active=True,
        )
        session.add(admin)
        session.commit()


def create_access_token(
    session: Session,
    user: GovernanceUser,
    *,
    ttl_hours: int,
    user_agent: str | None = None,
) -> tuple[str, GovernanceAuthToken]:
    """Create and persist an auth token for a user."""

    token = create_plain_token()
    token_model = GovernanceAuthToken(
        user_id=user.id,
        token_hash=hash_token(token),
        token_prefix=token[:12],
        expires_at=utc_now() + timedelta(hours=ttl_hours),
        user_agent=user_agent,
    )
    user.last_login_at = utc_now()
    session.add(token_model)
    return token, token_model


def create_personal_api_token(
    session: Session,
    user: GovernanceUser,
    *,
    name: str,
    scopes: list[str],
    expires_at: datetime | None,
    created_by: str | None,
) -> tuple[str, GovernanceApiToken]:
    """Create and persist a personal API token for a user."""

    token = create_plain_api_token(service_account=False)
    token_model = GovernanceApiToken(
        user_id=user.id,
        name=name,
        token_hash=hash_token(token),
        token_prefix=_token_prefix(token),
        scopes=scopes,
        expires_at=expires_at,
        created_by=created_by,
    )
    session.add(token_model)
    return token, token_model


def create_service_account_api_token(
    session: Session,
    service_account: GovernanceServiceAccount,
    *,
    name: str,
    scopes: list[str],
    expires_at: datetime | None,
    created_by: str | None,
) -> tuple[str, GovernanceApiToken]:
    """Create and persist an API token for a service account."""

    token = create_plain_api_token(service_account=True)
    token_model = GovernanceApiToken(
        service_account_id=service_account.id,
        name=name,
        token_hash=hash_token(token),
        token_prefix=_token_prefix(token),
        scopes=scopes,
        expires_at=expires_at,
        created_by=created_by,
    )
    session.add(token_model)
    return token, token_model


def get_current_user(
    request: Request,
    session: Session = Depends(get_session),
    authorization: str | None = Header(default=None),
) -> AuthContext:
    """Return the authenticated user, or a local-dev admin when auth is disabled."""

    config: GovernanceApiConfig = request.app.state.config
    if not config.auth_enabled:
        return AuthContext(
            id=0,
            username=DEV_USERNAME,
            display_name="Local development",
            role=DEV_ROLE,
            status="active",
            is_active=True,
        )

    token = _extract_bearer_token(authorization)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_hash = hash_token(token)
    now = utc_now()
    auth_token = session.scalar(
        select(GovernanceAuthToken)
        .join(GovernanceAuthToken.user)
        .where(
            GovernanceAuthToken.token_hash == token_hash,
            GovernanceAuthToken.revoked_at.is_(None),
            GovernanceAuthToken.expires_at > now,
        )
    )
    if auth_token is not None and user_can_auth(auth_token.user):
        return AuthContext(
            id=auth_token.user.id,
            username=auth_token.user.username,
            display_name=auth_token.user.display_name,
            role=auth_token.user.role,
            status=auth_token.user.status,
            is_active=auth_token.user.is_active,
            token_hash=token_hash,
            scopes=None,
            auth_type="session",
        )

    api_token = session.scalar(
        select(GovernanceApiToken)
        .outerjoin(GovernanceApiToken.user)
        .outerjoin(GovernanceApiToken.service_account)
        .where(
            GovernanceApiToken.token_hash == token_hash,
            GovernanceApiToken.revoked_at.is_(None),
        )
    )
    if api_token is not None and _not_expired(api_token.expires_at, now):
        if api_token.user is not None and user_can_auth(api_token.user):
            return AuthContext(
                id=api_token.user.id,
                username=api_token.user.username,
                display_name=api_token.user.display_name,
                role=api_token.user.role,
                status=api_token.user.status,
                is_active=api_token.user.is_active,
                token_hash=token_hash,
                scopes=frozenset(api_token.scopes or []),
                auth_type="personal_token",
            )
        if (
            api_token.service_account is not None
            and api_token.service_account.is_active
        ):
            return AuthContext(
                id=0,
                username=api_token.service_account.name,
                display_name=api_token.service_account.display_name,
                role=api_token.service_account.role,
                status="active" if api_token.service_account.is_active else "suspended",
                is_active=api_token.service_account.is_active,
                token_hash=token_hash,
                scopes=frozenset(api_token.scopes or []),
                auth_type="service_account",
                service_account_id=api_token.service_account.id,
            )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired bearer token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def validate_user_status(user_status: str) -> str:
    """Validate and normalize a user account status."""

    normalized = user_status.strip().lower()
    if normalized not in USER_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid user status: {user_status}",
        )
    return normalized


def user_can_auth(user: GovernanceUser) -> bool:
    """Return true when a human user can authenticate with sessions or tokens."""

    return user.is_active and user.status == "active"


def require_scopes(*required_scopes: str) -> Callable[[AuthContext], AuthContext]:
    """Build a dependency that requires scopes for API tokens.

    Session login tokens and local-dev mode are role-only and bypass scope checks.
    Personal/service-account API tokens must carry every requested scope.
    """

    def dependency(user: AuthContext = Depends(get_current_user)) -> AuthContext:
        if user.scopes is None:
            return user
        missing_scopes = sorted(set(required_scopes) - set(user.scopes))
        if missing_scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing API token scopes: {', '.join(missing_scopes)}",
            )
        return user

    return dependency


def require_roles(*roles: str) -> Callable[[AuthContext], AuthContext]:
    """Build a dependency that requires one of the requested roles."""

    invalid_roles = sorted(set(roles) - set(USER_ROLES))
    if invalid_roles:
        raise ValueError(f"Unknown governance roles: {', '.join(invalid_roles)}")

    def dependency(user: AuthContext = Depends(get_current_user)) -> AuthContext:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role permissions",
            )
        return user

    return dependency


def _not_expired(expires_at: datetime | None, now: datetime) -> bool:
    if expires_at is None:
        return True
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > now


def _token_prefix(token: str) -> str:
    if token.startswith("sk_pat_") or token.startswith("sk_sat_"):
        parts = token.split("_", 3)
        if len(parts) == 4:
            return "_".join(parts[:3])
    return token[:12]


def _extract_bearer_token(authorization: str | None) -> str | None:
    if authorization is None:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def normalize_username(value: str) -> str:
    """Normalize usernames for uniqueness checks."""

    return normalize_profile_name(value)
