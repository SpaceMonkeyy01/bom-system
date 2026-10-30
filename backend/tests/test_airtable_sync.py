"""Airtable pull and write-back against the fake client (no network)."""

from datetime import date

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import BOM, Order, SignType, WriteBack
from app.services.airtable import FakeAirtableClient, _flatten_fields, pull_orders, retry_failed, write_back
from app.services.bom import BOMRequest, build_bom, save_bom


def _rec(rid, code, **fields):
    base = {
        "Order Code": code,
        "Sign Type": "Metal - With Backlit",
        "Status": ["Shipping Needed", "Packed"],
        "Account Name": "Signmakerz-Ads",
        "Width( Inches)": 24,
        "Height(inches)": 12.5,
        "Finish": ["Matte"],
        "LED color": ["Warm White"],
        "Usage (Indoor / Outdoor)": "Outdoor",
        "Special Notes": "3D Metal Backlit Sign.\nDimensions: 24 x 12.5",
        "Order Date": "2026-10-28",
        "Dispatch by date": "2026-11-05",
        "Inventory Weekly Payment": "October - 4th week",
        "Design Image": [{"url": "https://example.com/a.png", "filename": "a.png"}],
        "BOM Done": False,
        "Etsy Sign Price": 250,
    }
    base.update(fields)
    return {"id": rid, "fields": base}


def test_flatten_fields_matches_csv_shapes():
    f = _flatten_fields(_rec("recX", "BS-T-1")["fields"])
    assert f["Status"] == "Shipping Needed,Packed"
    assert f["Finish"] == "Matte"
    assert f["Design Image"] == "a.png (https://example.com/a.png)"
    assert f["BOM Done"] == ""
    assert f["Width( Inches)"] == "24"


def test_pull_creates_updates_and_keeps_manual_mapping():
    db = SessionLocal()
    st = db.scalar(select(SignType).where(SignType.name == "Metal - With Backlit"))
    if not st:
        pytest.skip("seeded sign types missing")
    code = "BS-TEST-AT-1"
    db.query(Order).filter(Order.code == code).delete()
    db.commit()
    client = FakeAirtableClient(tables={"Test Month": [_rec("recTEST1", code)]})
    r = pull_orders(db, client, "Test Month")
    db.commit()
    assert r.fetched == 1 and r.created == 1 and r.updated == 0
    o = db.scalar(select(Order).where(Order.code == code))
    assert o.airtable_record_id == "recTEST1" and o.sign_type_id == st.id and o.finish == "Matte" and float(o.height_in) == 12.5
    assert o.dispatch_by == date(2026, 11, 5) and o.images[0]["url"] == "https://example.com/a.png"

    # second pull: an unknown sign type name must not wipe a mapping the team made in the app
    client.tables["Test Month"][0]["fields"]["Sign Type"] = "Some Brand New Name"
    client.tables["Test Month"][0]["fields"]["Width( Inches)"] = 30
    r2 = pull_orders(db, client, "Test Month")
    db.commit()
    db.refresh(o)
    assert r2.updated == 1 and float(o.width_in) == 30 and o.sign_type_id == st.id
    assert r2.unmapped_sign_types == {"Some Brand New Name": 1}

    # write-back of a saved BOM
    bom = build_bom(db, BOMRequest(order_id=o.id, parameters={"Crunched_Area_SS_ft2": 1, "Surface_Area": 2}))
    save_bom(db, bom)
    db.commit()
    wb = write_back(db, client, bom)
    db.commit()
    assert wb.status == "sent", wb.error
    sent = client.updates[-1][2]
    assert sent["BOM Done"] is True and sent["BOM Price(PKR)"] == float(bom.grand_total_pkr) and "BOM Done Time" in sent
    assert client.tables["Test Month"][0]["fields"]["BOM Price(PKR)"] == float(bom.grand_total_pkr)
    db.refresh(bom)
    assert bom.status == "written_back"

    # failure path + retry
    bad = Order(code="BS-TEST-AT-2", sign_type_id=st.id, width_in=10, height_in=10)
    db.add(bad)
    db.flush()
    bom2 = build_bom(db, BOMRequest(order_id=bad.id, parameters={"Crunched_Area_SS_ft2": 1}))
    save_bom(db, bom2)
    db.commit()
    wb2 = write_back(db, client, bom2)
    db.commit()
    assert wb2.status == "failed" and "no Airtable record" in wb2.error
    bad.airtable_record_id, bad.airtable_table = "recTEST2", "Test Month"
    client.tables["Test Month"].append(_rec("recTEST2", "BS-TEST-AT-2"))
    db.commit()
    assert retry_failed(db, client) == 1
    db.commit()
    statuses = [w.status for w in db.scalars(select(WriteBack).where(WriteBack.bom_id == bom2.id).order_by(WriteBack.id))]
    assert statuses == ["superseded", "sent"]

    # tidy
    for c in ("BS-TEST-AT-1", "BS-TEST-AT-2"):
        oo = db.scalar(select(Order).where(Order.code == c))
        for b in db.scalars(select(BOM).where(BOM.order_id == oo.id)):
            for w in b.write_backs:
                db.delete(w)
            db.delete(b)
        db.delete(oo)
    db.commit()
    db.close()
