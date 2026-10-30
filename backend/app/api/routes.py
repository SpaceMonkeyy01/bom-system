from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api import schemas as S
from app.db import get_session
from app.models import BOM, CostHead, Material, Order, SignType, Template
from app.seed.common import cost_tag_for_category
from app.models import User
from app.services.auth import current_user, require
from app.services.bom import BOMRequest, ExtraLine, build_bom, diff_boms, rates_changed_since, recalculate, save_bom
from app.services.rates import RateResolver

# every route needs a signed-in user; writes additionally need a permission
router = APIRouter(dependencies=[Depends(current_user)])


# ---------------------------------------------------------------- sign types / templates


@router.get("/sign-types", response_model=list[S.SignTypeOut])
def list_sign_types(db: Session = Depends(get_session), with_templates_only: bool = False):
    out = []
    for st in db.scalars(select(SignType).options(selectinload(SignType.templates)).order_by(SignType.name)):
        pub = next((t for t in st.templates if t.status == "published"), None)
        if with_templates_only and not st.templates:
            continue
        out.append(S.SignTypeOut(id=st.id, name=st.name, code=st.code, aliases=st.aliases, active=st.active, published_template_id=pub.id if pub else None, template_count=len(st.templates)))
    return out


@router.get("/sign-types/{sign_type_id}/templates", response_model=list[S.TemplateSummary])
def list_templates(sign_type_id: int, db: Session = Depends(get_session)):
    ts = db.scalars(select(Template).where(Template.sign_type_id == sign_type_id).options(selectinload(Template.lines)).order_by(Template.version))
    return [S.TemplateSummary(id=t.id, sign_type_id=t.sign_type_id, version=t.version, status=t.status, source=t.source, line_count=len(t.lines), flagged_lines=sum(1 for ln in t.lines if ln.notes)) for t in ts]


@router.get("/templates/{template_id}", response_model=S.TemplateOut)
def get_template(template_id: int, db: Session = Depends(get_session)):
    t = db.get(Template, template_id)
    if not t:
        raise HTTPException(404, "Template not found")
    out = S.TemplateOut.model_validate(t)
    out.sign_type_name = t.sign_type.name
    for lo, ln in zip(out.lines, t.lines):
        lo.material_name = ln.material.name if ln.material else ln.material_name_hint
    return out


# ---------------------------------------------------------------- materials


@router.get("/materials", response_model=list[S.MaterialSearchOut])
def search_materials(q: str = Query("", min_length=0), active_only: bool = True, limit: int = 50, db: Session = Depends(get_session)):
    stmt = select(Material).options(selectinload(Material.category), selectinload(Material.uom))
    if active_only:
        stmt = stmt.where(Material.active.is_(True))
    for word in q.split():
        stmt = stmt.where(or_(Material.name.ilike(f"%{word}%")))
    stmt = stmt.order_by(Material.name).limit(limit)
    resolver = RateResolver(db)
    out = []
    for m in db.scalars(stmt):
        rr = resolver.resolve(m)
        out.append(
            S.MaterialSearchOut(
                id=m.id,
                name=m.name,
                category_path=m.category.path if m.category else None,
                uom=m.uom.code if m.uom else None,
                active=m.active,
                rate=rr.rate if rr.source != "none" else None,
                rate_source=rr.source if rr.source != "none" else None,
                rate_uom=rr.uom,
                cost_tag=cost_tag_for_category(m.category.path if m.category else None, m.name),
            )
        )
    return out


@router.get("/cost-heads")
def list_cost_heads(db: Session = Depends(get_session)):
    return [{"id": h.id, "name": h.name, "default_wastage_pct": float(h.default_wastage_pct), "aliases": h.aliases} for h in db.scalars(select(CostHead).order_by(CostHead.sort_order))]


