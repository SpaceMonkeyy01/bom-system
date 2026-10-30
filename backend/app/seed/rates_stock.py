"""Seed BOM rates (from the Google Sheet price list) and iFlow stock snapshots (+ derived iFlow rates)."""

from __future__ import annotations

import re
from datetime import date

import openpyxl
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Material, MaterialExternalKey, MaterialRate, StockLine, StockSnapshot
from app.models.core import ExternalSystem, RateSource
from app.seed.common import RAW_DIR, clean, ensure_uoms, loose_key, norm_uom, to_date, to_float

BOM_SHEET_XLSX = RAW_DIR / "Bill_of_Materials__October-2026_to_Onward_.xlsx"
CATEGORIZATION_XLSX = RAW_DIR / "Categorization.xlsx"

# A few sheet names that clearly mean a specific Odoo material but don't match by text.
SHEET_NAME_OVERRIDES: dict[str, str] = {
    # sheet name -> Odoo internal reference
    "Tanaka Nozzle": "500193",
    "Paint Harnder": "502350",  # Nexa Hardner 922
    "Paint Hardner": "502350",
    "Paint Matt agent(Matt)": "502079",
    "Paint Mixing": "502098",  # Nexa 2k HS Jet Black (the colour base)
    "Paint Thinner": "501680",
    "Paint Binder(Gloss)": "502131",
    "Epoxy Primer": "502010",
    "Epoxy Thinner": "500214",
    "Epoxy Hardner": "502350",
    "Wire 18 Gauge (Red & white)": "502206",
    "Led Strips UL 6500k China": "501842",
    "SS Metal 14 g": "500425",
    "SS metal 26 g": "500591",
    "Aluminium 10 g": "501803",
    "Aluminium 14 g": "501060",
    "Acrylic White 8mm": "501408",
}


def _material_index(db: Session) -> tuple[dict[str, Material], dict[str, Material]]:
    by_key: dict[str, Material] = {}
    for m in db.scalars(select(Material)):
        by_key.setdefault(loose_key(m.name), m)
    by_odoo = {k.external_id: k.material for k in db.scalars(select(MaterialExternalKey).where(MaterialExternalKey.system == ExternalSystem.odoo))}
    return by_key, by_odoo


def _sheet_material(db: Session, name: str, uom_code: str, by_key: dict[str, Material], uoms) -> Material:
    """A material that only exists as a Google-Sheet price-list name. Created for review and merge later."""
    k = loose_key(name)
    m = by_key.get(k)
    if m:
        return m
    m = Material(name=name, uom=uoms[uom_code], review_status="to_review", notes="Created from the Google Sheet price list; merge with the Odoo material if one exists")
    db.add(m)
    db.flush()
    db.add(MaterialExternalKey(material=m, system=ExternalSystem.sheet, store="", external_id=name, external_name=name))
    by_key[k] = m
    return m


def seed_bom_rates(db: Session, path=BOM_SHEET_XLSX) -> dict:
    """Inventory Items Detail: U:W = prices as of 2025-06-01, AG:AI = prices as of 2025-09-01 (name, price, uom)."""
    uoms = ensure_uoms(db)
    by_key, by_odoo = _material_index(db)
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Inventory Items Detail"]
    rows = list(ws.iter_rows(min_row=1, max_row=400, values_only=True))
    blocks = [(20, 21, 22, date(2025, 6, 1)), (32, 33, 34, date(2025, 9, 1))]  # 0-based: U,V,W and AG,AH,AI
    existing = {
        (r.material_id, r.source.value, r.effective_from): r
        for r in db.scalars(select(MaterialRate).where(MaterialRate.source == RateSource.bom))
    }
    stats = {"rates": 0, "sheet_materials_created": 0, "matched_odoo": 0, "skipped": 0}
    before = db.scalar(select(Material).where(Material.review_status == "to_review").limit(1))  # noqa: F841
    for ni, pi, ui, eff in blocks:
        for r in rows[2:]:
            name = clean(r[ni]) if len(r) > ni else None
            price = to_float(r[pi]) if len(r) > pi else None
            if not name or price is None:
                stats["skipped"] += 1
                continue
            uom_code = norm_uom(clean(r[ui]) if len(r) > ui else None)
            mat = None
            if name in SHEET_NAME_OVERRIDES:
                mat = by_odoo.get(SHEET_NAME_OVERRIDES[name])
            if mat is None:
                mat = by_key.get(loose_key(name))
            if mat is not None and any(k.system == ExternalSystem.odoo for k in mat.external_keys):
                stats["matched_odoo"] += 1
            if mat is None:
                mat = _sheet_material(db, name, uom_code, by_key, uoms)
                stats["sheet_materials_created"] += 1
            # keep the sheet name reachable for the regression/import of old BOM lines
            if not any(k.system == ExternalSystem.sheet and k.external_id == name for k in mat.external_keys):
                db.add(MaterialExternalKey(material=mat, system=ExternalSystem.sheet, store="", external_id=name, external_name=name))
                db.flush()
            key = (mat.id, "bom", eff)
            if key in existing:
                existing[key].rate = price
                continue
            rate = MaterialRate(material=mat, source=RateSource.bom, store="", rate=price, effective_from=eff, note="Google Sheet: Inventory Items Detail")
            rate.uom_id = uoms[uom_code].id
            db.add(rate)
            existing[key] = rate
            stats["rates"] += 1
    db.flush()
    return stats


_STOCK_HEADER = ("Id", "Product Name", "Unit", "Op Qty", "Received", "Issued", "Balance")


