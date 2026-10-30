"""Scheduled job: incremental Airtable pull + retry failed write-backs. Exits 0 when nothing is configured."""

from __future__ import annotations

import sys
from datetime import timedelta

from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models import Order
from app.services.airtable import get_client, pull_all, retry_failed


def main() -> int:
    client = get_client()
    if not client or not settings.airtable_tables:
        print("airtable_pull: not configured (token/base/tables); nothing to do")
        return 0
    db = SessionLocal()
    try:
        since = db.scalar(select(Order.synced_at).where(Order.airtable_record_id.isnot(None)).order_by(Order.synced_at.desc()).limit(1))
        if since:
            since = since - timedelta(minutes=5)  # overlap so a slow write isn't missed
        results = pull_all(db, client, settings.airtable_tables, since)
        resent = retry_failed(db, client)
        db.commit()
        for r in results:
            print(f"airtable_pull: {r.table}: fetched={r.fetched} created={r.created} updated={r.updated} unmapped={len(r.unmapped_sign_types)} errors={len(r.errors)}")
        print(f"airtable_pull: write-backs resent={resent}")
        return 0
    except Exception as e:
        db.rollback()
        print(f"airtable_pull: FAILED {e}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
