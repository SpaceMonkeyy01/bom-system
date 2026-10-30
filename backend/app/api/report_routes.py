from __future__ import annotations

from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Order
from app.services.auth import current_user
from app.services.reports import ReportFilter, consolidated_by_material, funds_report_xlsx, material_report_xlsx, weekly_funds

router = APIRouter(dependencies=[Depends(current_user)])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ReportFilterIn(BaseModel):
    order_codes: list[str] | None = None
    order_codes_text: str | None = Field(None, description="Pasted ids, one per line or comma-separated")
    weekly_bucket: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    saved_from: date | None = None
    saved_to: date | None = None
    include_unsaved: bool = False

    def to_filter(self) -> ReportFilter:
        codes = list(self.order_codes or [])
        if self.order_codes_text:
            for part in self.order_codes_text.replace(",", "\n").splitlines():
                if part.strip():
                    codes.append(part.strip())
        return ReportFilter(order_codes=codes or None, weekly_bucket=self.weekly_bucket, date_from=self.date_from, date_to=self.date_to, saved_from=self.saved_from, saved_to=self.saved_to, include_unsaved=self.include_unsaved)


@router.post("/reports/weekly-funds")
def weekly_funds_json(body: ReportFilterIn, db: Session = Depends(get_session)):
    rep = weekly_funds(db, body.to_filter())
    return {"heads": rep.heads, "rows": [asdict(r) for r in rep.rows], "totals": rep.totals, "missing_codes": rep.missing_codes}


@router.post("/reports/weekly-funds.xlsx")
def weekly_funds_file(body: ReportFilterIn, db: Session = Depends(get_session)):
    rep = weekly_funds(db, body.to_filter())
    name = (body.weekly_bucket or f"{date.today():%Y-%m-%d}").replace(" ", "_")
    return Response(funds_report_xlsx(rep), media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="BOM weekly report {name}.xlsx"'})


@router.post("/reports/by-material")
def by_material_json(body: ReportFilterIn, db: Session = Depends(get_session)):
    return [asdict(r) for r in consolidated_by_material(db, body.to_filter())]


@router.post("/reports/by-material.xlsx")
def by_material_file(body: ReportFilterIn, db: Session = Depends(get_session)):
    rows = consolidated_by_material(db, body.to_filter())
    return Response(material_report_xlsx(rows), media_type=XLSX, headers={"Content-Disposition": 'attachment; filename="BOM by material.xlsx"'})


@router.get("/reports/weekly-buckets")
def weekly_buckets(db: Session = Depends(get_session)):
    rows = db.execute(select(Order.weekly_bucket, func.count(Order.id)).where(Order.weekly_bucket.isnot(None)).group_by(Order.weekly_bucket).order_by(Order.weekly_bucket)).all()
    return [{"bucket": b, "orders": n} for b, n in rows]
