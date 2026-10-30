"""Airtable integration: pull orders, push BOM results. The HTTP client is swappable so tests run offline.

Field names follow the orders base as exported in the 'Ali Hassan View' CSV. Change them in
`AIRTABLE_WRITE_FIELDS` / `map_airtable_record` if the base is renamed, not in callers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import BOM, Order, WriteBack
from app.seed.orders import map_airtable_record, sign_type_resolver

AIRTABLE_API = "https://api.airtable.com/v0"

# BOM result -> Airtable field name
AIRTABLE_WRITE_FIELDS = {
    "bom_price_pkr": "BOM Price(PKR)",
    "bom_price_usd": "BOM Price(Dollar Converted)",
    "production_cost_usd": "BOM Revised Production Cost",
    "box_dimension": "BOM Estd. Box Dimension",
    "est_shipment_cost_usd": "BOM Estd. Shipment cost",
    "bom_done": "BOM Done",
    "bom_done_time": "BOM Done Time",
}


class AirtableClient(Protocol):
    def list_records(self, table: str, modified_since: datetime | None = None) -> list[dict]: ...

    def update_record(self, table: str, record_id: str, fields: dict[str, Any]) -> dict: ...


class HttpAirtableClient:
    """Real client. Paginates, respects the 5 req/s limit loosely, raises on HTTP errors."""

    def __init__(self, token: str, base_id: str, timeout: float = 30.0):
        self.base_id = base_id
        self.http = httpx.Client(base_url=f"{AIRTABLE_API}/{base_id}", headers={"Authorization": f"Bearer {token}"}, timeout=timeout)

    def list_records(self, table: str, modified_since: datetime | None = None) -> list[dict]:
        params: dict[str, Any] = {"pageSize": 100}
        if modified_since:
            iso = modified_since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            params["filterByFormula"] = f"IS_AFTER(LAST_MODIFIED_TIME(), '{iso}')"
        out: list[dict] = []
        offset = None
        while True:
            if offset:
                params["offset"] = offset
            r = self.http.get(f"/{table}", params=params)
            r.raise_for_status()
            data = r.json()
            out.extend(data.get("records", []))
            offset = data.get("offset")
            if not offset:
                return out

    def update_record(self, table: str, record_id: str, fields: dict[str, Any]) -> dict:
        r = self.http.patch(f"/{table}/{record_id}", json={"fields": fields, "typecast": True})
        r.raise_for_status()
        return r.json()


@dataclass
class FakeAirtableClient:
    """In-memory stand-in with the same shape; tests and local dev without a token."""

    tables: dict[str, list[dict]] = field(default_factory=dict)
    updates: list[tuple[str, str, dict]] = field(default_factory=list)

    def list_records(self, table: str, modified_since: datetime | None = None) -> list[dict]:
        return list(self.tables.get(table, []))

    def update_record(self, table: str, record_id: str, fields: dict[str, Any]) -> dict:
        self.updates.append((table, record_id, fields))
        for rec in self.tables.get(table, []):
            if rec["id"] == record_id:
                rec["fields"].update(fields)
                return rec
        raise KeyError(record_id)


def get_client() -> AirtableClient | None:
    if settings.airtable_token and settings.airtable_base_id:
        return HttpAirtableClient(settings.airtable_token, settings.airtable_base_id)
    return None


def _flatten_fields(fields: dict[str, Any]) -> dict[str, str]:
    """Airtable API values -> the strings map_airtable_record expects (it was written for the CSV export)."""
    out: dict[str, str] = {}
    for k, v in fields.items():
        if isinstance(v, list):
            if v and isinstance(v[0], dict) and "url" in v[0]:  # attachments
                out[k] = ", ".join(f"{a.get('filename', 'file')} ({a['url']})" for a in v)
            else:
                out[k] = ",".join(str(x) for x in v)  # multi-select
        elif isinstance(v, bool):
            out[k] = "checked" if v else ""
        elif v is None:
            out[k] = ""
        else:
            out[k] = str(v)
    return out


@dataclass
class SyncResult:
    table: str
    fetched: int = 0
    created: int = 0
    updated: int = 0
    unmapped_sign_types: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def pull_orders(db: Session, client: AirtableClient, table: str, modified_since: datetime | None = None) -> SyncResult:
    """Upsert Orders from one Airtable table. Match by record id first, then by order code (for rows seeded from CSV)."""
    res = SyncResult(table=table)
    resolve = sign_type_resolver(db)
    records = client.list_records(table, modified_since)
    res.fetched = len(records)
    by_rec = {o.airtable_record_id: o for o in db.scalars(select(Order).where(Order.airtable_record_id.isnot(None)))}
    by_code = {o.code: o for o in db.scalars(select(Order))}
    now = datetime.now(timezone.utc)
    for rec in records:
        try:
            data = map_airtable_record(_flatten_fields(rec.get("fields", {})), resolve)
        except Exception as e:  # pragma: no cover - defensive against odd rows
            res.errors.append(f"{rec.get('id')}: {e}")
            continue
        if not data["code"]:
            continue
        o = by_rec.get(rec["id"]) or by_code.get(data["code"])
        if o is None:
            o = Order(code=data["code"])
            db.add(o)
            by_code[data["code"]] = o
            res.created += 1
        else:
            res.updated += 1
        if data["sign_type_id"] is None and data["sign_type_raw"]:
            res.unmapped_sign_types[data["sign_type_raw"]] = res.unmapped_sign_types.get(data["sign_type_raw"], 0) + 1
        for k, v in data.items():
            if k == "sign_type_id" and v is None and o.sign_type_id is not None:
                continue  # keep a manual mapping made in the app
            setattr(o, k, v)
        o.airtable_record_id = rec["id"]
        o.airtable_table = table
        o.raw = rec.get("fields", {})
        o.synced_at = now
    db.flush()
    return res


def pull_all(db: Session, client: AirtableClient, tables: list[str], since: datetime | None = None) -> list[SyncResult]:
    return [pull_orders(db, client, t, since) for t in tables]


def write_back(db: Session, client: AirtableClient, bom: BOM) -> WriteBack:
    """Push a saved BOM's results to its order's Airtable record. Always logs a WriteBack row."""
    order = bom.order
    fields = {
        AIRTABLE_WRITE_FIELDS["bom_price_pkr"]: float(bom.grand_total_pkr),
        AIRTABLE_WRITE_FIELDS["bom_price_usd"]: round(float(bom.grand_total_pkr) / float(bom.pkr_per_usd), 2),
        AIRTABLE_WRITE_FIELDS["production_cost_usd"]: float(bom.production_cost_usd or 0),
        AIRTABLE_WRITE_FIELDS["bom_done"]: True,
        AIRTABLE_WRITE_FIELDS["bom_done_time"]: (bom.saved_at or datetime.now(timezone.utc)).strftime("%d/%m/%Y %I:%M%p").lower(),
    }
    if bom.box_dimension:
        fields[AIRTABLE_WRITE_FIELDS["box_dimension"]] = bom.box_dimension
    if bom.est_shipment_cost_usd is not None:
        fields[AIRTABLE_WRITE_FIELDS["est_shipment_cost_usd"]] = float(bom.est_shipment_cost_usd)
    wb = WriteBack(bom_id=bom.id, target="airtable", fields_sent=fields, status="pending")
    db.add(wb)
    if not order.airtable_record_id or not order.airtable_table:
        wb.status, wb.error = "failed", "Order has no Airtable record id / table (was it seeded from CSV only?)"
        db.flush()
        return wb
    try:
        client.update_record(order.airtable_table, order.airtable_record_id, fields)
        wb.status, wb.sent_at = "sent", datetime.now(timezone.utc)
        bom.status = "written_back"
        order.airtable_bom_done = True
        order.airtable_bom_price_pkr = float(bom.grand_total_pkr)
    except Exception as e:
        wb.status, wb.error = "failed", str(e)[:1000]
    db.flush()
    return wb


def retry_failed(db: Session, client: AirtableClient, limit: int = 50) -> int:
    """Re-send failed write-backs whose BOM is still the latest saved version for its order."""
    n = 0
    for wb in db.scalars(select(WriteBack).where(WriteBack.status == "failed").order_by(WriteBack.id).limit(limit)):
        bom = wb.bom
        latest = db.scalar(select(BOM).where(BOM.order_id == bom.order_id).order_by(BOM.version.desc()))
        if latest.id != bom.id:
            wb.status = "superseded"
            continue
        if write_back(db, client, bom).status == "sent":
            wb.status = "superseded"  # the new row records the successful send
            n += 1
    db.flush()
    return n
