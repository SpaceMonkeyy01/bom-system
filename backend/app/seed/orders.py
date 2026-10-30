"""Load orders from an Airtable CSV export (the 'Ali Hassan View'). Same field mapping the live sync will use."""

from __future__ import annotations

import csv
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Order, SignType
from app.seed.common import RAW_DIR, clean, to_date, to_float

AIRTABLE_CSV = RAW_DIR / "airtable_october_2026.csv"

ATTACHMENT_RE = re.compile(r"(?P<name>[^,(]+?)\s*\((?P<url>https?://[^)]+)\)")


def _attachments(kind: str, cell: str | None) -> list[dict]:
    out = []
    for m in ATTACHMENT_RE.finditer(cell or ""):
        out.append({"kind": kind, "filename": m.group("name").strip(), "url": m.group("url")})
    return out


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def sign_type_resolver(db: Session):
    sts = list(db.scalars(select(SignType)))
    index: dict[str, SignType] = {}
    for st in sts:
        index.setdefault(_key(st.name), st)
        for a in st.aliases:
            index.setdefault(_key(a), st)

    def resolve(raw: str | None) -> SignType | None:
        if not raw:
            return None
        return index.get(_key(raw))

    return resolve


def map_airtable_record(rec: dict, resolve) -> dict:
    """Airtable field names (as exported) -> Order columns. Shared by the CSV seed and the API sync."""
    g = lambda k: clean(rec.get(k))  # noqa: E731
    raw_sign = g("Sign Type")
    st = resolve(raw_sign)
    images = (
        _attachments("cdr", rec.get("CDR design"))
        + _attachments("design", rec.get("Design Image"))
        + _attachments("bom", rec.get("BOM Images"))
        + _attachments("photo", rec.get("Real-time Image"))
        + _attachments("pdf", rec.get("PDF file"))
    )
    return dict(
        code=g("Order Code"),
        account_name=g("Account Name"),
        country=g("Country Name"),
        sign_type_raw=raw_sign,
        sign_type_id=st.id if st else None,
        width_in=to_float(g("Width( Inches)")),
        height_in=to_float(g("Height(inches)")),
        finish=g("Finish"),
        led_color=g("LED color"),
        usage=g("Usage (Indoor / Outdoor)"),
        special_notes=clean(rec.get("Special Notes")),
        status=g("Status"),
        order_date=to_date(g("Order Date")),
        dispatch_by=to_date(g("Dispatch by date")),
        weekly_bucket=g("Inventory Weekly Payment"),
        images=images,
        etsy_price_usd=to_float(g("Etsy Sign Price")),
        calculator_production_cost_usd=to_float(g("Calculator Production Cost")),
        calculator_shipping_cost_usd=to_float(g("Calculator Shipping Cost")),
        airtable_bom_done=(g("BOM Done") or "").lower() in ("checked", "true", "1", "yes"),
        airtable_bom_price_pkr=to_float(g("BOM Price(PKR)")),
        reason_of_re=clean(rec.get("Reason of RE")),
    )


def seed_orders(db: Session, path=AIRTABLE_CSV, table_name: str = "October 2026") -> dict:
    csv.field_size_limit(10**9)
    resolve = sign_type_resolver(db)
    existing = {o.code: o for o in db.scalars(select(Order))}
    stats = {"created": 0, "updated": 0, "skipped": 0, "unmapped_sign_types": {}}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for rec in csv.DictReader(f):
            data = map_airtable_record(rec, resolve)
            if not data["code"]:
                stats["skipped"] += 1
                continue
            if data["sign_type_id"] is None and data["sign_type_raw"]:
                stats["unmapped_sign_types"][data["sign_type_raw"]] = stats["unmapped_sign_types"].get(data["sign_type_raw"], 0) + 1
            o = existing.get(data["code"])
            if o is None:
                o = Order(code=data["code"])
                db.add(o)
                existing[data["code"]] = o
                stats["created"] += 1
            else:
                stats["updated"] += 1
            for k, v in data.items():
                setattr(o, k, v)
            o.airtable_table = table_name
            o.raw = {k: v for k, v in rec.items() if v}
            o.synced_at = datetime.now(timezone.utc)
    db.flush()
    return stats