@router.get("/materials/{material_id}", response_model=S.MaterialOut)
def get_material(material_id: int, db: Session = Depends(get_session)):
    m = db.get(Material, material_id)
    if not m:
        raise HTTPException(404, "Material not found")
    resolver = RateResolver(db)
    rr = resolver.resolve(m)
    return S.MaterialOut(
        id=m.id,
        name=m.name,
        category_path=m.category.path if m.category else None,
        uom=m.uom.code if m.uom else None,
        active=m.active,
        review_status=m.review_status,
        supplier=m.supplier,
        brand=m.brand,
        external_keys=[{"system": k.system.value, "store": k.store, "external_id": k.external_id, "external_name": k.external_name} for k in m.external_keys],
        rates=[S.RateOut(**r) for r in resolver.all_rates(m)],
        current_rate=S.RateOut(source=rr.source, rate=rr.rate, effective_from=rr.effective_from.isoformat() if rr.effective_from else "") if rr.source != "none" else None,
    )


# ---------------------------------------------------------------- orders


def _order_out(o: Order) -> S.OrderOut:
    out = S.OrderOut.model_validate(o)
    out.sign_type_name = o.sign_type.name if o.sign_type else None
    out.bom_count = len(o.boms)
    out.latest_bom_total_pkr = float(o.boms[-1].grand_total_pkr) if o.boms else None
    return out


@router.get("/orders", response_model=list[S.OrderOut])
def list_orders(q: str = "", needs_bom: bool | None = None, limit: int = 200, db: Session = Depends(get_session)):
    stmt = select(Order).options(selectinload(Order.sign_type), selectinload(Order.boms))
    if q:
        stmt = stmt.where(or_(Order.code.ilike(f"%{q}%"), Order.account_name.ilike(f"%{q}%"), Order.sign_type_raw.ilike(f"%{q}%")))
    has_saved = select(BOM.id).where(BOM.order_id == Order.id, BOM.status.in_(("saved", "written_back", "imported"))).exists()
    if needs_bom is True:
        stmt = stmt.where(~has_saved, ~func.coalesce(Order.status, "").ilike("%cancel%"))
    elif needs_bom is False:
        stmt = stmt.where(has_saved)
    stmt = stmt.order_by(Order.dispatch_by.nulls_last(), Order.code).limit(limit)
    return [_order_out(o) for o in db.scalars(stmt)]


@router.get("/orders/{order_id}", response_model=S.OrderOut)
def get_order(order_id: int, db: Session = Depends(get_session)):
    o = db.get(Order, order_id)
    if not o:
        raise HTTPException(404, "Order not found")
    return _order_out(o)


@router.get("/orders/{order_id}/boms", response_model=list[S.BOMOut])
def list_order_boms(order_id: int, db: Session = Depends(get_session)):
    boms = db.scalars(select(BOM).where(BOM.order_id == order_id).options(selectinload(BOM.lines)).order_by(BOM.version))
    return [_bom_out(b) for b in boms]


# ---------------------------------------------------------------- BOMs


def _bom_out(b: BOM) -> S.BOMOut:
    out = S.BOMOut.model_validate(b)
    out.order_code = b.order.code if b.order else None
    out.input_errors = getattr(b, "_input_errors", {}) or {}
    return out


def _req(body: S.BOMRequestIn) -> BOMRequest:
    return BOMRequest(
        order_id=body.order_id,
        template_id=body.template_id,
        parameters=body.parameters,
        overrides=body.overrides,
        override_notes=body.override_notes,
        extras=[ExtraLine(**x.model_dump()) for x in body.extras],
        misc_pct=body.misc_pct,
        box_dimension=body.box_dimension,
        est_shipment_cost_usd=body.est_shipment_cost_usd,
        notes=body.notes,
    )


@router.post("/boms/preview", response_model=S.BOMOut)
def preview_bom(body: S.BOMRequestIn, _: User = Depends(require("bom:write")), db: Session = Depends(get_session)):
    try:
        bom = build_bom(db, _req(body))
    except ValueError as e:
        raise HTTPException(400, str(e))
    bom.order = db.get(Order, body.order_id)
    out = _bom_out(bom)
    db.expunge_all()  # preview never persists
    return out


