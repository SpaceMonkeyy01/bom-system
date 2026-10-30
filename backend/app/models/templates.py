from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.core import TimestampMixin


class SignType(TimestampMixin, Base):
    """Canonical sign type (~25). Airtable's free-text names map onto it via `aliases`."""

    __tablename__ = "sign_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    code: Mapped[str | None] = mapped_column(String(10))  # "01", "02" ... from BOM_Check numbering
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    templates: Mapped[list[Template]] = relationship(back_populates="sign_type")


class Template(TimestampMixin, Base):
    """A versioned recipe for a sign type. Only one version is `published` at a time."""

    __tablename__ = "templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    sign_type_id: Mapped[int] = mapped_column(ForeignKey("sign_types.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(12), default="draft")  # draft | published | retired
    notes: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    source: Mapped[str | None] = mapped_column(String(120))  # e.g. "BOM_Check.xlsx / 01 - Metal - With Backlit"

    sign_type: Mapped[SignType] = relationship(back_populates="templates")
    parameters: Mapped[list[Parameter]] = relationship(
        back_populates="template", cascade="all, delete-orphan", order_by="Parameter.seq"
    )
    lines: Mapped[list[ComponentLine]] = relationship(
        back_populates="template", cascade="all, delete-orphan", order_by="ComponentLine.seq"
    )
    __table_args__ = (UniqueConstraint("sign_type_id", "version", name="uq_template_signtype_version"),)


class Parameter(Base):
    """An input the BOM person fills in. `param_name` is what formulas reference (no spaces)."""

    __tablename__ = "template_parameters"
    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("templates.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    label: Mapped[str] = mapped_column(String(120))
    param_name: Mapped[str] = mapped_column(String(80))
    uom: Mapped[str | None] = mapped_column(String(20))
    input_type: Mapped[str] = mapped_column(String(10), default="number")  # number | select
    options: Mapped[list[str]] = mapped_column(JSON, default=list)
    default_value: Mapped[str | None] = mapped_column(String(80))
    default_from_order: Mapped[str | None] = mapped_column(String(40))  # e.g. "finish", "width_in"
    required: Mapped[bool] = mapped_column(Boolean, default=False)

    template: Mapped[Template] = relationship(back_populates="parameters")
    __table_args__ = (UniqueConstraint("template_id", "param_name", name="uq_param_template_name"),)


class ComponentLine(Base):
    """One material line in a template. Quantity (and optionally unit cost) are formulas stored as text."""

    __tablename__ = "template_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("templates.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    material_id: Mapped[int | None] = mapped_column(ForeignKey("materials.id"))
    material_name_hint: Mapped[str | None] = mapped_column(String(255))  # kept when material unresolved at seed
    qty_formula: Mapped[str] = mapped_column(Text)
    unit_cost_formula: Mapped[str | None] = mapped_column(Text)  # e.g. 'COST("Paint") * 0.2'
    uom: Mapped[str | None] = mapped_column(String(20))
    usage: Mapped[str | None] = mapped_column(String(120))  # "Front Face", "Return", "Primer"
    cost_tag: Mapped[str | None] = mapped_column(String(60))  # rolls up to a CostHead
    work_centre: Mapped[str | None] = mapped_column(String(60))
    wastage_pct: Mapped[float | None] = mapped_column(Numeric(6, 2))  # null = inherit from cost head
    optional: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(String(255))

    template: Mapped[Template] = relationship(back_populates="lines")
    material = relationship("Material")
