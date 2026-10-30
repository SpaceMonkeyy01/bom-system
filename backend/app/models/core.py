from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Role(str, enum.Enum):
    admin = "admin"
    template_owner = "template_owner"
    bom_editor = "bom_editor"
    inventory_manager = "inventory_manager"
    viewer = "viewer"


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    role: Mapped[Role] = mapped_column(Enum(Role, name="role"), default=Role.viewer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UOM(Base):
    """Fixed unit-of-measure list. Spreadsheet variants (Ltrs/liter, Nos/Piece) map onto these."""

    __tablename__ = "uoms"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)  # Sqft, Meter, Feet, Piece, Gram, Kg, Liter ...
    name: Mapped[str] = mapped_column(String(60))
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)


class Category(TimestampMixin, Base):
    """4-level category tree seeded from CategoryMaster."""

    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    name: Mapped[str] = mapped_column(String(120))
    level: Mapped[int] = mapped_column(Integer)  # 1..4
    path: Mapped[str] = mapped_column(String(400), unique=True)  # "Paints / Paint Colors / 2K Paint / Nexa"
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    parent: Mapped[Category | None] = relationship(remote_side=[id], back_populates="children")
    children: Mapped[list[Category]] = relationship(back_populates="parent")
    attribute_defs: Mapped[list[AttributeDef]] = relationship(back_populates="category")


class AttributeDef(Base):
    """A spec field that applies to materials in a category subtree (gauge, thickness, sheet size...)."""

    __tablename__ = "attribute_defs"
    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))  # null = applies to all
    name: Mapped[str] = mapped_column(String(80))
    data_type: Mapped[str] = mapped_column(String(20), default="text")  # text | number | date
    uom: Mapped[str | None] = mapped_column(String(20))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    category: Mapped[Category | None] = relationship(back_populates="attribute_defs")
    __table_args__ = (UniqueConstraint("category_id", "name", name="uq_attrdef_category_name"),)


class Material(TimestampMixin, Base):
    __tablename__ = "materials"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    uom_id: Mapped[int | None] = mapped_column(ForeignKey("uoms.id"))
    product_type: Mapped[str] = mapped_column(String(30), default="Goods")
    supplier: Mapped[str | None] = mapped_column(String(255))  # legacy free text from the categorisation sheet
    supplier_city: Mapped[str | None] = mapped_column(String(120))
    preferred_supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"))
    brand: Mapped[str | None] = mapped_column(String(120))
    country_of_origin: Mapped[str | None] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    review_status: Mapped[str] = mapped_column(String(20), default="done")  # done | to_review | not_needed
    notes: Mapped[str | None] = mapped_column(Text)

    category: Mapped[Category | None] = relationship()
    uom: Mapped[UOM | None] = relationship()
    external_keys: Mapped[list[MaterialExternalKey]] = relationship(
        back_populates="material", cascade="all, delete-orphan"
    )
    attributes: Mapped[list[AttributeValue]] = relationship(back_populates="material", cascade="all, delete-orphan")
    rates: Mapped[list[MaterialRate]] = relationship(back_populates="material")


class ExternalSystem(str, enum.Enum):
    iflow = "iflow"
    odoo = "odoo"
    airtable = "airtable"
    sheet = "sheet"  # legacy Google-Sheet material name


class MaterialExternalKey(Base):
    """(system, store, external_id) is unique. iFlow BS and NS reuse the same numbers, hence `store`."""

    __tablename__ = "material_external_keys"
    id: Mapped[int] = mapped_column(primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), index=True)
    system: Mapped[ExternalSystem] = mapped_column(Enum(ExternalSystem, name="external_system"))
    store: Mapped[str] = mapped_column(String(10), default="")  # "BS" | "NS" | "" when not store-scoped
    external_id: Mapped[str] = mapped_column(String(120))
    external_name: Mapped[str | None] = mapped_column(String(255))

    material: Mapped[Material] = relationship(back_populates="external_keys")
    __table_args__ = (UniqueConstraint("system", "store", "external_id", name="uq_extkey_system_store_id"),)


class AttributeValue(Base):
    __tablename__ = "attribute_values"
    id: Mapped[int] = mapped_column(primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), index=True)
    def_id: Mapped[int] = mapped_column(ForeignKey("attribute_defs.id"))
    value: Mapped[str] = mapped_column(String(255))

    material: Mapped[Material] = relationship(back_populates="attributes")
    definition: Mapped[AttributeDef] = relationship()
    __table_args__ = (UniqueConstraint("material_id", "def_id", name="uq_attrval_material_def"),)


class RateSource(str, enum.Enum):
    bom = "bom"  # manually maintained BOM rate
    iflow = "iflow"  # derived from a stock import
    supplier = "supplier"  # a quoted/invoiced price from a named supplier
    other = "other"


