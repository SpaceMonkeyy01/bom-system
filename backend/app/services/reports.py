"""The two reports the team runs from the sheet today, built from saved BOMs.

- Weekly funds report: one row per order (latest saved BOM), cost split by cost head.
- Consolidated by material: material totals across a set of orders (what the reconciliation tab tried to do).
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import BOM, BOMLine, CostHead, Order

REPORT_HEADS_FALLBACK = ["Metal", "Acrylic", "LEDs", "Paint", "Power Supply", "Packaging", "Misc", "UV", "Alucobond", "PVD Coating", "Wires", "Tanaka Nozzle"]


@dataclass
class ReportFilter:
    order_codes: list[str] | None = None  # explicit list (pasted ids)
    weekly_bucket: str | None = None  # "October - 3rd week"
    date_from: date | None = None  # by order_date
    date_to: date | None = None
    saved_from: date | None = None  # by BOM saved_at
    saved_to: date | None = None
    include_unsaved: bool = False  # list orders without a BOM as empty rows


@dataclass
class FundsRow:
    order_id: int
    order_code: str
    order_date: date | None
    sign_type: str | None
    image_url: str | None
    calculator_production_cost_usd: float | None
    width_in: float | None
    height_in: float | None
    area_sqft: float | None
    heads: dict[str, float]
    total_pkr: float
    production_cost_usd: float | None
    bom_id: int | None
    bom_version: int | None
    weekly_bucket: str | None
    found: bool


@dataclass
class FundsReport:
    heads: list[str]
    rows: list[FundsRow]
    totals: dict[str, float] = field(default_factory=dict)
    missing_codes: list[str] = field(default_factory=list)


def cost_head_names(db: Session) -> list[str]:
    names = [h.name for h in db.scalars(select(CostHead).order_by(CostHead.sort_order))]
    return names or REPORT_HEADS_FALLBACK


def _latest_boms(db: Session, flt: ReportFilter) -> tuple[list[Order], dict[int, BOM]]:
    stmt = select(Order).options(selectinload(Order.sign_type), selectinload(Order.boms).selectinload(BOM.lines))
    if flt.order_codes:
        wanted = [c.strip() for c in flt.order_codes if c and c.strip()]
        stmt = stmt.where(Order.code.in_(wanted))
    if flt.weekly_bucket:
        stmt = stmt.where(Order.weekly_bucket == flt.weekly_bucket)
    if flt.date_from:
        stmt = stmt.where(Order.order_date >= flt.date_from)
    if flt.date_to:
        stmt = stmt.where(Order.order_date <= flt.date_to)
    orders = list(db.scalars(stmt.order_by(Order.order_date, Order.code)))
    latest: dict[int, BOM] = {}
    for o in orders:
        saved = [b for b in o.boms if b.status in ("saved", "written_back", "imported")]
        if flt.saved_from:
            saved = [b for b in saved if b.saved_at and b.saved_at.date() >= flt.saved_from]
        if flt.saved_to:
            saved = [b for b in saved if b.saved_at and b.saved_at.date() <= flt.saved_to]
        if saved:
            latest[o.id] = max(saved, key=lambda b: b.version)
    if flt.order_codes:  # keep the pasted order
        pos = {c.strip(): i for i, c in enumerate(flt.order_codes)}
        orders.sort(key=lambda o: pos.get(o.code, 10**9))
    return orders, latest


def weekly_funds(db: Session, flt: ReportFilter) -> FundsReport:
    heads = cost_head_names(db)
    orders, latest = _latest_boms(db, flt)
    rows: list[FundsRow] = []
    totals = {h: 0.0 for h in heads}
    totals["total_pkr"] = 0.0
    totals["area_sqft"] = 0.0
    totals["calculator_production_cost_usd"] = 0.0
    for o in orders:
        b = latest.get(o.id)
        if not b and not flt.include_unsaved:
            continue
        img = next((i["url"] for i in (o.images or []) if i.get("kind") in ("design", "cdr")), None) or (o.images[0]["url"] if o.images else None)
        by = {h: float((b.by_cost_head or {}).get(h, 0.0)) if b else 0.0 for h in heads}
        rows.append(
            FundsRow(
                order_id=o.id,
                order_code=o.code,
                order_date=o.order_date,
                sign_type=o.sign_type.name if o.sign_type else o.sign_type_raw,
                image_url=img,
                calculator_production_cost_usd=float(o.calculator_production_cost_usd) if o.calculator_production_cost_usd is not None else None,
                width_in=float(o.width_in) if o.width_in is not None else None,
                height_in=float(o.height_in) if o.height_in is not None else None,
                area_sqft=float(b.area_sqft) if b and b.area_sqft is not None else (float(o.width_in) * float(o.height_in) / 144 if o.width_in and o.height_in else None),
                heads=by,
                total_pkr=float(b.grand_total_pkr) if b else 0.0,
                production_cost_usd=float(b.production_cost_usd) if b and b.production_cost_usd is not None else None,
                bom_id=b.id if b else None,
                bom_version=b.version if b else None,
                weekly_bucket=o.weekly_bucket,
                found=b is not None,
            )
        )
        for h in heads:
            totals[h] += by[h]
        totals["total_pkr"] += rows[-1].total_pkr
        totals["area_sqft"] += rows[-1].area_sqft or 0.0
        totals["calculator_production_cost_usd"] += rows[-1].calculator_production_cost_usd or 0.0
    found_codes = {o.code for o in orders}
    missing = [c.strip() for c in (flt.order_codes or []) if c.strip() and c.strip() not in found_codes]
    return FundsReport(heads=heads, rows=rows, totals={k: round(v, 2) for k, v in totals.items()}, missing_codes=missing)


@dataclass
class MaterialRow:
    material_id: int | None
    material_name: str
    uom: str | None
    cost_head: str | None
    qty: float
    total_pkr: float
    total_with_wastage_pkr: float
    orders: int


def consolidated_by_material(db: Session, flt: ReportFilter) -> list[MaterialRow]:
    _, latest = _latest_boms(db, flt)
    acc: dict[tuple, MaterialRow] = {}
    seen_orders: dict[tuple, set[int]] = {}
    for b in latest.values():
        for ln in b.lines:
            if not ln.qty_final:
                continue
            key = (ln.material_id, ln.material_name if ln.material_id is None else None, ln.uom)
            row = acc.get(key)
            if not row:
                row = MaterialRow(ln.material_id, ln.material_name, ln.uom, ln.cost_head, 0.0, 0.0, 0.0, 0)
                acc[key] = row
                seen_orders[key] = set()
            row.qty += float(ln.qty_final)
            row.total_pkr += float(ln.total_pkr)
            row.total_with_wastage_pkr += float(ln.total_with_wastage_pkr)
            seen_orders[key].add(b.order_id)
    for key, row in acc.items():
        row.orders = len(seen_orders[key])
        row.qty, row.total_pkr, row.total_with_wastage_pkr = round(row.qty, 4), round(row.total_pkr, 2), round(row.total_with_wastage_pkr, 2)
    return sorted(acc.values(), key=lambda r: -r.total_with_wastage_pkr)


# ---------------------------------------------------------------- xlsx


def _style_header(ws, ncols: int) -> None:
    fill = PatternFill("solid", fgColor="DDE7F0")
    for c in range(1, ncols + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = Font(bold=True)
        cell.fill = fill
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    ws.freeze_panes = "A2"


def funds_report_xlsx(rep: FundsReport) -> bytes:
    """Same column order as the sheet's 'Weekly Funds Report' / 'BOM Consolidated' tab."""
    wb = Workbook()
    ws = wb.active
    ws.title = "BOM Consolidated"
    header = ["Sr. #", "Order Date", "Order Code", "Sign Type", "Images link", "Calculator Production Cost (by OD)", "Width (Inches)", "Height (Inches)", "Total Area (Sign) Ft2", *rep.heads, "Total material Cost (PKR)", "BOM Production Cost (USD)", "BOM version"]
    ws.append(header)
    _style_header(ws, len(header))
    for i, r in enumerate(rep.rows, start=1):
        ws.append([i, r.order_date, r.order_code, r.sign_type, r.image_url, r.calculator_production_cost_usd, r.width_in, r.height_in, round(r.area_sqft, 4) if r.area_sqft is not None else None, *[round(r.heads[h], 2) for h in rep.heads], round(r.total_pkr, 2), r.production_cost_usd, r.bom_version])
        if r.image_url:
            ws.cell(row=i + 1, column=5).hyperlink = r.image_url
    n = len(rep.rows)
    if n:
        tr = n + 2
        ws.cell(row=tr, column=3, value="Total").font = Font(bold=True)
        for col in [6, 9] + list(range(10, 10 + len(rep.heads))) + [10 + len(rep.heads)]:
            letter = get_column_letter(col)
            ws.cell(row=tr, column=col, value=f"=SUM({letter}2:{letter}{n + 1})").font = Font(bold=True)
    widths = {1: 6, 2: 12, 3: 18, 4: 30, 5: 14, 6: 14, 7: 9, 8: 9, 9: 10}
    for c in range(1, len(header) + 1):
        ws.column_dimensions[get_column_letter(c)].width = widths.get(c, 12)
    for row in ws.iter_rows(min_row=2, min_col=2, max_col=2):
        row[0].number_format = "DD-MM-YYYY"
    if rep.missing_codes:
        ws2 = wb.create_sheet("Not found")
        ws2.append(["Order codes with no saved BOM"])
        for c in rep.missing_codes:
            ws2.append([c])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def material_report_xlsx(rows: list[MaterialRow], title: str = "Consolidated by material") -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "By material"
    header = ["Material", "UOM", "Cost head", "Quantity", "Cost (PKR)", "Cost with wastage (PKR)", "Orders"]
    ws.append(header)
    _style_header(ws, len(header))
    for r in rows:
        ws.append([r.material_name, r.uom, r.cost_head, r.qty, r.total_pkr, r.total_with_wastage_pkr, r.orders])
    n = len(rows)
    if n:
        ws.cell(row=n + 2, column=1, value="Total").font = Font(bold=True)
        for col in (5, 6):
            letter = get_column_letter(col)
            ws.cell(row=n + 2, column=col, value=f"=SUM({letter}2:{letter}{n + 1})").font = Font(bold=True)
    for c, w in zip(range(1, 8), (40, 8, 14, 12, 14, 20, 8)):
        ws.column_dimensions[get_column_letter(c)].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
