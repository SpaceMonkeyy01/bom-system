from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api import schemas as S
from app.db import get_session
from app.models import BOM, Material, Order, SignType, Template
from app.models import User
from app.services.auth import current_user, require
from app.services.bom import BOMRequest, ExtraLine, build_bom, save_bom
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
        out.append(S.MaterialSearchOut(id=m.id, name=m.name, category_path=m.category.path if m.category else None, uom=m.uom.code if m.uom else None, active=m.active, rate=rr.rate if rr.source != "none" else None, rate_source=rr.source if rr.source != "none" else None))
    return out


@router.get("/materials/{material_id}", response_model=S.MaterialOut)
def get_material(material_id: int, db: Session = Depends(get_session)):
    m = db.get(Material, material_id)
    if not m:
        raise HTTPException(404, "Material not found")
    resolver = RateResolver(db)
    rr = resolver.resolve(m)
    out = S.MaterialOut.model_validate(m)
    out.category_path = m.category.path if m.category else None
    out.uom = m.uom.code if m.uom else None
    out.external_keys = [{"system": k.system.value, "store": k.store, "external_id": k.external_id, "external_name": k.external_name} for k in m.external_keys]
    out.rates = [S.RateOut(**r) for r in resolver.all_rates(m)]
    out.current_rate = S.RateOut(source=rr.source, rate=rr.rate, effective_from=rr.effective_from.isoformat() if rr.effective_from else "") if rr.source != "none" else None
    return out


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
    stmt = stmt.order_by(Order.dispatch_by.nulls_last(), Order.code).limit(limit)
    rows = [_order_out(o) for o in db.scalars(stmt)]
    if needs_bom is True:
        rows = [r for r in rows if r.bom_count == 0]
    elif needs_bom is False:
        rows = [r for r in rows if r.bom_count > 0]
    return rows


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
    db.commit()
    db.refresh(bom)
    return _bom_out(bom)


@router.get("/boms/{bom_id}", response_model=S.BOMOut)
def get_bom(bom_id: int, db: Session = Depends(get_session)):
    b = db.get(BOM, bom_id)
    if not b:
        raise HTTPException(404, "BOM not found")
    return _bom_out(b)


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