class Supplier(TimestampMixin, Base):
    """A vendor. A material can be bought from several suppliers at different rates."""

    __tablename__ = "suppliers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    city: Mapped[str | None] = mapped_column(String(120))
    contact: Mapped[str | None] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)


class StockSnapshot(Base):
    """One iFlow 'MAIN STORE STOCK SUMMARY' import for one store on one date."""

    __tablename__ = "stock_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    store: Mapped[str] = mapped_column(String(10))  # BS | NS
    snapshot_date: Mapped[date] = mapped_column(Date)
    source_file: Mapped[str | None] = mapped_column(String(255))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    imported_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    unmatched_count: Mapped[int] = mapped_column(Integer, default=0)

    lines: Mapped[list[StockLine]] = relationship(back_populates="snapshot", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("store", "snapshot_date", name="uq_snapshot_store_date"),)


class StockLine(Base):
    __tablename__ = "stock_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("stock_snapshots.id"), index=True)
    material_id: Mapped[int | None] = mapped_column(ForeignKey("materials.id"), index=True)  # null = unmatched
    external_id: Mapped[str] = mapped_column(String(60))
    external_name: Mapped[str] = mapped_column(String(255))
    unit: Mapped[str | None] = mapped_column(String(30))
    op_qty: Mapped[float | None] = mapped_column(Numeric(14, 4))
    received: Mapped[float | None] = mapped_column(Numeric(14, 4))
    issued: Mapped[float | None] = mapped_column(Numeric(14, 4))
    balance: Mapped[float | None] = mapped_column(Numeric(14, 4))
    op_amount: Mapped[float | None] = mapped_column(Numeric(16, 2))
    balance_amount: Mapped[float | None] = mapped_column(Numeric(16, 2))
    match_method: Mapped[str | None] = mapped_column(String(20))  # key | name | manual | None

    snapshot: Mapped[StockSnapshot] = relationship(back_populates="lines")


class MaterialRate(Base):
    """All rates are kept; none overwritten. The rate policy picks one at BOM time."""

    __tablename__ = "material_rates"
    id: Mapped[int] = mapped_column(primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), index=True)
    source: Mapped[RateSource] = mapped_column(Enum(RateSource, name="rate_source"))
    store: Mapped[str] = mapped_column(String(10), default="")
    rate: Mapped[float] = mapped_column(Numeric(14, 4))
    uom_id: Mapped[int | None] = mapped_column(ForeignKey("uoms.id"))
    effective_from: Mapped[date] = mapped_column(Date)
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("stock_snapshots.id"))
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), index=True)  # for source=supplier
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    note: Mapped[str | None] = mapped_column(String(255))

    material: Mapped[Material] = relationship(back_populates="rates")
    supplier: Mapped[Supplier | None] = relationship()
    __table_args__ = (Index("ix_rate_material_source_eff", "material_id", "source", "effective_from"),)


class RatePolicy(Base):
    """scope: global (scope_id null) | category | material. Most specific wins."""

    __tablename__ = "rate_policies"
    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(10))  # global | category | material
    scope_id: Mapped[int | None] = mapped_column(Integer)
    preferred_source: Mapped[RateSource] = mapped_column(Enum(RateSource, name="rate_source", create_type=False))
    fallback_order: Mapped[list[str]] = mapped_column(JSON, default=list)  # e.g. ["supplier:cheapest", "iflow:BS"]
    staleness_days: Mapped[int] = mapped_column(Integer, default=60)
    # how to pick among supplier rates when source=supplier: "latest" | "cheapest" | a supplier id as string
    supplier_rule: Mapped[str] = mapped_column(String(20), default="latest")
    __table_args__ = (UniqueConstraint("scope", "scope_id", name="uq_rate_policy_scope"),)


class UOMConversion(Base):
    """factor such that  qty_in_to_uom = qty_in_from_uom * factor.
    material_id null = generic (Gallon -> Liter 3.785); set = material-specific (a paint's quart -> grams via density)."""

    __tablename__ = "uom_conversions"
    id: Mapped[int] = mapped_column(primary_key=True)
    from_uom_id: Mapped[int] = mapped_column(ForeignKey("uoms.id"))
    to_uom_id: Mapped[int] = mapped_column(ForeignKey("uoms.id"))
    factor: Mapped[float] = mapped_column(Numeric(18, 8))
    material_id: Mapped[int | None] = mapped_column(ForeignKey("materials.id"), index=True)
    note: Mapped[str | None] = mapped_column(String(255))
    __table_args__ = (UniqueConstraint("from_uom_id", "to_uom_id", "material_id", name="uq_uom_conv"),)


class CostHead(Base):
    """The report columns (Metal, Acrylic, LEDs, Paint, Power Supply, Packaging, Misc, UV, ...)."""

    __tablename__ = "cost_heads"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    default_wastage_pct: Mapped[float] = mapped_column(Numeric(6, 2), default=0)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)  # cost tags that roll up here ("Wire" -> Wires)
