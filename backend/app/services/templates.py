"""Template editing: draft versions, validation, preview, publish."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.formula import check_formula, is_cost_formula, norm_tag, parse, qty_tags_used
from app.models import ComponentLine, Material, Order, Parameter, SignType, Template

ORDER_PARAMS = ["Length_in", "Width_in", "Area_sqft"]


@dataclass
class ParamIn:
    label: str
    param_name: str
    uom: str | None = None
    input_type: str = "number"
    options: list[str] = field(default_factory=list)
    default_value: str | None = None
    default_from_order: str | None = None
    required: bool = True


@dataclass
class LineIn:
    material_id: int | None
    qty_formula: str
    unit_cost_formula: str | None = None
    uom: str | None = None
    usage: str | None = None
    cost_tag: str | None = None
    work_centre: str | None = None
    wastage_pct: float | None = None
    optional: bool = False
    notes: str | None = None
    material_name_hint: str | None = None


@dataclass
class Problem:
    where: str  # "param:<n>" | "line:<n>" | "template"
    message: str


def validate_template(params: list[ParamIn], lines: list[LineIn]) -> list[Problem]:
    """Static checks mirroring the prototype's editor: names, formulas, tags, materials."""
    probs: list[Problem] = []
    seen: set[str] = set()
    import re

    for i, p in enumerate(params):
        n = (p.param_name or "").strip()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", n):
            probs.append(Problem(f"param:{i}", f"Parameter name “{n}” must be letters, digits and _ only, no spaces"))
        if n.lower() in seen:
            probs.append(Problem(f"param:{i}", f"Parameter name “{n}” is used twice"))
        seen.add(n.lower())
        if n in ORDER_PARAMS:
            probs.append(Problem(f"param:{i}", f"“{n}” is provided by the order; rename it or remove it"))
        if p.input_type == "select" and not p.options:
            probs.append(Problem(f"param:{i}", f"Dropdown “{p.label}” has no choices"))
    names = [p.param_name.strip() for p in params] + ORDER_PARAMS
    tags_present = {norm_tag(ln.cost_tag) for ln in lines if ln.cost_tag}
    for i, ln in enumerate(lines):
        if not ln.material_id and not ln.optional:
            probs.append(Problem(f"line:{i}", "No material chosen"))
        err = check_formula(ln.qty_formula, names)
        if err:
            probs.append(Problem(f"line:{i}", f"Quantity: {err}"))
        else:
            try:
                for t in qty_tags_used(parse(ln.qty_formula)):
                    if t not in tags_present:
                        probs.append(Problem(f"line:{i}", f'QTY("{t}") refers to a cost tag no line has'))
                    if ln.cost_tag and norm_tag(ln.cost_tag) == t:
                        probs.append(Problem(f"line:{i}", f'QTY("{t}") can’t be used on a line that has that cost tag itself'))
            except Exception:  # pragma: no cover
                pass
        if ln.unit_cost_formula:
            if not is_cost_formula(ln.unit_cost_formula):
                probs.append(Problem(f"line:{i}", "Unit cost formula is just a number; leave it blank to use the material rate"))
            else:
                err = check_formula(ln.unit_cost_formula, names)
                if err:
                    probs.append(Problem(f"line:{i}", f"Unit cost: {err}"))
        if not ln.cost_tag:
            probs.append(Problem(f"line:{i}", "No cost tag (needed for the report columns)"))
    if not lines:
        probs.append(Problem("template", "A template needs at least one line"))
    return probs


def new_draft(db: Session, sign_type_id: int, from_template_id: int | None, user_id: int | None) -> Template:
    """Create the next version for a sign type, copied from `from_template_id` (default: the published one)."""
    st = db.get(SignType, sign_type_id)
    if not st:
        raise ValueError("Sign type not found")
    if any(t.status == "draft" for t in st.templates):
        raise ValueError("This sign type already has a draft; edit or discard it first")
    src = db.get(Template, from_template_id) if from_template_id else next((t for t in st.templates if t.status == "published"), None)
    version = max((t.version for t in st.templates), default=0) + 1
    t = Template(sign_type=st, version=version, status="draft", created_by=user_id, source=f"copy of v{src.version}" if src else "new", notes=None)
    db.add(t)
    db.flush()
    if src:
        for p in src.parameters:
            db.add(Parameter(template=t, seq=p.seq, label=p.label, param_name=p.param_name, uom=p.uom, input_type=p.input_type, options=list(p.options or []), default_value=p.default_value, default_from_order=p.default_from_order, required=p.required))
        for ln in src.lines:
            db.add(ComponentLine(template=t, seq=ln.seq, material_id=ln.material_id, material_name_hint=ln.material_name_hint, qty_formula=ln.qty_formula, unit_cost_formula=ln.unit_cost_formula, uom=ln.uom, usage=ln.usage, cost_tag=ln.cost_tag, work_centre=ln.work_centre, wastage_pct=ln.wastage_pct, optional=ln.optional, notes=ln.notes))
    db.flush()
    db.refresh(t)
    return t


