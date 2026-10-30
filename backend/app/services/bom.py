"""BOM generation: order + template version + parameters -> costed, frozen lines."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.engine.formula import LineSpec, ParamSpec, calculate, norm_tag, order_vars
from app.models import BOM, BOMLine, CostHead, Order, Template, UOM
from app.services.rates import RateResolver

MISC_PCT_DEFAULT = 10.0  # % of total-with-wastage, applied as one automatic line (prototype default)


@dataclass
class ExtraLine:
    material_id: int | None
    name: str
    qty: float
    unit_cost: float | None  # None -> resolve from rates
    cost_tag: str | None = None
    uom: str | None = None
    note: str | None = None


@dataclass
class BOMRequest:
    order_id: int
    template_id: int | None = None  # default: the sign type's published template
    template: Any = None  # an in-memory Template (unsaved editor state) takes precedence; never persisted
    parameters: dict[str, Any] = field(default_factory=dict)
    overrides: dict[int, float] = field(default_factory=dict)  # component_line_id -> qty
    override_notes: dict[int, str] = field(default_factory=dict)
    extras: list[ExtraLine] = field(default_factory=list)
    misc_pct: float | None = None
    box_dimension: str | None = None
    est_shipment_cost_usd: float | None = None
    notes: str | None = None
    as_of: date | None = None


def _cost_head_index(db: Session) -> dict[str, CostHead]:
    idx: dict[str, CostHead] = {}
    for h in db.scalars(select(CostHead)):
        idx[norm_tag(h.name)] = h
        for a in h.aliases or []:
            idx.setdefault(norm_tag(a), h)
    return idx


def default_parameters(order: Order, template: Template) -> dict[str, Any]:
    """Pre-fill parameter values from the order (finish today; more as templates declare them)."""
    out: dict[str, Any] = {}
    for p in template.parameters:
        if p.default_value not in (None, ""):
            out[p.param_name] = p.default_value
        if p.default_from_order == "finish" and order.finish:
            f = order.finish.lower()
            for opt in p.options or []:
                if opt.lower()[:4] in f:  # "Matte" -> Matt, "Satin Finish" -> Satin, "Glossy" -> Gloss
                    out[p.param_name] = opt
                    break
        elif p.default_from_order == "width_in" and order.width_in is not None:
            out[p.param_name] = float(order.width_in)
        elif p.default_from_order == "height_in" and order.height_in is not None:
            out[p.param_name] = float(order.height_in)
    return out


def pick_template(db: Session, order: Order, template_id: int | None) -> Template:
    if template_id:
        t = db.get(Template, template_id)
        if not t:
            raise ValueError(f"Template {template_id} not found")
        return t
    if not order.sign_type_id:
        raise ValueError(f"Order {order.code} has no sign type mapped; choose a template explicitly")
    t = db.scalar(select(Template).where(Template.sign_type_id == order.sign_type_id, Template.status == "published").order_by(Template.version.desc()))
    if not t:
        t = db.scalar(select(Template).where(Template.sign_type_id == order.sign_type_id).order_by(Template.version.desc()))
    if not t:
        raise ValueError(f"No template for sign type '{order.sign_type.name}'")
    return t


def build_bom(db: Session, req: BOMRequest) -> BOM:
    """Compute a BOM in memory (not added to the session). Call save_bom() to persist it."""
    order = db.get(Order, req.order_id)
    if not order:
        raise ValueError(f"Order {req.order_id} not found")
    template = req.template or pick_template(db, order, req.template_id)
    resolver = RateResolver(db, req.as_of)
    heads = _cost_head_index(db)

    params = [ParamSpec(p.param_name, p.input_type, p.options or []) for p in template.parameters]
    raw = {**default_parameters(order, template), **(req.parameters or {})}

    # one LineSpec per template line; unit cost = resolved rate unless the line has a cost formula
    specs: list[LineSpec] = []
    resolved: dict[int, Any] = {}
    for ln in template.lines:
        unit_cost: float | str | None
        if ln.unit_cost_formula:
            unit_cost = ln.unit_cost_formula
        elif ln.material is not None:
            line_uom = db.scalar(select(UOM.id).where(UOM.code == ln.uom)) if ln.uom else ln.material.uom_id
            rr = resolver.resolve(ln.material, line_uom)
            resolved[ln.id] = rr
            unit_cost = rr.rate
        else:
            unit_cost = 0.0
        specs.append(LineSpec(ln.id, ln.material.name if ln.material else (ln.material_name_hint or "?"), ln.qty_formula, unit_cost, ln.cost_tag, ln.uom, ln.usage, ln.work_centre, ln.wastage_pct))

    extra_tuples = []
    extra_resolved = []
    for x in req.extras:
        uc = x.unit_cost
        rr = None
        if uc is None and x.material_id:
            from app.models import Material  # local import to keep module import light

            m = db.get(Material, x.material_id)
            if m:
                rr = resolver.resolve(m)
                uc = rr.rate
        extra_resolved.append((x, uc or 0.0, rr))
        extra_tuples.append((x.cost_tag or "Misc", x.qty, uc or 0.0))

    res = calculate(params, specs, raw, extra_vars=order_vars(order.width_in, order.height_in), overrides=req.overrides or {}, extra_lines=extra_tuples)

    bom = BOM(order_id=order.id, template_id=template.id, parameters=raw, status="draft", source="app", version=0)
    bom.length_in = order.width_in
    bom.width_in = order.height_in
    ov = order_vars(order.width_in, order.height_in)
    bom.area_sqft = ov["Area_sqft"]
    bom.pkr_per_usd = settings.pkr_per_usd
    bom.box_dimension = req.box_dimension
    bom.est_shipment_cost_usd = req.est_shipment_cost_usd
    bom.notes = req.notes

    by_head: dict[str, float] = {}
    base = waste = 0.0
    seq = 0
    line_by_id = {ln.id: ln for ln in template.lines}
    for r in res.lines:
        ln = line_by_id[r.key]
        head = heads.get(norm_tag(ln.cost_tag))
        head_name = head.name if head else (ln.cost_tag or "Misc")
        w = float(ln.wastage_pct) if ln.wastage_pct is not None else (float(head.default_wastage_pct) if head else 0.0)
        rr = resolved.get(ln.id)
        total = r.total
        tww = total * (1 + w / 100)
        bl = BOMLine(
            seq=seq,
            component_line_id=ln.id if ln.id and ln.id > 0 else None,  # transient preview lines carry negative ids
            material_id=ln.material_id,
            material_name=r.name,
            usage=ln.usage,
            cost_tag=ln.cost_tag,
            cost_head=head_name,
            work_centre=ln.work_centre,
            uom=ln.uom,
            qty_formula=ln.qty_formula,
            qty_auto=r.qty_auto,
            qty_final=r.qty_final,
            override_note=(req.override_notes or {}).get(ln.id) if r.overridden else None,
            rate=r.unit_cost,
            rate_source="formula" if r.unit_cost_is_formula else (rr.source if rr else "none"),
            rate_date=rr.effective_from if rr else None,
            rate_stale=bool(rr.stale) if rr else (not r.unit_cost_is_formula),
            wastage_pct=w,
            total_pkr=round(total, 2),
            total_with_wastage_pkr=round(tww, 2),
            error=r.error,
            rate_uom=rr.uom if rr else None,
            warning=(
                f"Rate is per {rr.uom} but the line is in {ln.uom or (ln.material.uom.code if ln.material and ln.material.uom else '?')}; check the unit"
                if rr and rr.uom_mismatch
                else (
                    "No rate found for this material"
                    if rr and rr.source == "none"
                    else (f"Rate converted from per-{rr.converted_from}" if rr and rr.converted_from else None)
                )
            ),
        )
        bom.lines.append(bl)
        seq += 1
        base += total
        waste += tww - total
        by_head[head_name] = by_head.get(head_name, 0.0) + tww
    for x, uc, rr in extra_resolved:
        head = heads.get(norm_tag(x.cost_tag))
        head_name = head.name if head else (x.cost_tag or "Misc")
        w = float(head.default_wastage_pct) if head else 0.0
        total = x.qty * uc
        tww = total * (1 + w / 100)
        bom.lines.append(
            BOMLine(seq=seq, component_line_id=None, material_id=x.material_id, material_name=x.name, cost_tag=x.cost_tag, cost_head=head_name, uom=x.uom, qty_auto=None, qty_final=x.qty, override_note=x.note, rate=uc, rate_source=rr.source if rr else "manual", rate_date=rr.effective_from if rr else None, rate_stale=bool(rr.stale) if rr else False, wastage_pct=w, total_pkr=round(total, 2), total_with_wastage_pkr=round(tww, 2))
        )
        seq += 1
        base += total
        waste += tww - total
        by_head[head_name] = by_head.get(head_name, 0.0) + tww

    misc_pct = MISC_PCT_DEFAULT if req.misc_pct is None else float(req.misc_pct)
    inventory_total = base + waste
    misc_total = inventory_total * misc_pct / 100
    if misc_total:
        by_head["Misc"] = by_head.get("Misc", 0.0) + misc_total
    bom.base_total_pkr = round(base, 2)
    bom.wastage_total_pkr = round(waste, 2)
    bom.misc_pct = misc_pct
    bom.misc_total_pkr = round(misc_total, 2)
    bom.grand_total_pkr = round(inventory_total + misc_total, 2)
    bom.by_cost_head = {k: round(v, 2) for k, v in by_head.items()}
    # today's rule from the sheet: material $ = total/rate * 1.2 ; production $ = material / 0.6
    bom.material_cost_usd = round(bom.grand_total_pkr / bom.pkr_per_usd * 1.2, 2)
    bom.production_cost_usd = round(bom.material_cost_usd / 0.6, 2)
    bom._input_errors = res.input_errors  # type: ignore[attr-defined]  (transient, for the API response)
    return bom


def save_bom(db: Session, bom: BOM, user_id: int | None = None) -> BOM:
    """Persist as the next version for the order and mark it saved."""
    last = db.scalar(select(BOM.version).where(BOM.order_id == bom.order_id).order_by(BOM.version.desc()))
    bom.version = (last or 0) + 1
    bom.status = "saved"
    bom.created_by = user_id
    bom.saved_at = datetime.now(timezone.utc)
    db.add(bom)
    db.flush()
    return bom


# ---------------------------------------------------------------- recalculation


def recalculate(db: Session, saved: BOM, use_published_template: bool = True) -> tuple[BOM, dict]:
    """Rebuild a saved BOM with today's rates (and, optionally, the sign type's current published template),
    keeping the saved parameters, overrides and extra lines. Returns the new in-memory BOM and a diff."""
    template_id = saved.template_id
    if use_published_template and saved.order.sign_type_id:
        pub = db.scalar(select(Template).where(Template.sign_type_id == saved.order.sign_type_id, Template.status == "published"))
        if pub:
            template_id = pub.id
    overrides = {ln.component_line_id: float(ln.qty_final) for ln in saved.lines if ln.component_line_id and ln.qty_auto is not None and float(ln.qty_final) != float(ln.qty_auto)}
    notes = {ln.component_line_id: ln.override_note for ln in saved.lines if ln.component_line_id and ln.override_note}
    extras = [ExtraLine(ln.material_id, ln.material_name, float(ln.qty_final), None if ln.material_id else float(ln.rate), ln.cost_tag, ln.uom, ln.override_note) for ln in saved.lines if ln.component_line_id is None]
    if template_id != saved.template_id:
        overrides, notes = {}, {}  # line ids belong to the old version; overrides can't be carried across
    req = BOMRequest(order_id=saved.order_id, template_id=template_id, parameters=dict(saved.parameters or {}), overrides=overrides, override_notes=notes, extras=extras, misc_pct=float(saved.misc_pct), box_dimension=saved.box_dimension, est_shipment_cost_usd=float(saved.est_shipment_cost_usd) if saved.est_shipment_cost_usd is not None else None, notes=saved.notes)
    new = build_bom(db, req)
    return new, diff_boms(saved, new)


def diff_boms(a: BOM, b: BOM) -> dict:
    """Line-level comparison keyed by material name + usage (works across template versions and imports)."""

    def key(ln: BOMLine):
        return f"{ln.material_name}|{ln.usage or ''}"

    la = {key(ln): ln for ln in a.lines}
    lb = {key(ln): ln for ln in b.lines}
    changed, added, removed = [], [], []
    for k in lb.keys() - la.keys():
        added.append({"line": k, "qty": float(lb[k].qty_final), "rate": float(lb[k].rate), "total": float(lb[k].total_with_wastage_pkr)})
    for k in la.keys() - lb.keys():
        removed.append({"line": k, "qty": float(la[k].qty_final), "rate": float(la[k].rate), "total": float(la[k].total_with_wastage_pkr)})
    for k in la.keys() & lb.keys():
        x, y = la[k], lb[k]
        # frozen quantities are stored to 4 dp and rates to 4 dp; compare at that precision
        if round(float(x.qty_final), 4) != round(float(y.qty_final), 4) or round(float(x.rate), 4) != round(float(y.rate), 4) or abs(float(x.total_with_wastage_pkr) - float(y.total_with_wastage_pkr)) >= 0.01:
            changed.append({"line": k, "qty": [float(x.qty_final), float(y.qty_final)], "rate": [float(x.rate), float(y.rate)], "rate_source": [x.rate_source, y.rate_source], "total": [float(x.total_with_wastage_pkr), float(y.total_with_wastage_pkr)]})
    return {
        "template_changed": a.template_id != b.template_id,
        "grand_total": [float(a.grand_total_pkr), float(b.grand_total_pkr)],
        "delta_pkr": round(float(b.grand_total_pkr) - float(a.grand_total_pkr), 2),
        "changed": sorted(changed, key=lambda c: -abs(c["total"][1] - c["total"][0])),
        "added": added,
        "removed": removed,
    }


def rates_changed_since(db: Session, saved: BOM) -> list[dict]:
    """Cheap check for the BOM page: lines whose current rate differs from the frozen one."""
    resolver = RateResolver(db)
    out = []
    for ln in saved.lines:
        if not ln.material_id or ln.rate_source in ("formula", "manual", "sheet") or not float(ln.qty_final):
            continue  # only lines that actually cost something on this BOM
        uom_id = db.scalar(select(UOM.id).where(UOM.code == ln.uom)) if ln.uom else None
        rr = resolver.resolve(ln.material, uom_id)
        if rr.source != "none" and abs(rr.rate - float(ln.rate)) > 1e-6:
            out.append({"line": ln.material_name, "frozen": float(ln.rate), "current": rr.rate, "source": rr.source})
    return out
