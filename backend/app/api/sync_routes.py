"""Order sync: Airtable pull/write-back and a CSV-export fallback for when no token is configured."""

from __future__ import annotations

import csv
import io
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_session
from app.models import BOM, Order, User, WriteBack
from app.seed.orders import map_airtable_record, sign_type_resolver
from app.services.airtable import get_client, pull_all, refresh_order_images, retry_failed, write_back
from app.services.auth import current_user, require

router = APIRouter(dependencies=[Depends(current_user)])


class SyncSettingsOut(BaseModel):
    configured: bool
    base_id: str | None
    tables: list[str]
    last_synced_at: datetime | None


@router.get("/sync/airtable/status", response_model=SyncSettingsOut)
def status(db: Session = Depends(get_session)):
    last = db.scalar(select(Order.synced_at).where(Order.airtable_record_id.isnot(None)).order_by(Order.synced_at.desc()).limit(1))
    return SyncSettingsOut(configured=get_client() is not None, base_id=settings.airtable_base_id, tables=settings.airtable_tables, last_synced_at=last)


class PullBody(BaseModel):
    tables: list[str] | None = None
    full: bool = False  # ignore the incremental watermark


@router.post("/sync/airtable/pull")
def pull(body: PullBody, _: User = Depends(require("bom:write")), db: Session = Depends(get_session)):
    client = get_client()
    if not client:
        raise HTTPException(400, "Airtable is not configured (BOM_AIRTABLE_TOKEN / BOM_AIRTABLE_BASE_ID)")
    tables = body.tables or settings.airtable_tables
    if not tables:
        raise HTTPException(400, "No Airtable tables configured (BOM_AIRTABLE_TABLES)")
    since = None
    if not body.full:
        since = db.scalar(select(Order.synced_at).where(Order.airtable_record_id.isnot(None)).order_by(Order.synced_at.desc()).limit(1))
    results = pull_all(db, client, tables, since)
    db.commit()
    return [r.__dict__ for r in results]


@router.post("/sync/airtable/upload-csv")
async def upload_csv(table_name: str = Form("CSV export"), file: UploadFile = File(...), _: User = Depends(require("bom:write")), db: Session = Depends(get_session)):
    """Fallback: upload an Airtable CSV export of the orders view. Same mapping as the live sync."""
    text = (await file.read()).decode("utf-8-sig", errors="replace")
    csv.field_size_limit(10**9)
    resolve = sign_type_resolver(db)
    by_code = {o.code: o for o in db.scalars(select(Order))}
    created = updated = 0
    unmapped: dict[str, int] = {}
    for rec in csv.DictReader(io.StringIO(text)):
        data = map_airtable_record(rec, resolve)
        if not data["code"]:
            continue
        o = by_code.get(data["code"])
        if o is None:
            o = Order(code=data["code"])
            db.add(o)
            by_code[data["code"]] = o
            created += 1
        else:
            updated += 1
        if data["sign_type_id"] is None and data["sign_type_raw"]:
            unmapped[data["sign_type_raw"]] = unmapped.get(data["sign_type_raw"], 0) + 1
        for k, v in data.items():
            if k == "sign_type_id" and v is None and o.sign_type_id is not None:
                continue
            setattr(o, k, v)
        o.airtable_table = o.airtable_table or table_name
        o.raw = {k: v for k, v in rec.items() if v}
        o.synced_at = datetime.utcnow()
    db.commit()
    return {"created": created, "updated": updated, "unmapped_sign_types": unmapped}


@router.post("/boms/{bom_id}/write-back")
def push_bom(bom_id: int, _: User = Depends(require("bom:write")), db: Session = Depends(get_session)):
    bom = db.get(BOM, bom_id)
    if not bom:
        raise HTTPException(404, "BOM not found")
    if bom.status not in ("saved", "written_back"):
        raise HTTPException(400, "Save the BOM first")
    client = get_client()
    if not client:
        raise HTTPException(400, "Airtable is not configured; the BOM is saved here but was not pushed")
    wb = write_back(db, client, bom)
    db.commit()
    return {"status": wb.status, "error": wb.error, "fields": wb.fields_sent}


@router.post("/sync/airtable/retry-failed")
def retry(_: User = Depends(require("bom:write")), db: Session = Depends(get_session)):
    client = get_client()
    if not client:
        raise HTTPException(400, "Airtable is not configured")
    n = retry_failed(db, client)
    db.commit()
    return {"resent": n}


@router.get("/sync/write-backs")
def list_write_backs(status: str | None = None, limit: int = 100, db: Session = Depends(get_session)):
    stmt = select(WriteBack).order_by(WriteBack.id.desc()).limit(limit)
    if status:
        stmt = stmt.where(WriteBack.status == status)
    return [{"id": w.id, "bom_id": w.bom_id, "order_code": w.bom.order.code, "status": w.status, "error": w.error, "sent_at": w.sent_at, "created_at": w.created_at, "fields": w.fields_sent} for w in db.scalars(stmt)]


@router.get("/orders/{order_id}/images/{index}")
def order_image(order_id: int, index: int, thumb: bool = False, db: Session = Depends(get_session)):
    """Serve an order attachment through the API. Airtable's signed URLs expire, so when the stored URL fails and
    Airtable is configured, the record is re-read for fresh URLs and the image is retried once."""
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Order not found")

    def fetch(images):
        if index < 0 or index >= len(images):
            return None
        url = (images[index].get("thumb") if thumb else None) or images[index]["url"]
        try:
            r = httpx.get(url, timeout=20, follow_redirects=True)
        except httpx.HTTPError:
            return None
        return r if r.status_code == 200 else None

    r = fetch(order.images or [])
    if r is None:
        client = get_client()
        if client:
            try:
                images = refresh_order_images(db, client, order)
                db.commit()
                r = fetch(images)
            except Exception:
                r = None
    if r is None:
        raise HTTPException(404, "Image not available (the Airtable link has expired and no live connection is configured)")
    return Response(r.content, media_type=r.headers.get("content-type", "application/octet-stream"), headers={"Cache-Control": "private, max-age=3600"})
