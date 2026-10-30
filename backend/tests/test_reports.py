"""Reports built from saved BOMs."""

import io

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import BOM, User

client = TestClient(app)


@pytest.fixture(scope="module")
def h():
    db = SessionLocal()
    ok = db.scalar(select(User).where(User.email == "viewer@example.com")) is not None
    b = db.scalar(select(BOM).where(BOM.status.in_(("saved", "written_back"))).limit(1))
    db.close()
    if not ok or not b:
        pytest.skip("dev users / saved BOMs missing")
    r = client.post("/api/auth/login", data={"username": "viewer@example.com", "password": "viewer-dev-pass"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_weekly_funds_rows_match_boms_and_flag_missing(h):
    db = SessionLocal()
    b = db.scalar(select(BOM).where(BOM.status.in_(("saved", "written_back"))).order_by(BOM.id.desc()).limit(1))
    code, total, heads = b.order.code, float(b.grand_total_pkr), dict(b.by_cost_head)
    db.close()
    rep = client.post("/api/reports/weekly-funds", json={"order_codes_text": f"{code}\nBS-DOES-NOT-EXIST"}, headers=h).json()
    assert rep["missing_codes"] == ["BS-DOES-NOT-EXIST"]
    row = next(r for r in rep["rows"] if r["order_code"] == code)
    assert row["found"] and row["total_pkr"] == pytest.approx(total)
    assert row["heads"]["Metal"] == pytest.approx(heads.get("Metal", 0.0))
    assert set(rep["heads"]) >= {"Metal", "Acrylic", "Paint", "Misc"}
    assert rep["totals"]["total_pkr"] == pytest.approx(total)


def test_xlsx_layout_matches_sheet(h):
    x = client.post("/api/reports/weekly-funds.xlsx", json={"weekly_bucket": "October - 1st week", "include_unsaved": False}, headers=h)
    assert x.status_code == 200 and x.headers["content-type"].startswith("application/vnd.openxmlformats")
    ws = openpyxl.load_workbook(io.BytesIO(x.content)).active
    hdr = [c.value for c in ws[1]]
    assert hdr[:9] == ["Sr. #", "Order Date", "Order Code", "Sign Type", "Images link", "Calculator Production Cost (by OD)", "Width (Inches)", "Height (Inches)", "Total Area (Sign) Ft2"]
    assert "Metal" in hdr and "Total material Cost (PKR)" in hdr


def test_by_material_aggregates(h):
    rows = client.post("/api/reports/by-material", json={}, headers=h).json()
    assert rows and all(r["qty"] > 0 for r in rows)
    assert rows == sorted(rows, key=lambda r: -r["total_with_wastage_pkr"])
    x = client.post("/api/reports/by-material.xlsx", json={}, headers=h)
    assert x.status_code == 200
    assert client.get("/api/reports/weekly-buckets", headers=h).status_code == 200
