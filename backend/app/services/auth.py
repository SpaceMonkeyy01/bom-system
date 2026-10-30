"""Password hashing, JWT issue/verify, and the FastAPI dependencies that enforce roles."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.models import User
from app.models.core import Role

_ph = PasswordHasher()
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

# Which roles may do what. admin can do everything.
PERMISSIONS: dict[str, set[Role]] = {
    "bom:write": {Role.admin, Role.template_owner, Role.bom_editor},
    "template:write": {Role.admin, Role.template_owner},
    "inventory:write": {Role.admin, Role.inventory_manager, Role.template_owner},
    "rates:write": {Role.admin, Role.inventory_manager, Role.template_owner},
    "users:write": {Role.admin},
    "settings:write": {Role.admin},
    "read": set(Role),
}


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, pw_hash: str | None) -> bool:
    if not pw_hash:
        return False
    try:
        return _ph.verify(pw_hash, pw)
    except VerifyMismatchError:
        return False


def issue_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user.id), "email": user.email, "role": user.role.value, "iat": now, "exp": now + timedelta(hours=settings.jwt_ttl_hours)}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if not user or not user.active or not verify_password(password, user.password_hash):
        return None
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return user


def current_user(token: str | None = Depends(oauth2), db: Session = Depends(get_session)) -> User:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in", headers={"WWW-Authenticate": "Bearer"})
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired, sign in again")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    user = db.get(User, int(data["sub"]))
    if not user or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account is disabled")
    return user


def require(permission: str):
    """Dependency factory: `Depends(require("bom:write"))`."""
    allowed = PERMISSIONS[permission]

    def _check(user: User = Depends(current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Your role ({user.role.value}) can't do this")
        return user

    return _check


def bootstrap_admin(db: Session) -> User | None:
    """Create the first admin from env settings when the users table is empty."""
    if db.scalar(select(User.id).limit(1)) is not None:
        return None
    if not (settings.bootstrap_admin_email and settings.bootstrap_admin_password):
        return None
    u = User(email=settings.bootstrap_admin_email.lower(), name="Admin", role=Role.admin, password_hash=hash_password(settings.bootstrap_admin_password))
    db.add(u)
    db.commit()
    return u
