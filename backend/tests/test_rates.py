"""Rate resolution rules, exercised against the test database."""

from datetime import date

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import Base
from app.models import Material, MaterialRate, RatePolicy, Supplier
from app.models.core import RateSource
from app.services.rates import RateResolver


@pytest.fixture(scope="module")
def db():
    engine = create_engine(settings.test_database_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def _material(db, name, **kw):
    m = Material(name=name, **kw)
    db.add(m)
    db.flush()
    return m


def test_policy_prefers_bom_then_falls_back_to_iflow_and_flags_stale(db):
    db.add(RatePolicy(scope="global", preferred_source=RateSource.bom, fallback_order=["iflow:BS", "iflow:NS"], staleness_days=60))
    m = _material(db, "SS Metal 14g")
    db.add(MaterialRate(material=m, source=RateSource.iflow, store="BS", rate=700, effective_from=date(2026, 10, 1)))
    db.add(MaterialRate(material=m, source=RateSource.bom, rate=778, effective_from=date(2025, 9, 1)))
    db.flush()
    r = RateResolver(db, as_of=date(2026, 10, 30)).resolve(m)
    assert r.rate == 778 and r.source == "bom" and r.stale  # preferred source wins even when stale

    m2 = _material(db, "Only in iFlow")
    db.add(MaterialRate(material=m2, source=RateSource.iflow, store="NS", rate=12, effective_from=date(2026, 10, 20)))
    db.flush()
    r2 = RateResolver(db, as_of=date(2026, 10, 30)).resolve(m2)
    assert r2.rate == 12 and r2.source == "iflow:NS" and not r2.stale

    r3 = RateResolver(db).resolve(_material(db, "No rates"))
    assert r3.source == "none" and r3.rate == 0


def test_supplier_rules(db):
    a = Supplier(name="Khizer Brothers")
    b = Supplier(name="Lahore Purchaser")
    db.add_all([a, b])
    db.flush()
    m = _material(db, "Nexa Hardner 922", preferred_supplier_id=b.id)
    db.add(MaterialRate(material=m, source=RateSource.supplier, supplier_id=a.id, rate=7.5, effective_from=date(2026, 10, 1)))
    db.add(MaterialRate(material=m, source=RateSource.supplier, supplier_id=b.id, rate=8.0, effective_from=date(2026, 10, 15)))
    db.add(MaterialRate(material=m, source=RateSource.supplier, supplier_id=a.id, rate=6.9, effective_from=date(2026, 9, 1)))
    db.flush()
    as_of = date(2026, 10, 30)
    pol = RatePolicy(scope="material", scope_id=m.id, preferred_source=RateSource.supplier, fallback_order=[], staleness_days=60, supplier_rule="latest")
    db.add(pol)
    db.flush()

    r = RateResolver(db, as_of).resolve(m)
    assert r.rate == 8.0 and r.source == "supplier:Lahore Purchaser" and r.policy_scope == "material"

    pol.supplier_rule = "cheapest"  # lowest of each supplier's *latest* rate: a=7.5 (not the older 6.9), b=8.0
    db.flush()
    assert RateResolver(db, as_of).resolve(m).rate == 7.5

    pol.supplier_rule = "preferred"
    db.flush()
    assert RateResolver(db, as_of).resolve(m).source == "supplier:Lahore Purchaser"

    pol.supplier_rule = str(a.id)
    db.flush()
    assert RateResolver(db, as_of).resolve(m).rate == 7.5

    rows = RateResolver(db, as_of).all_rates(m)
    assert {x["source"] for x in rows} == {"supplier:Khizer Brothers", "supplier:Lahore Purchaser"}


def test_category_policy_walks_up_the_tree(db):
    from app.models import Category

    root = Category(name="Paints", level=1, path="Paints")
    child = Category(parent=root, name="2K Paint", level=2, path="Paints / 2K Paint")
    db.add_all([root, child])
    db.flush()
    db.add(RatePolicy(scope="category", scope_id=root.id, preferred_source=RateSource.iflow, fallback_order=["bom"], staleness_days=30))
    m = _material(db, "Jet Black", category_id=child.id)
    db.add(MaterialRate(material=m, source=RateSource.bom, rate=8, effective_from=date(2026, 10, 1)))
    db.add(MaterialRate(material=m, source=RateSource.iflow, store="BS", rate=9, effective_from=date(2026, 10, 1)))
    db.flush()
    db.expire_all()
    r = RateResolver(db, date(2026, 10, 30)).resolve(m)
    assert r.rate == 9 and r.policy_scope == "category"
