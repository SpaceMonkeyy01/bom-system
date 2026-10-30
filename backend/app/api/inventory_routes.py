"""Inventory module: stock imports, review queue, materials, rates, categories, suppliers, rate policies."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.models import Category, Material, MaterialRate, RatePolicy, StockLine, StockSnapshot, Supplier, UOM, User
from app.models.core import RateSource
from app.services.auth import current_user, require
from app.services.inventory import add_rate, create_material_from_line, import_stock_file, link_line, merge_materials, suggest_matches, unmatched_lines

router = APIRouter(dependencies=[Depends(current_user)])


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- stock imports


class SnapshotOut(ORM):
    id: int
    store: str
    snapshot_date: date
    source_file: str | None
    row_count: int
    unmatched_count: int


@router.post("/inventory/stock-imports", response_model=SnapshotOut, status_code=201)
async def upload_stock(store: str = Form(..., pattern="^(BS|NS)$"), snapshot_date: date | None = Form(None), file: UploadFile = File(...), user: User = Depends(require("inventory:write")), db: Session = Depends(get_session)):
    """Upload an iFlow 'MAIN STORE STOCK SUMMARY' export for one store. Re-uploading the same store+date replaces it."""
    content = await file.read()
    try:
        snap = import_stock_file(db, store, file.filename or "upload", content, snapshot_date, user.id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    return snap


@router.get("/inventory/stock-imports", response_model=list[SnapshotOut])
def list_snapshots(db: Session = Depends(get_session)):
    return list(db.scalars(select(StockSnapshot).order_by(StockSnapshot.snapshot_date.desc(), StockSnapshot.store)))


class StockLineOut(ORM):
    id: int
    snapshot_id: int
    store: str = ""
    snapshot_date: date | None = None
    external_id: str
    external_name: str
    unit: str | None
    op_qty: float | None
    balance: float | None
    op_amount: float | None
    balance_amount: float | None
    suggestions: list[dict] = []


@router.get("/inventory/review-queue", response_model=list[StockLineOut])
def review_queue(store: str | None = None, limit: int = 100, with_suggestions: bool = True, db: Session = Depends(get_session)):
    out = []
    for ln in unmatched_lines(db, store, limit):
        o = StockLineOut.model_validate(ln)
        o.store, o.snapshot_date = ln.snapshot.store, ln.snapshot.snapshot_date
        if with_suggestions:
            o.suggestions = [{"id": m.id, "name": m.name, "category": m.category.path if m.category else None} for m in suggest_matches(db, ln)]
        out.append(o)
    return out


class LinkBody(BaseModel):
    material_id: int


class CreateFromLineBody(BaseModel):
    category_id: int | None = None


@router.post("/inventory/review-queue/{line_id}/link", status_code=204)
def link(line_id: int, body: LinkBody, user: User = Depends(require("inventory:write")), db: Session = Depends(get_session)):
    ln, m = db.get(StockLine, line_id), db.get(Material, body.material_id)
    if not ln or not m:
        raise HTTPException(404, "Line or material not found")
    try:
        link_line(db, ln, m, user.id)
    except ValueError as e:
        raise HTTPException(409, str(e))
    db.commit()


@router.post("/inventory/review-queue/{line_id}/create-material", status_code=201)
def create_from_line(line_id: int, body: CreateFromLineBody, user: User = Depends(require("inventory:write")), db: Session = Depends(get_session)):
    ln = db.get(StockLine, line_id)
    if not ln:
        raise HTTPException(404, "Line not found")
    m = create_material_from_line(db, ln, body.category_id, user.id)
    db.commit()
    return {"material_id": m.id, "name": m.name}


# ---------------------------------------------------------------- materials


class MaterialPatch(BaseModel):
    name: str | None = None
    category_id: int | None = None
    uom: str | None = None  # UOM code
    active: bool | None = None
    review_status: str | None = None
    preferred_supplier_id: int | None = None
    brand: str | None = None
    notes: str | None = None


@router.patch("/materials/{material_id}")
def patch_material(material_id: int, body: MaterialPatch, _: User = Depends(require("inventory:write")), db: Session = Depends(get_session)):
    m = db.get(Material, material_id)
    if not m:
        raise HTTPException(404, "Material not found")
    data = body.model_dump(exclude_unset=True)
    if "uom" in data:
        u = db.scalar(select(UOM).where(UOM.code == data.pop("uom")))
        if not u:
            raise HTTPException(400, "Unknown UOM code")
        m.uom = u
    if "category_id" in data and data["category_id"] is not None and not db.get(Category, data["category_id"]):
        raise HTTPException(400, "Unknown category")
    for k, v in data.items():
        setattr(m, k, v)
    db.commit()
    return {"ok": True}


class MergeBody(BaseModel):
    drop_material_id: int


@router.post("/materials/{material_id}/merge")
def merge(material_id: int, body: MergeBody, _: User = Depends(require("inventory:write")), db: Session = Depends(get_session)):
    keep, drop = db.get(Material, material_id), db.get(Material, body.drop_material_id)
    if not keep or not drop:
        raise HTTPException(404, "Material not found")
    try:
        moved = merge_materials(db, keep, drop)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    return moved


@router.get("/materials/review")
def materials_to_review(limit: int = 200, db: Session = Depends(get_session)):
    """Materials needing a human look: sheet-only, duplicates, created from imports."""
    rows = db.scalars(select(Material).where(Material.review_status == "to_review").options(selectinload(Material.external_keys)).order_by(Material.name).limit(limit))
    return [{"id": m.id, "name": m.name, "notes": m.notes, "active": m.active, "keys": [f"{k.system.value}:{k.store}:{k.external_id}" if k.store else f"{k.system.value}:{k.external_id}" for k in m.external_keys]} for m in rows]


# ---------------------------------------------------------------- rates


class RateIn(BaseModel):
    source: RateSource = RateSource.bom
    rate: float
    effective_from: date = Field(default_factory=date.today)
    supplier_id: int | None = None
    store: str = ""
    note: str | None = None


@router.post("/materials/{material_id}/rates", status_code=201)
def post_rate(material_id: int, body: RateIn, user: User = Depends(require("rates:write")), db: Session = Depends(get_session)):
    m = db.get(Material, material_id)
    if not m:
        raise HTTPException(404, "Material not found")
    try:
        r = add_rate(db, m, body.source, body.rate, body.effective_from, user.id, body.supplier_id, body.store, body.note)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    return {"id": r.id}


@router.get("/materials/{material_id}/rates")
def rate_history(material_id: int, db: Session = Depends(get_session)):
    rows = db.scalars(select(MaterialRate).where(MaterialRate.material_id == material_id).order_by(MaterialRate.effective_from.desc(), MaterialRate.id.desc()).limit(200))
    return [{"id": r.id, "source": r.source.value, "store": r.store, "supplier": r.supplier.name if r.supplier else None, "rate": float(r.rate), "effective_from": r.effective_from, "note": r.note, "created_at": r.created_at} for r in rows]


class PolicyIn(BaseModel):
    scope: str = Field(pattern="^(global|category|material)$")
    scope_id: int | None = None
    preferred_source: RateSource
    fallback_order: list[str] = Field(default_factory=list)
    staleness_days: int = 60
    supplier_rule: str = "latest"


@router.get("/rate-policies")
def list_policies(db: Session = Depends(get_session)):
    return [{"id": p.id, "scope": p.scope, "scope_id": p.scope_id, "preferred_source": p.preferred_source.value, "fallback_order": p.fallback_order, "staleness_days": p.staleness_days, "supplier_rule": p.supplier_rule} for p in db.scalars(select(RatePolicy))]


@router.put("/rate-policies")
def upsert_policy(body: PolicyIn, _: User = Depends(require("settings:write")), db: Session = Depends(get_session)):
    p = db.scalar(select(RatePolicy).where(RatePolicy.scope == body.scope, RatePolicy.scope_id == body.scope_id))
    if not p:
        p = RatePolicy(scope=body.scope, scope_id=body.scope_id, preferred_source=body.preferred_source)
        db.add(p)
    p.preferred_source, p.fallback_order, p.staleness_days, p.supplier_rule = body.preferred_source, body.fallback_order, body.staleness_days, body.supplier_rule
    db.commit()
    return {"id": p.id}


# ---------------------------------------------------------------- categories, UOMs, suppliers


@router.get("/categories")
def categories(db: Session = Depends(get_session)):
    counts = dict(db.execute(select(Material.category_id, func.count(Material.id)).group_by(Material.category_id)).all())
    return [{"id": c.id, "parent_id": c.parent_id, "name": c.name, "level": c.level, "path": c.path, "materials": counts.get(c.id, 0)} for c in db.scalars(select(Category).order_by(Category.path))]


class CategoryIn(BaseModel):
    name: str
    parent_id: int | None = None


@router.post("/categories", status_code=201)
def create_category(body: CategoryIn, _: User = Depends(require("inventory:write")), db: Session = Depends(get_session)):
    parent = db.get(Category, body.parent_id) if body.parent_id else None
    if body.parent_id and not parent:
        raise HTTPException(404, "Parent not found")
    if parent and parent.level >= 4:
        raise HTTPException(400, "The tree is four levels deep at most")
    path = f"{parent.path} / {body.name}" if parent else body.name
    if db.scalar(select(Category).where(Category.path == path)):
        raise HTTPException(409, "Category already exists")
    c = Category(parent=parent, name=body.name, level=(parent.level + 1) if parent else 1, path=path)
    db.add(c)
    db.commit()
    return {"id": c.id, "path": c.path}


@router.get("/uoms")
def uoms(db: Session = Depends(get_session)):
    return [{"id": u.id, "code": u.code, "name": u.name} for u in db.scalars(select(UOM).order_by(UOM.code))]


class SupplierIn(BaseModel):
    name: str
    city: str | None = None
    contact: str | None = None
    active: bool = True
    notes: str | None = None


@router.get("/suppliers")
def suppliers(q: str = "", db: Session = Depends(get_session)):
    stmt = select(Supplier).order_by(Supplier.name)
    if q:
        stmt = stmt.where(Supplier.name.ilike(f"%{q}%"))
    return [{"id": s.id, "name": s.name, "city": s.city, "contact": s.contact, "active": s.active} for s in db.scalars(stmt)]


@router.post("/suppliers", status_code=201)
def create_supplier(body: SupplierIn, _: User = Depends(require("inventory:write")), db: Session = Depends(get_session)):
    if db.scalar(select(Supplier).where(func.lower(Supplier.name) == body.name.lower())):
        raise HTTPException(409, "Supplier already exists")
    s = Supplier(**body.model_dump())
    db.add(s)
    db.commit()
    return {"id": s.id}


@router.patch("/suppliers/{supplier_id}")
def update_supplier(supplier_id: int, body: SupplierIn, _: User = Depends(require("inventory:write")), db: Session = Depends(get_session)):
    s = db.get(Supplier, supplier_id)
    if not s:
        raise HTTPException(404, "Supplier not found")
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    db.commit()
    return {"ok": True}