def import_stock_rows(
    db: Session, store: str, snapshot_date: date, rows: list[tuple], source_file: str | None = None, cols: dict | None = None
) -> StockSnapshot:
    """Generic iFlow 'MAIN STORE STOCK SUMMARY' importer. `cols` maps field -> index in each row.
    Matching: (store, Id) external key, then exact normalised name within that store, else unmatched."""
    cols = cols or {"id": 0, "name": 1, "unit": 2, "op_qty": 3, "received": 4, "issued": 5, "balance": 6, "op_amt": 7, "bal_amt": 10}
    snap = db.scalar(select(StockSnapshot).where(StockSnapshot.store == store, StockSnapshot.snapshot_date == snapshot_date))
    if snap:
        for ln in list(snap.lines):
            db.delete(ln)
        for r in db.scalars(select(MaterialRate).where(MaterialRate.snapshot_id == snap.id)):
            db.delete(r)
        db.flush()
    else:
        snap = StockSnapshot(store=store, snapshot_date=snapshot_date, source_file=source_file)
        db.add(snap)
        db.flush()

    key_map = {
        k.external_id: k.material
        for k in db.scalars(select(MaterialExternalKey).where(MaterialExternalKey.system == ExternalSystem.iflow, MaterialExternalKey.store == store))
    }
    name_map: dict[str, Material] = {}
    for k in db.scalars(select(MaterialExternalKey).where(MaterialExternalKey.system == ExternalSystem.iflow, MaterialExternalKey.store == store)):
        if k.material.active:
            name_map.setdefault(loose_key(k.external_name or k.material.name), k.material)
    for m in db.scalars(select(Material).where(Material.active.is_(True))):  # never match a retired/merged material by name
        name_map.setdefault(loose_key(m.name), m)

    n = unmatched = 0
    for r in rows:
        rid = r[cols["id"]] if cols["id"] < len(r) else None
        name = clean(r[cols["name"]]) if cols["name"] < len(r) else None
        if rid in (None, "") or not name or not re.match(r"^\d+(\.0)?$", str(rid)):
            continue
        rid = str(int(float(rid)))
        mat = key_map.get(rid)
        method = "key" if mat else None
        if not mat:
            mat = name_map.get(loose_key(name))
            method = "name" if mat else None
        op_qty, received, issued, balance = (to_float(r[cols[k]]) if cols[k] < len(r) else None for k in ("op_qty", "received", "issued", "balance"))
        op_amt = to_float(r[cols["op_amt"]]) if cols.get("op_amt") is not None and cols["op_amt"] < len(r) else None
        bal_amt = to_float(r[cols["bal_amt"]]) if cols.get("bal_amt") is not None and cols["bal_amt"] < len(r) else None
        db.add(
            StockLine(
                snapshot=snap,
                material_id=mat.id if mat else None,
                external_id=rid,
                external_name=name,
                unit=clean(r[cols["unit"]]) if cols["unit"] < len(r) else None,
                op_qty=op_qty,
                received=received,
                issued=issued,
                balance=balance,
                op_amount=op_amt,
                balance_amount=bal_amt,
                match_method=method,
            )
        )
        n += 1
        if mat is None:
            unmatched += 1
            continue
        # derived iFlow rate: prefer balance amount / balance, else opening amount / opening qty
        rate = None
        if bal_amt and balance and balance > 0:
            rate = bal_amt / balance
        elif op_amt and op_qty and op_qty > 0:
            rate = op_amt / op_qty
        if rate and rate > 0:
            db.add(MaterialRate(material=mat, source=RateSource.iflow, store=store, rate=round(rate, 4), uom_id=mat.uom_id, effective_from=snapshot_date, snapshot_id=snap.id, note=f"iFlow {store} stock summary"))
    snap.row_count = n
    snap.unmatched_count = unmatched
    db.flush()
    return snap


def seed_stock(db: Session) -> dict:
    """Two snapshots we have on file: BS from the BOM sheet (28/10/2026) and NS from Categorization (15/01/2026)."""
    out = {}
    wb = openpyxl.load_workbook(BOM_SHEET_XLSX, read_only=True, data_only=True)
    ws = wb["Inventory Stock"]
    rows = list(ws.iter_rows(values_only=True))
    hdr = str(rows[0][2] or "")
    m = re.search(r"To (\d{2}/\d{2}/\d{4})", hdr)
    d = to_date(m.group(1)) if m else date(2026, 10, 28)
    snap = import_stock_rows(db, "BS", d, rows[2:], source_file="Bill_of_Materials / Inventory Stock")
    out["BS"] = (str(d), snap.row_count, snap.unmatched_count)

    wb2 = openpyxl.load_workbook(CATEGORIZATION_XLSX, read_only=True, data_only=True)
    ws2 = wb2["Ali Neon Data"]
    rows2 = list(ws2.iter_rows(values_only=True))
    hdr2 = str(rows2[0][9] or "")
    m2 = re.search(r"To (\d{2}-\d{2}-\d{4})", hdr2)
    d2 = to_date(m2.group(1)) if m2 else date(2026, 1, 15)
    cols = {"id": 7, "name": 8, "unit": 9, "op_qty": 10, "received": 11, "issued": 12, "balance": 13, "op_amt": None, "bal_amt": None}
    snap2 = import_stock_rows(db, "NS", d2, rows2[2:], source_file="Categorization / Ali Neon Data", cols=cols)
    out["NS"] = (str(d2), snap2.row_count, snap2.unmatched_count)
    return out
