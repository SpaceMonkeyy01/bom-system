"""Template editor: drafts, validation, preview, publish. Role: template_owner / admin."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api import schemas as S
from app.api.routes import _bom_out, get_template
from app.db import get_session
from app.models import ComponentLine, Order, SignType, Template, User
from app.services.auth import current_user, require
from app.services.bom import BOMRequest, build_bom
from app.services.templates import LineIn, ParamIn, discard_draft, new_draft, publish, replace_draft_content, sample_order_for, template_diff, transient_template, validate_template

router = APIRouter(dependencies=[Depends(current_user)])


class ParamEdit(BaseModel):
    label: str
    param_name: str
    uom: str | None = None
    input_type: str = "number"
    options: list[str] = Field(default_factory=list)
    default_value: str | None = None
    default_from_order: str | None = None
    required: bool = True


class LineEdit(BaseModel):
    material_id: int | None = None
    material_name_hint: str | None = None
    qty_formula: str = "0"
    unit_cost_formula: str | None = None
    uom: str | None = None
    usage: str | None = None
    cost_tag: str | None = None
    work_centre: str | None = None
    wastage_pct: float | None = None
    optional: bool = False
    notes: str | None = None


class DraftBody(BaseModel):
    parameters: list[ParamEdit]
    lines: list[LineEdit]
    notes: str | None = None


class ProblemOut(BaseModel):
    where: str
    message: str


class NewDraftBody(BaseModel):
    sign_type_id: int
    from_template_id: int | None = None


class SignTypeBody(BaseModel):
    name: str
    code: str | None = None
    aliases: list[str] = Field(default_factory=list)
    active: bool = True


class PreviewBody(BaseModel):
    order_id: int | None = None  # default: most recent order of this sign type
    parameters: dict[str, Any] = Field(default_factory=dict)
    draft: DraftBody | None = None  # unsaved editor state; when present it is previewed instead of the stored template


def _ins(body: DraftBody):
    return [ParamIn(**p.model_dump()) for p in body.parameters], [LineIn(**ln.model_dump()) for ln in body.lines]


@router.post("/templates/validate", response_model=list[ProblemOut])
def validate(body: DraftBody):
    """Check without saving; the editor calls this as the user types."""
    p, ln = _ins(body)
    return [ProblemOut(where=x.where, message=x.message) for x in validate_template(p, ln)]


@router.post("/templates/drafts", response_model=S.TemplateOut, status_code=201)
def create_draft(body: NewDraftBody, user: User = Depends(require("template:write")), db: Session = Depends(get_session)):
    try:
        t = new_draft(db, body.sign_type_id, body.from_template_id, user.id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    return get_template(t.id, db)


@router.put("/templates/{template_id}", response_model=dict)
def save_draft(template_id: int, body: DraftBody, _: User = Depends(require("template:write")), db: Session = Depends(get_session)):
    t = db.get(Template, template_id)
    if not t:
        raise HTTPException(404, "Template not found")
    p, ln = _ins(body)
    try:
        probs = replace_draft_content(db, t, p, ln, body.notes)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    return {"template": get_template(t.id, db), "problems": [ProblemOut(where=x.where, message=x.message) for x in probs]}


@router.post("/templates/{template_id}/publish", response_model=S.TemplateOut)
def publish_template(template_id: int, user: User = Depends(require("template:write")), db: Session = Depends(get_session)):
    t = db.get(Template, template_id)
    if not t:
        raise HTTPException(404, "Template not found")
    try:
        publish(db, t, user.id)
    except ValueError as e:
        raise HTTPException(422, str(e))
    db.commit()
    return get_template(t.id, db)


@router.delete("/templates/{template_id}", status_code=204)
def delete_draft(template_id: int, _: User = Depends(require("template:write")), db: Session = Depends(get_session)):
    t = db.get(Template, template_id)
    if not t:
        raise HTTPException(404, "Template not found")
    try:
        discard_draft(db, t)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()


@router.post("/templates/{template_id}/preview", response_model=S.BOMOut)
def preview_template(template_id: int, body: PreviewBody, db: Session = Depends(get_session)):
    """Run the template against a real order so the editor shows live numbers. Pass `draft` (same shape as
    PUT /templates/{id}) to preview unsaved edits; nothing is written either way, so any user may call it."""
    t = db.get(Template, template_id)
    if not t:
        raise HTTPException(404, "Template not found")
    order = db.get(Order, body.order_id) if body.order_id else sample_order_for(db, t)
    if not order:
        raise HTTPException(400, "No order to preview against; pass order_id")
    live = None
    if body.draft is not None:
        p, ln = _ins(body.draft)
        live = transient_template(db, t, p, ln)
    try:
        bom = build_bom(db, BOMRequest(order_id=order.id, template_id=t.id, template=live, parameters=body.parameters))
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.rollback()  # belt and braces: the preview must never leave anything behind
    bom.order = order
    out = _bom_out(bom)
    db.expunge_all()
    return out


@router.get("/templates/{a_id}/diff/{b_id}")
def diff(a_id: int, b_id: int, db: Session = Depends(get_session)):
    a, b = db.get(Template, a_id), db.get(Template, b_id)
    if not a or not b:
        raise HTTPException(404, "Template not found")
    return template_diff(a, b)


@router.get("/templates/flagged")
def flagged_lines(db: Session = Depends(get_session)):
    """The template owner's to-do list: every line the import flagged, grouped by template."""
    out = []
    for t in db.scalars(select(Template).options(selectinload(Template.lines).selectinload(ComponentLine.material), selectinload(Template.sign_type)).order_by(Template.sign_type_id, Template.version)):
        bad = [{"line_id": ln.id, "seq": ln.seq, "material_id": ln.material_id, "material": (ln.material.name if ln.material is not None else None) or ln.material_name_hint, "formula": ln.qty_formula, "problem": ln.notes} for ln in t.lines if ln.notes]
        if bad:
            out.append({"template_id": t.id, "sign_type": t.sign_type.name, "version": t.version, "status": t.status, "flagged": bad})
    return out


