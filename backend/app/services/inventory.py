"""Inventory module services: iFlow file import, review queue actions, material/rate maintenance."""

from __future__ import annotations

import csv
import io
import re
from datetime import date

import openpyxl
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Material, MaterialExternalKey, MaterialRate, StockLine, StockSnapshot, Supplier, UOM
from app.models.core import ExternalSystem, RateSource
from app.seed.common import norm_uom, to_date
from app.seed.rates_stock import import_stock_rows

STOCK_HEADER_WORDS = ("id", "product name", "unit", "op qty", "received", "issued", "balance")


def parse_stock_file(filename: str, content: bytes) -> tuple[list[tuple], date | None, dict]:
    """Read an iFlow 'MAIN STORE STOCK SUMMARY' export (.xlsx/.xls or .csv).
    Returns (data rows, report date from the header, column map)."""
    if filename.lower().endswith((".xlsx", ".xlsm")):
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        rows = [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    else:
        text = content.decode("utf-8-sig", errors="replace")
        rows = [list(r) for r in csv.reader(io.StringIO(text))]
    # find the header row and its column positions
    header_idx, cols = None, None
    for i, r in enumerate(rows[:10]):
        cells = [str(c).strip().lower() if c is not None else "" for c in r]
        if "product name" in cells and "balance" in cells:
            header_idx = i
            idx: dict[str, int] = {}
            for j, name in enumerate(cells):
                if name:
                    idx.setdefault(name, j)  # first occurrence wins ("Balance" appears twice: qty, then amount)
            cols = {
                "id": idx.get("id", 0),
                "name": idx["product name"],
                "unit": idx.get("unit", idx["product name"] + 1),
                "op_qty": idx.get("op qty", idx["product name"] + 2),
                "received": idx.get("received", idx["product name"] + 3),
                "issued": idx.get("issued", idx["product name"] + 4),
                "balance": idx.get("balance", idx["product name"] + 5),
                "op_amt": idx.get("op amt"),
                "bal_amt": None,
            }
            # the second "balance" column (amount) sits after Dr/Cr
            bal_positions = [j for j, name in enumerate(cells) if name == "balance"]
            if len(bal_positions) > 1:
                cols["bal_amt"] = bal_positions[1]
            break
    if header_idx is None:
        raise ValueError("Could not find the stock summary header row (Id, Product Name, Unit, Op Qty, ...)")
    report_date = None
    for r in rows[:header_idx]:
        for c in r:
            if isinstance(c, str):
                m = re.search(r"To\s+(\d{1,2}[/-]\d{1,2}[/-]\d{4})", c)
                if m:
                    report_date = to_date(m.group(1).replace("-", "/")) or to_date(m.group(1))
    return rows[header_idx + 1 :], report_date, cols


def import_stock_file(db: Session, store: str, filename: str, content: bytes, snapshot_date: date | None, user_id: int | None) -> StockSnapshot:
    rows, report_date, cols = parse_stock_file(filename, content)
    d = snapshot_date or report_date
    if not d:
        raise ValueError("No report date in the file header; pass snapshot_date")
    snap = import_stock_rows(db, store, d, rows, source_file=filename, cols=cols)
    snap.imported_by = user_id
    db.flush()
    return snap


# ---------------------------------------------------------------- review queue


def unmatched_lines(db: Session, store: str | None = None, limit: int = 200) -> list[StockLine]:
    stmt = select(StockLine).join(StockLine.snapshot).where(StockLine.material_id.is_(None))
    if store:
        stmt = stmt.where(StockSnapshot.store == store)
    stmt = stmt.order_by(StockSnapshot.snapshot_date.desc(), StockLine.external_name).limit(limit)
    return list(db.scalars(stmt))


def suggest_matches(db: Session, line: StockLine, limit: int = 5) -> list[Material]:
    """Cheap fuzzy suggestions: materials sharing the most name tokens."""
    tokens = [t for t in re.split(r"[^a-z0-9]+", line.external_name.lower()) if len(t) > 2]
    if not tokens:
        return []
    stmt = select(Material).where(Material.active.is_(True))
    for t in tokens[:2]:
        stmt = stmt.where(Material.name.ilike(f"%{t}%"))
    cands = list(db.scalars(stmt.limit(50)))

    def score(m: Material) -> int:
        n = m.name.lower()
        return sum(1 for t in tokens if t in n)

    return sorted(cands, key=score, reverse=True)[:limit]


def link_line(db: Session, line: StockLine, material: Material, user_id: int | None) -> None:
    """Attach an unmatched stock line to a material and remember the (store, id) key for next time."""
    store = line.snapshot.store
    existing = db.scalar(select(MaterialExternalKey).where(MaterialExternalKey.system == ExternalSystem.iflow, MaterialExternalKey.store == store, MaterialExternalKey.external_id == line.external_id))
    if existing and existing.material_id != material.id:
        raise ValueError(f"iFlow {store} id {line.external_id} already belongs to material #{existing.material_id} ({existing.material.name})")
    if not existing:
        db.add(MaterialExternalKey(material=material, system=ExternalSystem.iflow, store=store, external_id=line.external_id, external_name=line.external_name))
    # apply to every unmatched line with this (store, id), across snapshots
    for ln in db.scalars(select(StockLine).join(StockLine.snapshot).where(StockLine.material_id.is_(None), StockLine.external_id == line.external_id, StockSnapshot.store == store)):
        ln.material_id = material.id
        ln.match_method = "manual"
        _derive_iflow_rate(db, ln, material)
        ln.snapshot.unmatched_count = max(0, (ln.snapshot.unmatched_count or 1) - 1)
    db.flush()


def create_material_from_line(db: Session, line: StockLine, category_id: int | None, user_id: int | None) -> Material:
    uom_code = norm_uom(line.unit)
    uom = db.scalar(select(UOM).where(UOM.code == uom_code))
    m = Material(name=line.external_name, category_id=category_id, uom=uom, active=True, review_status="to_review", notes=f"Created from iFlow {line.snapshot.store} import")
    db.add(m)
    db.flush()
    link_line(db, line, m, user_id)
    return m


def _derive_iflow_rate(db: Session, ln: StockLine, material: Material) -> None:
    rate = None
    if ln.balance_amount and ln.balance and float(ln.balance) > 0:
        rate = float(ln.balance_amount) / float(ln.balance)
    elif ln.op_amount and ln.op_qty and float(ln.op_qty) > 0:
        rate = float(ln.op_amount) / float(ln.op_qty)
    if rate and rate > 0:
        db.add(MaterialRate(material=material, source=RateSource.iflow, store=ln.snapshot.store, rate=round(rate, 4), uom_id=material.uom_id, effective_from=ln.snapshot.snapshot_date, snapshot_id=ln.snapshot_id, note=f"iFlow {ln.snapshot.store} stock summary"))


# ---------------------------------------------------------------- rates & suppliers


def add_rate(db: Session, material: Material, source: RateSource, rate: float, effective_from: date, user_id: int | None, supplier_id: int | None = None, store: str = "", note: str | None = None) -> MaterialRate:
    if rate < 0:
        raise ValueError("Rate can't be negative")
    if source == RateSource.supplier and not supplier_id:
        raise ValueError("A supplier rate needs a supplier")
    if source == RateSource.supplier and not db.get(Supplier, supplier_id):
        raise ValueError("Supplier not found")
    r = MaterialRate(material=material, source=source, store=store or "", supplier_id=supplier_id, rate=rate, uom_id=material.uom_id, effective_from=effective_from, created_by=user_id, note=note)
    db.add(r)
    db.flush()
    return r


def merge_materials(db: Session, keep: Material, drop: Material) -> dict:
    """Fold a duplicate (e.g. a sheet-only material) into the real one: keys, rates, stock lines, template lines, BOM lines.
    The dropped material is deactivated, not deleted, because saved BOM lines may name it."""
    from app.models import BOMLine, ComponentLine

    if keep.id == drop.id:
        raise ValueError("Pick two different materials")
    moved = {"keys": 0, "rates": 0, "stock_lines": 0, "template_lines": 0, "bom_lines": 0}
    have = {(k.system, k.store, k.external_id) for k in keep.external_keys}
    for k in list(drop.external_keys):
        if (k.system, k.store, k.external_id) in have:
            db.delete(k)
        else:
            k.material_id = keep.id
            moved["keys"] += 1
    for r in db.scalars(select(MaterialRate).where(MaterialRate.material_id == drop.id)):
        r.material_id = keep.id
        moved["rates"] += 1
    for ln in db.scalars(select(StockLine).where(StockLine.material_id == drop.id)):
        ln.material_id = keep.id
        moved["stock_lines"] += 1
    for ln in db.scalars(select(ComponentLine).where(ComponentLine.material_id == drop.id)):
        ln.material_id = keep.id
        ln.material_name_hint = keep.name
        moved["template_lines"] += 1
    for ln in db.scalars(select(BOMLine).where(BOMLine.material_id == drop.id)):
        ln.material_id = keep.id  # frozen name/rate stay as they were
        moved["bom_lines"] += 1
    drop.active = False
    drop.review_status = "merged"
    drop.notes = f"Merged into material #{keep.id} ({keep.name})"
    db.flush()
    return moved
