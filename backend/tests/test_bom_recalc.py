"""Recalculation and diff against the dev database."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import BOM, User

client = TestClient(app)


def _login(email: str, password: str) -> dict:
    r = client.post("/api/auth/login", data={"username": email, "password": password})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def admin():
    return _login("admin@example.com", "admin-dev-pass")


@pytest.fixture(scope="module")
def h():
    db = SessionLocal()
    ok = db.scalar(select(User).where(User.email == "ali.hassan@example.com")) is not None
    db.close()
    if not ok:
        pytest.skip("dev users missing")
    r = client.post("/api/auth/login", data={"username": "ali.hassan@example.com", "password": "ali-dev-pass"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_recalculate_preview_and_save(h, admin):
    import time

    new_rate = 800 + (int(time.time()) % 1000) / 10  # unique per run so the saved BOM is always stale afterwards
    o = client.get("/api/orders?q=BS-ET-16765", headers=h).json()[0]
    params = {"Crunched_Area_SS_ft2": 1, "LOC_of_SS_Ft": 6, "Returns_SS_in": 1, "Surface_Area": 2, "Number_of_Connections": 2}
    saved = client.post("/api/boms", json={"order_id": o["id"], "parameters": params, "extras": [{"name": "Hanging kit", "qty": 1, "unit_cost": 500, "cost_tag": "Misc"}]}, headers=h).json()
    # a brand-new supplier rate for SS Metal 14g makes the saved BOM stale
    m = client.get("/api/materials?q=SS Metal 14g", headers=h).json()[0]
    sup = client.get("/api/suppliers?q=khizer", headers=h).json()[0]
    assert client.post(f"/api/materials/{m['id']}/rates", json={"source": "supplier", "rate": new_rate, "supplier_id": sup["id"]}, headers=h).status_code == 201
    assert client.put("/api/rate-policies", json={"scope": "material", "scope_id": m["id"], "preferred_source": "supplier", "fallback_order": ["bom"], "supplier_rule": "latest"}, headers=admin).status_code in (200, 201)

    rc = client.get(f"/api/boms/{saved['id']}/rate-changes", headers=h).json()
    assert any(c["line"] == "SS Metal 14g" and c["current"] == new_rate for c in rc["changed_lines"])

    r = client.post(f"/api/boms/{saved['id']}/recalculate?use_published_template=false", headers=h).json()
    d = r["diff"]
    assert not d["template_changed"]
    assert any(c["line"].startswith("SS Metal 14g") and c["rate"][1] == new_rate for c in d["changed"])
    assert d["delta_pkr"] == pytest.approx(round(r["preview"]["grand_total_pkr"] - saved["grand_total_pkr"], 2))
    assert any(ln["material_name"] == "Hanging kit" for ln in r["preview"]["lines"])  # extras carried over

    new = client.post(f"/api/boms/{saved['id']}/recalculate/save?use_published_template=false", headers=h)
    assert new.status_code == 201 and new.json()["version"] == saved["version"] + 1
    diff = client.get(f"/api/boms/{saved['id']}/diff/{new.json()['id']}", headers=h).json()
    assert diff["grand_total"][1] == new.json()["grand_total_pkr"]

    # viewer may read diffs but not recalc-save
    vh = {"Authorization": "Bearer " + client.post("/api/auth/login", data={"username": "viewer@example.com", "password": "viewer-dev-pass"}).json()["access_token"]}
    assert client.get(f"/api/boms/{saved['id']}/rate-changes", headers=vh).status_code == 200
    assert client.post(f"/api/boms/{saved['id']}/recalculate/save", headers=vh).status_code == 403
    # tidy the policy
    client.put("/api/rate-policies", json={"scope": "material", "scope_id": m["id"], "preferred_source": "bom", "fallback_order": ["iflow:BS", "iflow:NS"], "supplier_rule": "latest"}, headers=h)
