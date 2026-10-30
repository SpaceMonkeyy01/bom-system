"""Export the team's data-cleanup to-do list as one workbook, and import the decisions back.

    python scripts/cleanup_workbook.py export  [out.xlsx]
    python scripts/cleanup_workbook.py apply   decisions.xlsx [--dry-run]

Sheets (each has a yellow "Decision" column the team fills in; everything else is read-only context):

  Sheet-only materials  171 price-list names created at seed time that probably duplicate an Odoo/iFlow
                        material. Decision = material id to merge into, "keep" (it is a real new material)
                        or "ignore" (deactivate; nothing uses it).
  Unmapped sign types   Airtable sign-type names that match no template. Decision = existing sign-type
                        name to alias to, or "new" to create a sign type of that name.
  Price list            Every material a template uses, with its current bom rate (dated), the latest
                        iFlow rate per store and the sheet's unit. Decision = new rate (PKR per unit).
  Flagged lines         Template lines the import could not resolve or parse. No import — fix these in the
                        template editor; the sheet is just the work list.
  Duplicate iFlow ids   Odoo rows sharing one iFlow id (first claim won). Decision = material id that
                        really owns the id, if different.

Decisions are applied through the same service functions the UI uses (merge_materials, add_rate, aliases),
so the result is identical to doing it by hand in the app.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openpyxl import Workbook, load_workbook  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import BOMLine, ComponentLine, Material, MaterialExternalKey, MaterialRate, Order, SignType, Template  # noqa: E402
from app.models.core import ExternalSystem, RateSource  # noqa: E402
from app.seed.common import loose_key  # noqa: E402

DECISION_FILL = PatternFill("solid", fgColor="FFF2CC")
HEADER_FILL = PatternFill("solid", fgColor="DDE7F0")


# ----------------------------------------------------------------------------- helpers


def _tokens(name: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (name or "").lower()) if len(t) > 1}


def _suggest(name: str, pool: list[tuple[int, str, str | None, str | None]], n: int = 3) -> list[tuple[int, str, str | None, str | None]]:
    """Rank candidate materials by shared name tokens; exact loose-key match first."""
    lk = loose_key(name)
    toks = _tokens(name)
    scored = []
    for mid, mname, uom, cat in pool:
        if loose_key(mname) == lk:
            scored.append((99, mid, mname, uom, cat))
            continue
        shared = toks & _tokens(mname)
        words = [t for t in shared if not t.isdigit()]
        if words:  # at least one real word in common; numbers alone ("3000") are not a match
            score = len(words) + 0.5 * (len(shared) - len(words))
            scored.append((score / max(len(toks), 1) + score * 0.01, mid, mname, uom, cat))
    scored.sort(key=lambda s: -s[0])
    return [(m, nm, u, c) for _, m, nm, u, c in scored[:n]]


def _sheet(wb: Workbook, title: str, header: list[str], widths: list[int], decision_cols: list[int], note: str) -> "Worksheet":  # noqa: F821
    ws = wb.create_sheet(title)
    ws.append([note])
    ws.cell(row=1, column=1).font = Font(italic=True, color="555555")
    ws.append(header)
    for c in range(1, len(header) + 1):
        cell = ws.cell(row=2, column=c)
        cell.font = Font(bold=True)
        cell.fill = DECISION_FILL if c in decision_cols else HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(c)].width = widths[c - 1] if c - 1 < len(widths) else 14
    ws.freeze_panes = "A3"
    ws._decision_cols = decision_cols  # type: ignore[attr-defined]
    return ws


def _append(ws, row: list) -> None:
    ws.append(row)
    for c in ws._decision_cols:  # type: ignore[attr-defined]
        ws.cell(row=ws.max_row, column=c).fill = DECISION_FILL


# ----------------------------------------------------------------------------- export


def export(path: Path) -> None:
    db = SessionLocal()
    wb = Workbook()
    wb.remove(wb.active)

    readme = wb.create_sheet("README")
    for line in __doc__.strip().splitlines()[2:]:
        readme.append([line])
    readme.column_dimensions["A"].width = 120

    # --- usage counts
    tpl_use = dict(db.execute(select(ComponentLine.material_id, func.count()).where(ComponentLine.material_id.is_not(None)).group_by(ComponentLine.material_id)).all())
    bom_use = dict(db.execute(select(BOMLine.material_id, func.count()).where(BOMLine.material_id.is_not(None)).group_by(BOMLine.material_id)).all())
    mats = list(db.scalars(select(Material).options(selectinload(Material.uom), selectinload(Material.category), selectinload(Material.external_keys), selectinload(Material.rates)).where(Material.active.is_(True))))
    pool = [(m.id, m.name, m.uom.code if m.uom else None, m.category.path if m.category else None) for m in mats if not any(k.system == ExternalSystem.sheet for k in m.external_keys)]

    def latest_rate(m: Material, source: RateSource, store: str = "") -> MaterialRate | None:
        rs = [r for r in m.rates if r.source == source and (not store or r.store == store) and r.effective_from <= date.today()]
        return max(rs, key=lambda r: (r.effective_from, r.id)) if rs else None

    # --- 1. sheet-only materials
    ws = _sheet(
        wb,
        "Sheet-only materials",
        ["Material id", "Sheet name", "Unit", "BOM rate (PKR)", "Used in templates (lines)", "Used in Oct BOMs (lines)", "Suggestion 1", "Suggestion 2", "Suggestion 3", "Decision (merge into id / keep / ignore)", "Comment"],
        [10, 45, 8, 12, 12, 12, 45, 45, 45, 24, 30],
        [10, 11],
        "Each row is a price-list name the seed could not match to an Odoo/iFlow material. If one of the suggestions (shown as 'id · name · unit · category') is the same thing, put its id in Decision.",
    )
    for m in sorted(mats, key=lambda m: m.name.lower()):
        if m.review_status != "to_review" or not any(k.system == ExternalSystem.sheet for k in m.external_keys):
            continue
        br = latest_rate(m, RateSource.bom)
        sugg = _suggest(m.name, pool)
        cells = [f"{mid} · {nm} · {u or '-'} · {c or '-'}" for mid, nm, u, c in sugg] + [""] * (3 - len(sugg))
        _append(ws, [m.id, m.name, m.uom.code if m.uom else None, float(br.rate) if br else None, tpl_use.get(m.id, 0), bom_use.get(m.id, 0), *cells, "", ""])

    # --- 2. unmapped sign types
    ws = _sheet(
        wb,
        "Unmapped sign types",
        ["Airtable sign type", "Orders", "Example order codes", "Suggested sign type", "Decision (sign-type name / new)", "Comment"],
        [50, 8, 40, 40, 30, 30],
        [5, 6],
        "Orders whose Airtable 'Sign Type' matches no template. Pick the existing template name to alias it to (orders re-map automatically), or write 'new'.",
    )
    sign_types = list(db.scalars(select(SignType).where(SignType.active.is_(True)).order_by(SignType.name)))
    st_pool = [(s.id, s.name, None, None) for s in sign_types]
    groups: dict[str, list[Order]] = defaultdict(list)
    for o in db.scalars(select(Order).where(Order.sign_type_id.is_(None), Order.sign_type_raw.is_not(None)).order_by(Order.order_date.desc())):
        groups[o.sign_type_raw.strip()].append(o)
    for raw, orders in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        sugg = _suggest(raw, st_pool, n=2)
        _append(ws, [raw, len(orders), ", ".join(o.code for o in orders[:5]), " | ".join(nm for _, nm, _, _ in sugg), "", ""])
    ws.append([])
    ws.append(["Existing sign types:", ", ".join(s.name for s in sign_types)])

    # --- 3. price list
    ws = _sheet(
        wb,
        "Price list",
        ["Material id", "Material", "Unit", "Category", "BOM rate (PKR)", "BOM rate date", "iFlow BS rate", "iFlow BS date", "iFlow NS rate", "iFlow NS date", "Templates using it", "New BOM rate (PKR per unit)", "Supplier (optional)", "Comment"],
        [10, 45, 8, 35, 12, 12, 12, 12, 12, 12, 10, 16, 24, 30],
        [12, 13, 14],
        "Every material a template references, sorted by how many templates use it. The sheet's rates are from 2025-09 and count as stale; enter today's rate per unit in the yellow column (leave blank to keep the current one).",
    )
    used = [m for m in mats if tpl_use.get(m.id)]
    used.sort(key=lambda m: (-tpl_use.get(m.id, 0), m.name.lower()))
    for m in used:
        br, bs, ns = latest_rate(m, RateSource.bom), latest_rate(m, RateSource.iflow, "BS"), latest_rate(m, RateSource.iflow, "NS")
        _append(ws, [m.id, m.name, m.uom.code if m.uom else None, m.category.path if m.category else None, float(br.rate) if br else None, br.effective_from if br else None, float(bs.rate) if bs else None, bs.effective_from if bs else None, float(ns.rate) if ns else None, ns.effective_from if ns else None, tpl_use.get(m.id, 0), "", "", ""])

    # --- 4. flagged template lines (work list only)
    ws = _sheet(
        wb,
        "Flagged lines",
        ["Template", "Status", "Line #", "Material", "Qty formula", "Cost tag", "Problem", "Done?"],
        [40, 10, 7, 40, 50, 14, 60, 8],
        [8],
        "Lines the import flagged. Fix them in the template editor (Templates → sign type → draft); tick Done here to keep track. 'no formula in source' means the sheet row had a typed number instead of a formula — decide whether it should be a formula or a fixed quantity.",
    )
    tpls = list(db.scalars(select(Template).options(selectinload(Template.sign_type), selectinload(Template.lines)).order_by(Template.sign_type_id, Template.version)))
    for t in tpls:
        for ln in sorted(t.lines, key=lambda l: l.seq):
            if ln.notes:
                mat = db.get(Material, ln.material_id) if ln.material_id else None
                _append(ws, [f"{t.sign_type.name} v{t.version}", t.status, ln.seq, mat.name if mat else (ln.material_name_hint or "?"), ln.qty_formula, ln.cost_tag, ln.notes, ""])

    # --- 5. duplicate iFlow ids
    ws = _sheet(
        wb,
        "Duplicate iFlow ids",
        ["Store", "iFlow id", "Owner material id", "Owner material", "Other material id", "Other material (flagged)", "Decision (correct owner id)", "Comment"],
        [6, 10, 10, 45, 10, 45, 18, 30],
        [7, 8],
        "Two Odoo products carried the same iFlow id; the first one seen kept it. If the other one is the real owner, put its id in Decision and the key (and its stock/rate) moves over.",
    )
    pat = re.compile(r"Duplicate: iflow (\w+) (\d+) already belongs to material #(\d+)")
    for m in mats:
        for note in (m.notes or "").split("\n"):
            mm = pat.search(note)
            if mm:
                owner = db.get(Material, int(mm.group(3)))
                _append(ws, [mm.group(1), int(mm.group(2)), owner.id if owner else None, owner.name if owner else "?", m.id, m.name, "", ""])

    wb.save(path)
    counts = {s.title: max(s.max_row - 2, 0) for s in wb.worksheets if s.title != "README"}
    print(f"wrote {path}: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    db.close()


# ----------------------------------------------------------------------------- apply


def _rows(ws):
    header = [str(c.value or "").strip() for c in ws[2]]
    for r in ws.iter_rows(min_row=3, values_only=True):
        if not any(v not in (None, "") for v in r):
            continue
        yield dict(zip(header, r))


def apply(path: Path, dry_run: bool) -> None:
    from app.services.inventory import add_rate, merge_materials

    db = SessionLocal()
    wb = load_workbook(path, data_only=True)
    log: list[str] = []

    def dec(row: dict, key_prefix: str) -> str:
        for k, v in row.items():
            if k.startswith(key_prefix):
                return str(v).strip() if v not in (None, "") else ""
        return ""

    if "Sheet-only materials" in wb.sheetnames:
        for row in _rows(wb["Sheet-only materials"]):
            d = dec(row, "Decision").lower()
            if not d:
                continue
            drop = db.get(Material, int(row["Material id"]))
            if d == "keep":
                drop.review_status = "done"
                log.append(f"keep   #{drop.id} {drop.name}")
            elif d == "ignore":
                drop.active, drop.review_status = False, "not_needed"
                log.append(f"ignore #{drop.id} {drop.name}")
            else:
                keep = db.get(Material, int(re.match(r"\d+", d).group()))
                moved = merge_materials(db, keep, drop)
                log.append(f"merge  #{drop.id} {drop.name} -> #{keep.id} {keep.name} {moved}")

    if "Unmapped sign types" in wb.sheetnames:
        for row in _rows(wb["Unmapped sign types"]):
            d = dec(row, "Decision")
            raw = row.get("Airtable sign type")
            if not d or not raw or raw == "Existing sign types:":
                continue
            if d.lower() == "new":
                st = SignType(name=raw, aliases=[])
                db.add(st)
                db.flush()
                log.append(f"new sign type #{st.id} {raw}")
            else:
                st = db.scalar(select(SignType).where(func.lower(SignType.name) == d.lower()))
                if not st:
                    log.append(f"!! sign type not found: {d!r} (for {raw!r})")
                    continue
                if raw not in st.aliases:
                    st.aliases = [*st.aliases, raw]
            n = db.execute(Order.__table__.update().where(Order.sign_type_id.is_(None), func.lower(Order.sign_type_raw) == raw.lower()).values(sign_type_id=st.id)).rowcount
            log.append(f"map    {raw!r} -> {st.name} ({n} orders)")

    if "Price list" in wb.sheetnames:
        for row in _rows(wb["Price list"]):
            d = dec(row, "New BOM rate")
            if not d:
                continue
            m = db.get(Material, int(row["Material id"]))
            rate = float(str(d).replace(",", ""))
            add_rate(db, m, source=RateSource.bom, rate=rate, effective_from=date.today(), user_id=None, note=f"cleanup workbook {row.get('Comment') or ''}".strip())
            log.append(f"rate   #{m.id} {m.name}: {rate}")

    if "Duplicate iFlow ids" in wb.sheetnames:
        for row in _rows(wb["Duplicate iFlow ids"]):
            d = dec(row, "Decision")
            if not d or int(d) == int(row["Owner material id"]):
                continue
            key = db.scalar(select(MaterialExternalKey).where(MaterialExternalKey.system == ExternalSystem.iflow, MaterialExternalKey.store == row["Store"], MaterialExternalKey.external_id == str(row["iFlow id"])))
            if key:
                key.material_id = int(d)
                log.append(f"iflow  {row['Store']} {row['iFlow id']}: owner -> #{d}")

    print("\n".join(log) or "nothing to apply")
    if dry_run:
        db.rollback()
        print(f"-- dry run, {len(log)} change(s) not saved")
    else:
        db.commit()
        print(f"-- applied {len(log)} change(s)")
    db.close()


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] not in ("export", "apply"):
        print(__doc__)
        sys.exit(1)
    if args[0] == "export":
        export(Path(args[1]) if len(args) > 1 else Path("bom_cleanup.xlsx"))
    else:
        apply(Path(args[1]), dry_run="--dry-run" in args)