def replace_draft_content(db: Session, t: Template, params: list[ParamIn], lines: list[LineIn], notes: str | None) -> list[Problem]:
    """Overwrite a draft's parameters and lines (the editor saves the whole thing). Returns validation problems."""
    if t.status != "draft":
        raise ValueError("Only drafts can be edited; create a new version instead")
    probs = validate_template(params, lines)
    for p in list(t.parameters):
        db.delete(p)
    for ln in list(t.lines):
        db.delete(ln)
    db.flush()
    for i, p in enumerate(params):
        db.add(Parameter(template=t, seq=i, label=p.label, param_name=p.param_name.strip(), uom=p.uom, input_type=p.input_type, options=p.options or [], default_value=p.default_value, default_from_order=p.default_from_order, required=p.required))
    for i, ln in enumerate(lines):
        m = db.get(Material, ln.material_id) if ln.material_id else None
        db.add(
            ComponentLine(
                template=t,
                seq=i,
                material_id=m.id if m else None,
                material_name_hint=m.name if m else ln.material_name_hint,
                qty_formula=ln.qty_formula.strip() or "0",
                unit_cost_formula=(ln.unit_cost_formula or "").strip() or None,
                uom=ln.uom or (m.uom.code if m and m.uom else None),
                usage=ln.usage,
                cost_tag=ln.cost_tag,
                work_centre=ln.work_centre,
                wastage_pct=ln.wastage_pct,
                optional=ln.optional,
                notes=ln.notes,
            )
        )
    t.notes = notes
    db.flush()
    db.refresh(t)
    return probs


def transient_template(db: Session, base: Template, params: list[ParamIn], lines: list[LineIn]) -> Template:
    """Build the editor's unsaved state as an in-memory Template for preview. Nothing here is added to the
    session: relationships to persistent rows are set by id only, so no cascade can save it by accident."""
    t = Template(sign_type_id=base.sign_type_id, version=base.version, status="preview", source="unsaved editor state")
    t.id = None
    t.parameters = [
        Parameter(seq=i, label=p.label, param_name=p.param_name.strip(), uom=p.uom, input_type=p.input_type, options=p.options or [], default_value=p.default_value, default_from_order=p.default_from_order, required=p.required)
        for i, p in enumerate(params)
    ]
    out = []
    for i, ln in enumerate(lines):
        m = db.get(Material, ln.material_id) if ln.material_id else None
        c = ComponentLine(
            seq=i,
            material_id=m.id if m else None,
            material_name_hint=m.name if m else ln.material_name_hint,
            qty_formula=ln.qty_formula.strip() or "0",
            unit_cost_formula=(ln.unit_cost_formula or "").strip() or None,
            uom=ln.uom or (m.uom.code if m and m.uom else None),
            usage=ln.usage,
            cost_tag=ln.cost_tag,
            work_centre=ln.work_centre,
            wastage_pct=ln.wastage_pct,
            optional=ln.optional,
        )
        c.id = -(i + 1)  # distinct keys for the engine; negative so nothing mistakes them for saved lines
        c.material = m
        out.append(c)
    t.lines = out
    return t


def publish(db: Session, t: Template, user_id: int | None) -> None:
    if t.status != "draft":
        raise ValueError("Only a draft can be published")
    params = [ParamIn(p.label, p.param_name, p.uom, p.input_type, p.options or [], p.default_value, p.default_from_order, p.required) for p in t.parameters]
    lines = [LineIn(ln.material_id, ln.qty_formula, ln.unit_cost_formula, ln.uom, ln.usage, ln.cost_tag, ln.work_centre, ln.wastage_pct, ln.optional, ln.notes, ln.material_name_hint) for ln in t.lines]
    probs = validate_template(params, lines)
    if probs:
        raise ValueError("Fix these before publishing: " + "; ".join(f"{p.where}: {p.message}" for p in probs[:8]))
    for other in t.sign_type.templates:
        if other is not t and other.status == "published":
            other.status = "retired"
    for ln in t.lines:  # import flags are cleared once a human has published the template
        ln.notes = None
        ln.optional = False if ln.material_id else ln.optional
    t.status = "published"
    t.published_at = datetime.now(timezone.utc)
    t.published_by = user_id
    db.flush()


def discard_draft(db: Session, t: Template) -> None:
    if t.status != "draft":
        raise ValueError("Only a draft can be discarded")
    if db.scalar(select(Template.id).join(Template.sign_type).where(Template.id == t.id)) is None:
        return
    from app.models import BOM

    if db.scalar(select(BOM.id).where(BOM.template_id == t.id).limit(1)):
        t.status = "retired"  # a BOM points at it; keep the row
    else:
        db.delete(t)
    db.flush()


def sample_order_for(db: Session, t: Template) -> Order | None:
    """A real order of this sign type to preview against (most recent first)."""
    return db.scalar(select(Order).where(Order.sign_type_id == t.sign_type_id).order_by(Order.order_date.desc().nulls_last(), Order.id.desc()).limit(1))


def template_diff(a: Template, b: Template) -> dict[str, Any]:
    """What changed between two versions, by parameter name and by (material, usage) line key."""

    def pmap(t):
        return {p.param_name: (p.label, p.uom, p.input_type, tuple(p.options or []), p.default_value) for p in t.parameters}

    def lmap(t):
        out = {}
        for ln in t.lines:
            name = (ln.material.name if ln.material is not None else None) or ln.material_name_hint or "(no material)"
            key = f"{name}|{ln.usage or ''}|{ln.seq}"
            out[key] = (ln.qty_formula, ln.unit_cost_formula, ln.cost_tag, ln.work_centre, float(ln.wastage_pct) if ln.wastage_pct is not None else None)
        return out

    pa, pb, la, lb = pmap(a), pmap(b), lmap(a), lmap(b)
    return {
        "params_added": sorted(set(pb) - set(pa)),
        "params_removed": sorted(set(pa) - set(pb)),
        "params_changed": sorted(k for k in set(pa) & set(pb) if pa[k] != pb[k]),
        "lines_added": sorted(set(lb) - set(la)),
        "lines_removed": sorted(set(la) - set(lb)),
        "lines_changed": sorted(k for k in set(la) & set(lb) if la[k] != lb[k]),
    }
