"""Import the Google Sheet's October BOM blocks as read-only BOM records, so reports cover the whole month
from day one and the team can compare old and new costings side by side.

Each sheet block becomes BOM(status="imported", source="sheet-import") with one BOMLine per sheet line
(quantity, unit cost and total exactly as the sheet had them) and the sheet's own summary row as
by_cost_head / grand total (which includes the sheet's ×1.2 metal/acrylic uplift and the Misc constant).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BOM, BOMLine, Material, MaterialExternalKey, Order
from app.models.core import ExternalSystem
from app.seed.common import RAW_DIR, loose_key, norm_uom
from app.seed.sheet_blocks import Block, parse_blocks

BOM_SHEET_XLSX = RAW_DIR / "Bill_of_Materials__October-2026_to_Onward_.xlsx"
OCTOBER_SHEETS = ["October-BOM-2026", "October_Remaining"]

# sheet "Item Category" -> cost head name used by the app
CATEGORY_TO_HEAD = {
    "Metal": "Metal",
    "Acrylic": "Acrylic",
    "LEDs": "LEDs",
    "Paint": "Paint",
    "Power Supply": "Power Supply",
    "Packaging": "Packaging",
    "Misc": "Misc",
    "UV": "UV",
    "Alucobond": "Alucobond",
    "PVD Coating": "PVD Coating",
    "Wires": "Wires",
    "Tanaka Nozzle": "Tanaka Nozzle",
}
SUMMARY_HEADS = list(CATEGORY_TO_HEAD.values())


def _material_lookup(db: Session):
    by_sheet = {k.external_id: k.material for k in db.scalars(select(MaterialExternalKey).where(MaterialExternalKey.system == ExternalSystem.sheet))}
    by_key: dict[str, Material] = {}
    for m in db.scalars(select(Material).where(Material.active.is_(True))):
        by_key.setdefault(loose_key(m.name), m)

    def find(name: str | None) -> Material | None:
        if not name:
            return None
        return by_sheet.get(name) or by_key.get(loose_key(name))

    return find


def import_block(db: Session, block: Block, order: Order, find, pkr_per_usd: float) -> BOM:
    bom = BOM(order_id=order.id, template_id=None, status="imported", source=f"sheet-import:{block.sheet}", version=0)
    bom.parameters = {p: (v if isinstance(v, (int, float, str)) else None) for p, v in block.param_cells.values()}
    s = block.summary
    bom.length_in = s.get("Width( Inches)") or order.width_in
    bom.width_in = s.get("Height (Inches)") or order.height_in
    bom.area_sqft = s.get("Total Area (Sign)Ft2")
    base = 0.0
    for i, ln in enumerate(block.lines):
        qty = float(ln.qty_value or 0.0)
        rate = float(ln.unit_cost_value or 0.0)
        total = float(ln.total_value if ln.total_value is not None else qty * rate)
        mat = find(ln.name)
        head = CATEGORY_TO_HEAD.get(ln.category or "", ln.category or "Misc")
        bom.lines.append(
            BOMLine(
                seq=i,
                component_line_id=None,
                material_id=mat.id if mat else None,
                material_name=ln.name or "?",
                cost_tag=ln.category,
                cost_head=head,
                uom=None,
                qty_formula=str(ln.qty_formula) if isinstance(ln.qty_formula, str) and str(ln.qty_formula).startswith("=") else None,
                qty_auto=qty,
                qty_final=qty,
                rate=rate,
                rate_source="sheet",
                rate_date=None,
                rate_stale=False,
                wastage_pct=0.0,  # the sheet applied its uplift in the summary row, not per line
                total_pkr=round(total, 2),
                total_with_wastage_pkr=round(total, 2),
            )
        )
        base += total
    by_head = {h: round(float(s.get(h, 0.0)), 2) for h in SUMMARY_HEADS if s.get(h)}
    grand = float(s.get("Total Inventory (PKR)") or sum(by_head.values()) or base)
    gap = round(grand - sum(by_head.values()), 2)
    if abs(gap) > 1:  # some sheet blocks have inconsistent summary formulas; keep the total Airtable saw, show the gap
        by_head["Other"] = gap
    bom.base_total_pkr = round(base, 2)
    bom.wastage_total_pkr = round(max(0.0, grand - base), 2)  # the sheet's uplift + Misc constant, in aggregate
    bom.misc_pct = 0.0
    bom.misc_total_pkr = 0.0
    bom.grand_total_pkr = round(grand, 2)
    bom.by_cost_head = by_head
    bom.pkr_per_usd = pkr_per_usd
    bom.material_cost_usd = round(grand / pkr_per_usd * 1.2, 2)
    bom.production_cost_usd = round(bom.material_cost_usd / 0.6, 2)
    bom.notes = f"Imported from the Google Sheet ({block.sheet}, row {block.header_row}). Sign type as typed: {block.sign_type}"
    bom.saved_at = datetime.now(timezone.utc)
    if isinstance(block.order_date, datetime):
        bom.saved_at = block.order_date.replace(tzinfo=timezone.utc)
    return bom


def import_october_boms(db: Session, path=BOM_SHEET_XLSX, sheets: list[str] | None = None) -> dict:
    """Idempotent: a block already imported (same order + source + header row) is skipped."""
    from app.config import settings

    find = _material_lookup(db)
    orders = {o.code.strip(): o for o in db.scalars(select(Order))}
    existing = {(b.order_id, b.notes) for b in db.scalars(select(BOM).where(BOM.status == "imported"))}
    stats = {"blocks": 0, "imported": 0, "skipped_existing": 0, "no_order": [], "lines": 0, "unmatched_materials": {}}
    for sheet in sheets or OCTOBER_SHEETS:
        for block in parse_blocks(path, sheet):
            stats["blocks"] += 1
            code = (block.order_code or "").strip()
            order = orders.get(code)
            if not order:
                stats["no_order"].append(code or f"(blank @ {sheet} row {block.header_row})")
                continue
            bom = import_block(db, block, order, find, settings.pkr_per_usd)
            if (order.id, bom.notes) in existing:
                stats["skipped_existing"] += 1
                continue
            last = db.scalar(select(BOM.version).where(BOM.order_id == order.id).order_by(BOM.version.desc()))
            bom.version = (last or 0) + 1
            db.add(bom)
            db.flush()
            existing.add((order.id, bom.notes))
            stats["imported"] += 1
            stats["lines"] += len(bom.lines)
            for ln in bom.lines:
                if ln.material_id is None:
                    stats["unmatched_materials"][ln.material_name] = stats["unmatched_materials"].get(ln.material_name, 0) + 1
    db.flush()
    return stats
