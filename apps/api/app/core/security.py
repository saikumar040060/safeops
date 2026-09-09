"""Authentication and RBAC.

Bearer API tokens, not JWT or cookie sessions: a random high-entropy token
is generated once, shown to the operator exactly once, and only its SHA-256
hash is ever persisted (plain hashlib is fine here -- unlike a password,
these tokens are never user-chosen and never low-entropy, so there is no
offline-guessing risk a slow KDF like bcrypt/argon2 would defend against).

There is no unauthenticated fallback anywhere, including demo mode: demo
mode only controls whether well-known demo operator accounts get seeded and
whether the frontend shows a banner (see app/core/seed.py and
app/core/config.py). Every protected endpoint always requires a valid
bearer token that resolves to an active Operator.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import get_db
from app.models import Operator, OperatorToken
from app.models.enums import OperatorRole

TOKEN_PREFIX = "sfops_"

# ADMIN deliberately holds the union of every other role's permissions
# rather than being special-cased in the check itself -- one code path
# (`permission in ROLE_PERMISSIONS[role]`) covers every role.
ROLE_PERMISSIONS: dict[OperatorRole, set[str]] = {
    OperatorRole.VIEWER: {"read"},
    OperatorRole.OPERATOR: {"read", "execute"},
    OperatorRole.APPROVER: {"read", "approve"},
    OperatorRole.ADMIN: {"read", "execute", "approve"},
}


def generate_token() -> str:
    return f"{TOKEN_PREFIX}{secrets.token_urlsafe(32)}"


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def issue_token(
    operator: Operator, *, expires_at: datetime | None = None, raw_token: str | None = None
) -> tuple[OperatorToken, str]:
    """Creates and returns (token_row, raw_token). The caller is
    responsible for committing and for handing `raw_token` to the operator
    exactly once -- it is never recoverable afterward."""
    raw = raw_token or generate_token()
    token = OperatorToken(
        id=uuid.uuid4(), operator_id=operator.id, token_hash=hash_token(raw), expires_at=expires_at
    )
    return token, raw


def _unauthorized() -> HTTPException:
    # Deliberately one generic response for every failure mode (missing
    # header, malformed scheme, unknown/revoked/expired token, inactive
    # operator) -- never reveals which check failed.
    return HTTPException(
        status_code=401,
        detail={"code": "UNAUTHENTICATED", "message": "Authentication required."},
    )


def get_current_operator(request: Request, db: Session = Depends(get_db)) -> Operator:
    auth_header = request.headers.get("authorization")
    if not auth_header:
        raise _unauthorized()

    scheme, _, raw_token = auth_header.partition(" ")
    raw_token = raw_token.strip()
    if scheme.lower() != "bearer" or not raw_token:
        raise _unauthorized()

    token_hash = hash_token(raw_token)
    token = db.scalar(select(OperatorToken).where(OperatorToken.token_hash == token_hash))
    if token is None or token.revoked_at is not None:
        raise _unauthorized()
    if token.expires_at is not None and token.expires_at <= datetime.now(UTC):
        raise _unauthorized()

    operator = db.get(Operator, token.operator_id)
    if operator is None or not operator.is_active:
        raise _unauthorized()

    return operator


def require_permission(permission: str):
    """FastAPI dependency factory. `permission` is one of "read", "execute",
    "approve". Backend-enforced independent of anything the frontend hides
    -- this is the actual security boundary."""

    def _dependency(operator: Operator = Depends(get_current_operator)) -> Operator:
        allowed = ROLE_PERMISSIONS.get(operator.role, set())
        if permission not in allowed:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "FORBIDDEN",
                    "message": "Your role does not permit this action.",
                },
            )
        return operator

    return _dependency


def ensure_bootstrap_admin(db: Session, settings: Settings) -> None:
    """Idempotent: if no ADMIN operator exists yet and a bootstrap token is
    configured, provisions exactly one ADMIN operator/token pair from it.
    Safe to call on every startup -- a no-op once an ADMIN exists.

    Also safe under concurrent multi-worker startup: `uvicorn --workers N`
    runs N separate processes, each importing app.main and running its own
    lifespan independently, so this can race against itself. Every insert
    below is guarded by catching the resulting IntegrityError and treating
    "someone else already created it" as success rather than letting it
    crash application startup.
    """
    if not settings.bootstrap_admin_token:
        return

    existing_admin = db.scalar(
        select(Operator).where(Operator.role == OperatorRole.ADMIN, Operator.is_active.is_(True))
    )
    if existing_admin is not None:
        return

    operator = db.scalar(
        select(Operator).where(Operator.username == settings.bootstrap_admin_username)
    )
    if operator is None:
        operator = Operator(
            username=settings.bootstrap_admin_username,
            display_name="Bootstrap Admin",
            role=OperatorRole.ADMIN,
            is_active=True,
        )
        db.add(operator)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            operator = db.scalar(
                select(Operator).where(Operator.username == settings.bootstrap_admin_username)
            )
            if operator is None:
                raise
    else:
        operator.role = OperatorRole.ADMIN
        operator.is_active = True

    token_hash = hash_token(settings.bootstrap_admin_token)
    if db.scalar(select(OperatorToken).where(OperatorToken.token_hash == token_hash)) is not None:
        db.commit()
        return

    token, _ = issue_token(operator, raw_token=settings.bootstrap_admin_token)
    db.add(token)
    try:
        db.commit()
    except IntegrityError:
        # Another worker's token insert won the race between our check
        # above and this commit -- the token already exists either way.
        db.rollback()
