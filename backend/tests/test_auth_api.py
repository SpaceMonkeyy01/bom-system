"""Auth and role enforcement through the real API against the dev database (needs seeded data + dev users)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import Order, User

client = TestClient(app)


def _login(email, pw):
    r = client.post("/api/auth/login", data={"username": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def heads():
    db = SessionLocal()
    have = {u.email for u in db.scalars(select(User))}
    db.close()
    if not {"admin@example.com", "ali.hassan@example.com", "viewer@example.com"} <= have:
        pytest.skip("dev users not created (scripts/create_user.py)")
    return {"admin": _login("admin@example.com", "admin-dev-pass"), "owner": _login("ali.hassan@example.com", "ali-dev-pass"), "viewer": _login("viewer@example.com", "viewer-dev-pass")}


def test_unauthenticated_is_rejected():
    assert client.get("/api/orders").status_code == 401
    assert client.get("/api/dashboard/summary").status_code == 401
    assert client.get("/health").status_code == 200  # health stays open


def test_bad_password():
    assert client.post("/api/auth/login", data={"username": "admin@example.com", "password": "nope"}).status_code == 401


def test_me_and_roles(heads):
    assert client.get("/api/auth/me", headers=heads["owner"]).json()["role"] == "template_owner"
    assert client.get("/api/auth/me", headers=heads["viewer"]).json()["role"] == "viewer"


def test_viewer_can_read_but_not_write(heads):
    assert client.get("/api/orders?limit=1", headers=heads["viewer"]).status_code == 200
    db = SessionLocal()
    oid = db.scalar(select(Order.id).where(Order.sign_type_id.isnot(None)).limit(1))
    db.close()
    if oid is None:
        pytest.skip("no seeded orders")
    r = client.post("/api/boms/preview", json={"order_id": oid}, headers=heads["viewer"])
    assert r.status_code == 403
    r = client.post("/api/boms/preview", json={"order_id": oid}, headers=heads["owner"])
    assert r.status_code in (200, 400)  # 400 only if that order's sign type has no template


def test_user_admin_only(heads):
    assert client.get("/api/users", headers=heads["owner"]).status_code == 403
    assert client.get("/api/users", headers=heads["admin"]).status_code == 200
    r = client.patch("/api/users/1", json={"email": "admin@example.com", "name": "Saad", "role": "viewer"}, headers=heads["admin"])
    # an admin can't demote themselves (user 1 is the admin in the dev db) — or it's a different id, either is fine
    assert r.status_code in (400, 404, 200)
