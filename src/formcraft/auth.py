# Formcraft by catapultaiwork — https://catapultaiwork.com
# Source-available with required attribution; see LICENSE.
# Personal and commercial use is allowed. Every hosted form must retain the small
# "Powered by catapultaiwork" link. There is no builder setting to hide it.
# People controlling the source can edit it, but the license requires this credit.
# This is a custom attribution license, not standard MIT or OSI-approved open source.

"""Single-admin authentication.

There is exactly one account. Credentials live in the environment, not the
database, so there is no signup path and no way to create a second admin.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import settings

SESSION_COOKIE = "formcraft_session"
SESSION_MAX_AGE = 60 * 60 * 12  # 12 hours

_hasher = PasswordHasher()

# Login throttle: per-process, which is all a single-admin app needs.
_attempts: list[float] = []
_MAX_ATTEMPTS = 8
_WINDOW_SECONDS = 300


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def _serializer() -> URLSafeTimedSerializer:
    if not settings.secret_key:
        raise RuntimeError(
            "FORMCRAFT_SECRET_KEY is not set. Copy .env.example to .env and fill it in."
        )
    return URLSafeTimedSerializer(settings.secret_key, salt="formcraft-session")


def throttled() -> bool:
    now = time.time()
    _attempts[:] = [t for t in _attempts if now - t < _WINDOW_SECONDS]
    return len(_attempts) >= _MAX_ATTEMPTS


def record_failure() -> None:
    _attempts.append(time.time())


def clear_failures() -> None:
    _attempts.clear()


def verify_credentials(username: str, password: str) -> bool:
    """Constant-time-ish check of the single admin credential pair."""
    if not settings.admin_password_hash and not settings.admin_password:
        raise RuntimeError(
            "No admin password configured. Run: uv run python scripts/set_password.py"
        )
    username_ok = hmac.compare_digest(
        username.strip().encode(), settings.admin_username.encode()
    )
    if not settings.admin_password_hash:
        password_ok = hmac.compare_digest(
            password.encode(), settings.admin_password.encode()
        )
        return username_ok and password_ok
    try:
        _hasher.verify(settings.admin_password_hash, password)
    except (VerifyMismatchError, Exception):  # noqa: B014 - argon2 raises several
        return False
    return username_ok


def _credential_version() -> str:
    return hashlib.sha256(
        (settings.admin_password_hash or settings.admin_password).encode()
    ).hexdigest()


def issue_session() -> str:
    return _serializer().dumps(
        {
            "sub": settings.admin_username,
            "sid": secrets.token_urlsafe(24),
            "credential": _credential_version(),
        }
    )


def read_session(request: Request) -> bool:
    # A public-role instance has no signing key and therefore no sessions.
    if not settings.secret_key:
        return False
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return False
    try:
        data = _serializer().loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return False
    return (
        isinstance(data, dict)
        and data.get("sub") == settings.admin_username
        and data.get("credential") == _credential_version()
    )


def require_admin(request: Request) -> None:
    """FastAPI dependency guarding every admin route."""
    if not read_session(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin login required"
        )