# ---------------------------------------------------------------- sign types (canonical list + Airtable aliases)


@router.post("/sign-types", response_model=S.SignTypeOut, status_code=201)
def create_sign_type(body: SignTypeBody, _: User = Depends(require("template:write")), db: Session = Depends(get_session)):
    if db.scalar(select(SignType).where(SignType.name == body.name)):
        raise HTTPException(409, "Sign type already exists")
    st = SignType(**body.model_dump())
    db.add(st)
    db.commit()
    return S.SignTypeOut(id=st.id, name=st.name, code=st.code, aliases=st.aliases, active=st.active)


@router.patch("/sign-types/{sign_type_id}", response_model=S.SignTypeOut)
def update_sign_type(sign_type_id: int, body: SignTypeBody, _: User = Depends(require("template:write")), db: Session = Depends(get_session)):
    st = db.get(SignType, sign_type_id)
    if not st:
        raise HTTPException(404, "Sign type not found")
    st.name, st.code, st.aliases, st.active = body.name, body.code, body.aliases, body.active
    # re-map orders whose raw name now matches an alias
    from app.seed.orders import sign_type_resolver

    db.flush()
    resolve = sign_type_resolver(db)
    remapped = 0
    for o in db.scalars(select(Order).where(Order.sign_type_id.is_(None), Order.sign_type_raw.isnot(None))):
        m = resolve(o.sign_type_raw)
        if m:
            o.sign_type_id = m.id
            remapped += 1
    db.commit()
    pub = next((t for t in st.templates if t.status == "published"), None)
    return S.SignTypeOut(id=st.id, name=st.name, code=st.code, aliases=st.aliases, active=st.active, published_template_id=pub.id if pub else None, template_count=len(st.templates))


@router.get("/sign-types/unmapped")
def unmapped_sign_type_names(db: Session = Depends(get_session)):
    """Airtable sign-type names on orders that match no SignType or alias, with counts."""
    rows = db.execute(select(Order.sign_type_raw, Order.id).where(Order.sign_type_id.is_(None), Order.sign_type_raw.isnot(None))).all()
    counts: dict[str, int] = {}
    for raw, _ in rows:
        counts[raw] = counts.get(raw, 0) + 1
    return [{"name": k, "orders": v} for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]
