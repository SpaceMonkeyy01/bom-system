"""Historical sheet import: imported BOMs reproduce the sheet's totals and reconcile with Airtable's BOM price."""

import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import BOM, Order


@pytest.fixture(scope="module")
def db():
    s = SessionLocal()
    if not s.scalar(select(BOM.id).where(BOM.status == "imported").limit(1)):
        pytest.skip("historical BOMs not imported (python -m app.seed.run --only historical_boms)")
    yield s
    s.close()


def test_imported_boms_reconcile_with_airtable(db):
    rows = db.execute(select(BOM.grand_total_pkr, Order.airtable_bom_price_pkr).join(Order, Order.id == BOM.order_id).where(BOM.status == "imported", Order.airtable_bom_price_pkr.isnot(None))).all()
    assert len(rows) > 400
    within_1 = sum(1 for g, a in rows if abs(float(g) - float(a)) <= 1.0)
    assert within_1 / len(rows) > 0.98  # the handful that differ were edited in Airtable after the sheet


def test_imported_boms_have_lines_and_heads(db):
    b = db.scalar(select(BOM).where(BOM.status == "imported", BOM.grand_total_pkr > 0).limit(1))
    assert b.lines and all(ln.rate_source == "sheet" for ln in b.lines)
    assert sum(b.by_cost_head.values()) == pytest.approx(float(b.grand_total_pkr), rel=1e-3)
    assert b.template_id is None and b.source.startswith("sheet-import")


def test_import_is_idempotent(db):
    from app.seed.historical_boms import import_october_boms

    before = db.scalar(select(func.count(BOM.id)).where(BOM.status == "imported"))
    stats = import_october_boms(db)
    db.rollback()
    assert stats["imported"] == 0 and stats["skipped_existing"] == before