@router.post("/boms", response_model=S.BOMOut, status_code=201)
def create_bom(body: S.BOMRequestIn, user: User = Depends(require("bom:write")), db: Session = Depends(get_session)):
    try:
        bom = build_bom(db, _req(body))
    except ValueError as e:
        raise HTTPException(400, str(e))
    if any(ln.error for ln in bom.lines):
        raise HTTPException(422, {"message": "A formula has a problem; fix the template first", "lines": [(ln.material_name, ln.error) for ln in bom.lines if ln.error]})
    errs = getattr(bom, "_input_errors", {})
    if errs:
        raise HTTPException(422, {"message": "Fix the inputs first", "input_errors": errs})
    save_bom(db, bom, user_id=user.id)
    from app.config import settings
    from app.services.airtable import get_client, write_back

    client = get_client() if settings.airtable_auto_write_back else None
    if client:
        write_back(db, client, bom)  # failures are logged on the BOM's write_backs; the save still succeeds
    db.commit()
    db.refresh(bom)
    return _bom_out(bom)


@router.get("/boms/{bom_id}", response_model=S.BOMOut)
def get_bom(bom_id: int, db: Session = Depends(get_session)):
    b = db.get(BOM, bom_id)
    if not b:
        raise HTTPException(404, "BOM not found")
    return _bom_out(b)


@router.get("/boms/{bom_id}/rate-changes")
def bom_rate_changes(bom_id: int, db: Session = Depends(get_session)):
    """Lines whose current rate differs from the one frozen on this BOM ("rates changed since save")."""
    b = db.get(BOM, bom_id)
    if not b:
        raise HTTPException(404, "BOM not found")
    changes = rates_changed_since(db, b)
    return {"bom_id": b.id, "changed_lines": changes, "count": len(changes)}


@router.post("/boms/{bom_id}/recalculate", response_model=dict)
def recalc_preview(bom_id: int, use_published_template: bool = True, _: User = Depends(require("bom:write")), db: Session = Depends(get_session)):
    """Preview what this BOM would cost today (current rates, optionally the current published template)."""
    b = db.get(BOM, bom_id)
    if not b:
        raise HTTPException(404, "BOM not found")
    try:
        new, diff = recalculate(db, b, use_published_template)
    except ValueError as e:
        raise HTTPException(400, str(e))
    new.order = b.order
    out = {"preview": _bom_out(new).model_dump(), "diff": diff}
    db.expunge_all()
    return out


@router.post("/boms/{bom_id}/recalculate/save", response_model=S.BOMOut, status_code=201)
def recalc_save(bom_id: int, use_published_template: bool = True, user: User = Depends(require("bom:write")), db: Session = Depends(get_session)):
    """Save the recalculated BOM as the order's next version (the old one is kept)."""
    b = db.get(BOM, bom_id)
    if not b:
        raise HTTPException(404, "BOM not found")
    try:
        new, _ = recalculate(db, b, use_published_template)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if any(ln.error for ln in new.lines):
        raise HTTPException(422, {"message": "A formula has a problem in the current template", "lines": [(ln.material_name, ln.error) for ln in new.lines if ln.error]})
    new.notes = (new.notes or "") + f" [recalculated from v{b.version}]"
    save_bom(db, new, user_id=user.id)
    db.commit()
    db.refresh(new)
    return _bom_out(new)


@router.get("/boms/{a_id}/diff/{b_id}")
def bom_diff(a_id: int, b_id: int, db: Session = Depends(get_session)):
    a, b = db.get(BOM, a_id), db.get(BOM, b_id)
    if not a or not b:
        raise HTTPException(404, "BOM not found")
    return diff_boms(a, b)


@router.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_session)):
    total_orders = db.scalar(select(func.count(Order.id)))
    with_bom = db.scalar(select(func.count(func.distinct(BOM.order_id))))
    unmapped = db.scalar(select(func.count(Order.id)).where(Order.sign_type_id.is_(None)))
    by_bucket = db.execute(select(Order.weekly_bucket, func.count(Order.id)).group_by(Order.weekly_bucket)).all()
    return {
        "orders": total_orders,
        "orders_with_bom": with_bom,
        "orders_awaiting_bom": total_orders - with_bom,
        "orders_unmapped_sign_type": unmapped,
        "weekly_buckets": {k or "(none)": v for k, v in by_bucket},
    }
