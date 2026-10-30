from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import User
from app.models.core import Role
from app.services.auth import authenticate, current_user, hash_password, issue_token, require

router = APIRouter()


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    name: str
    role: Role
    active: bool
    last_login_at: datetime | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserIn(BaseModel):
    email: EmailStr
    name: str
    role: Role = Role.viewer
    password: str | None = None
    active: bool = True


class PasswordIn(BaseModel):
    current_password: str | None = None
    new_password: str


@router.post("/auth/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_session)):
    user = authenticate(db, form.username, form.password)
    if not user:
        raise HTTPException(401, "Wrong email or password")
    return TokenOut(access_token=issue_token(user), user=UserOut.model_validate(user))


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.post("/auth/password", status_code=204)
def change_password(body: PasswordIn, user: User = Depends(current_user), db: Session = Depends(get_session)):
    from app.services.auth import verify_password

    if user.password_hash and not verify_password(body.current_password or "", user.password_hash):
        raise HTTPException(400, "Current password is wrong")
    if len(body.new_password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters")
    user.password_hash = hash_password(body.new_password)
    db.commit()


@router.get("/users", response_model=list[UserOut])
def list_users(_: User = Depends(require("users:write")), db: Session = Depends(get_session)):
    return list(db.scalars(select(User).order_by(User.name)))


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserIn, _: User = Depends(require("users:write")), db: Session = Depends(get_session)):
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(409, "A user with that email already exists")
    u = User(email=body.email.lower(), name=body.name, role=body.role, active=body.active, password_hash=hash_password(body.password) if body.password else None)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserIn, actor: User = Depends(require("users:write")), db: Session = Depends(get_session)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if u.id == actor.id and (body.role != Role.admin or not body.active):
        raise HTTPException(400, "You can't remove your own admin access")
    u.email, u.name, u.role, u.active = body.email.lower(), body.name, body.role, body.active
    if body.password:
        u.password_hash = hash_password(body.password)
    db.commit()
    db.refresh(u)
    return u
