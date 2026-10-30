"""Inventory module through the API: iFlow import, review queue, rates, UOM-aware resolution."""

import csv
import io
import time

NEW_ID = str(900000 + int(time.time()) % 90000)  # unique per run so the test is rerunnable
NEW_NAME = f"Test Unmatched Thing {NEW_ID}"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import Material, StockLine, StockSnapshot, User

client = TestClient(app)


def _login(email, pw):
    r = client.post("/api/auth/login", data={"username": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def admin():
    db = SessionLocal()
    ok = db.scalar(select(User).where(User.email == "admin@example.com")) is not None
    db.close()
    if not ok:
        pytest.skip("dev users missing")
    return _login("admin@example.com", "admin-dev-pass")


def _stock_csv(rows):
    head = [
        ["Epic Crafting Unit-II", "", "MAIN STORE STOCK SUMMARY", "Date From 29/10/2026 To 29/10/2026", "User :", "Test"],
        ["Id", "Product Name", "Unit", "Op Qty", "Received", "Issued", "Balance", "Op Amt", "Dr", "Cr", "Balance"],
    ]
    buf = io.StringIO()
    csv.writer(buf).writerows(head + rows)
    return buf.getvalue().encode()


def test_import_matches_by_key_and_derives_rate(admin):
    content = _stock_csv([["483", "SS Metal 14g", "Sqft", "10", "-", "-", "10", "7800", "-", "-", "7800"], [NEW_ID, NEW_NAME, "Piece", "4", "-", "-", "4", "400", "-", "-", "400"]])
    r = client.post("/api/inventory/stock-imports", data={"store": "BS"}, files={"file": ("s.csv", content, "text/csv")}, headers=admin)
    assert r.status_code == 201, r.text
    snap = r.json()
    assert snap["snapshot_date"] == "2026-10-29" and snap["row_count"] == 2 and snap["unmatched_count"] == 1
    # the matched line produced an iFlow rate of 780 (7800/10), in the material's own unit
    m = client.get("/api/materials?q=SS Metal 14g", headers=admin).json()[0]
    rates = client.get(f"/api/materials/{m['id']}/rates", headers=admin).json()
    assert any(x["source"] == "iflow" and x["store"] == "BS" and x["rate"] == 780.0 and x["effective_from"] == "2026-10-29" for x in rates)
    # re-upload same store+date replaces, not duplicates
    r2 = client.post("/api/inventory/stock-imports", data={"store": "BS"}, files={"file": ("s.csv", content, "text/csv")}, headers=admin)
    assert r2.json()["id"] == snap["id"]


def test_review_queue_create_and_link(admin):
    q = client.get("/api/inventory/review-queue?store=BS&limit=500", headers=admin).json()
    ln = next(x for x in q if x["external_id"] == NEW_ID)
    r = client.post(f"/api/inventory/review-queue/{ln['id']}/create-material", json={}, headers=admin)
    assert r.status_code == 201
    mid = r.json()["material_id"]
    d = client.get(f"/api/materials/{mid}", headers=admin).json()
    assert d["external_keys"] == [{"system": "iflow", "store": "BS", "external_id": NEW_ID, "external_name": NEW_NAME}]
    assert d["current_rate"]["rate"] == 100.0  # 400 / 4
    assert all(x["external_id"] != NEW_ID for x in client.get("/api/inventory/review-queue?store=BS&limit=500", headers=admin).json())
    # linking the same id to another material is refused
    other = client.get("/api/materials?q=Tanka", headers=admin).json()[0]
    db = SessionLocal()
    line_id = db.scalar(select(StockLine.id).where(StockLine.external_id == NEW_ID))
    db.close()
    r = client.post(f"/api/inventory/review-queue/{line_id}/link", json={"material_id": other["id"]}, headers=admin)
    assert r.status_code == 409
    # tidy: merge the test material into itself is refused; deactivate instead
    assert client.post(f"/api/materials/{mid}/merge", json={"drop_material_id": mid}, headers=admin).status_code == 400
    client.patch(f"/api/materials/{mid}", json={"active": False, "review_status": "not_needed"}, headers=admin)


def test_supplier_rate_and_policy_and_uom_preference(admin):
    m = client.get("/api/materials?q=Nexa Hardner 922", headers=admin).json()[0]
    sup = client.get("/api/suppliers?q=khizer", headers=admin).json()[0]
    # a supplier rate in the material's unit (Quarter) ...
    r = client.post(f"/api/materials/{m['id']}/rates", json={"source": "supplier", "rate": 9999, "supplier_id": sup["id"], "note": "test"}, headers=admin)
    assert r.status_code == 201
    client.put("/api/rate-policies", json={"scope": "material", "scope_id": m["id"], "preferred_source": "supplier", "fallback_order": ["bom"], "supplier_rule": "latest"}, headers=admin)
    assert client.get(f"/api/materials/{m['id']}", headers=admin).json()["current_rate"]["rate"] == 9999
    # ... but a paint line computes grams, so the BOM must still use the per-gram bom rate, not the per-quart one
    o = client.get("/api/orders?q=BS-ET-16765", headers=admin).json()[0]
    b = client.post("/api/boms/preview", json={"order_id": o["id"], "parameters": {"Surface_Area": 2, "LOC_of_SS_Ft": 5, "Returns_SS_in": 1}}, headers=admin).json()
    hard = [ln for ln in b["lines"] if ln["material_name"].startswith("Nexa Hardner") and ln["qty_final"] > 0]
    assert hard and all(ln["uom"] == "Gram" and ln["rate_uom"] == "Gram" and ln["rate"] < 100 and not ln["warning"] for ln in hard)
    # supplier rate without supplier is refused; viewer can't post rates
    assert client.post(f"/api/materials/{m['id']}/rates", json={"source": "supplier", "rate": 1}, headers=admin).status_code == 400
    assert client.post(f"/api/materials/{m['id']}/rates", json={"rate": 1}, headers=_login("viewer@example.com", "viewer-dev-pass")).status_code == 403
    # tidy the policy so other tests see the global one
    client.put("/api/rate-policies", json={"scope": "material", "scope_id": m["id"], "preferred_source": "bom", "fallback_order": ["iflow:BS", "iflow:NS"], "supplier_rule": "latest"}, headers=admin)


def test_merge_sheet_only_material(admin):
    db = SessionLocal()
    drop = db.scalar(select(Material).where(Material.notes.like("Created from the Google Sheet%"), Material.active.is_(True)).limit(1))
    keep = db.scalar(select(Material).where(Material.name == "SS Metal 14g"))
    db.close()
    if not drop or not keep:
        pytest.skip("no sheet-only material to merge")
    before = len(client.get(f"/api/materials/{keep.id}/rates", headers=admin).json())
    r = client.post(f"/api/materials/{keep.id}/merge", json={"drop_material_id": drop.id}, headers=admin)
    assert r.status_code == 200 and r.json()["rates"] >= 1
    assert len(client.get(f"/api/materials/{keep.id}/rates", headers=admin).json()) == before + r.json()["rates"]
    d = client.get(f"/api/materials/{drop.id}", headers=admin).json()
    assert d["active"] is False and d["review_status"] == "merged"


def test_categories_and_uoms_listed(admin):
    cats = client.get("/api/categories", headers=admin).json()
    assert len(cats) >= 140 and any(c["path"] == "Paints / Paint Additives / Hardeners" for c in cats)
    assert any(u["code"] == "Gram" for u in client.get("/api/uoms", headers=admin).json())
    r = client.post("/api/categories", json={"name": "Test Child", "parent_id": cats[0]["id"]}, headers=admin)
    assert r.status_code in (201, 409)
