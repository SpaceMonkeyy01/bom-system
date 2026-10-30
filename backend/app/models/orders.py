from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.core import TimestampMixin


class Order(TimestampMixin, Base):
    """Mirror of the Airtable order record. Synced, not edited here (except template mapping)."""

    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(60), unique=True)  # BS-ET-16765
    airtable_record_id: Mapped[str | None] = mapped_column(String(40), unique=True)
    airtable_table: Mapped[str | None] = mapped_column(String(80))  # which month tab it came from
    account_name: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(60))
    sign_type_raw: Mapped[str | None] = mapped_column(String(200))  # as typed in Airtable
    sign_type_id: Mapped[int | None] = mapped_column(ForeignKey("sign_types.id"))
    width_in: Mapped[float | None] = mapped_column(Numeric(10, 3))
    height_in: Mapped[float | None] = mapped_column(Numeric(10, 3))
    finish: Mapped[str | None] = mapped_column(String(120))
    led_color: Mapped[str | None] = mapped_column(String(120))
    usage: Mapped[str | None] = mapped_column(String(20))  # Indoor | Outdoor
    special_notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(200))
    order_date: Mapped[date | None] = mapped_column(Date)
    dispatch_by: Mapped[date | None] = mapped_column(Date)
    weekly_bucket: Mapped[str | None] = mapped_column(String(60))  # "October - 2nd week"
    images: Mapped[list[dict]] = mapped_column(JSON, default=list)  # [{kind, url, filename}]
    etsy_price_usd: Mapped[float | None] = mapped_column(Numeric(12, 2))
    calculator_production_cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 2))
    calculator_shipping_cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 2))
    airtable_bom_done: Mapped[bool] = mapped_column(Boolean, default=False)
    airtable_bom_price_pkr: Mapped[float | None] = mapped_column(Numeric(14, 2))  # what Airtable currently holds
    reason_of_re: Mapped[str | None] = mapped_column(Text)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)  # full Airtable record for anything not modelled
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    sign_type = relationship("SignType")
    boms: Mapped[list[BOM]] = relationship(back_populates="order", order_by="BOM.version")


class BOM(TimestampMixin, Base):
    """A costed bill of materials for an order. One order can have several versions."""

    __tablename__ = "boms"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft | saved | written_back | imported
    template_id: Mapped[int | None] = mapped_column(ForeignKey("templates.id"))
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)  # {param_name: value}
    length_in: Mapped[float | None] = mapped_column(Numeric(10, 3))
    width_in: Mapped[float | None] = mapped_column(Numeric(10, 3))
    area_sqft: Mapped[float | None] = mapped_column(Numeric(12, 4))
    base_total_pkr: Mapped[float] = mapped_column(Numeric(14, 2), default=0)  # before wastage & misc
    wastage_total_pkr: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    misc_pct: Mapped[float] = mapped_column(Numeric(6, 2), default=0)
    misc_total_pkr: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    grand_total_pkr: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    pkr_per_usd: Mapped[float] = mapped_column(Numeric(10, 4), default=270)
    material_cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 2))
    production_cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 2))
    by_cost_head: Mapped[dict] = mapped_column(JSON, default=dict)  # {"Metal": 1234.5, ...}
    box_dimension: Mapped[str | None] = mapped_column(String(40))  # "14x10x2.5"
    est_shipment_cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 2))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str | None] = mapped_column(String(60))  # app | sheet-import | prototype-import

    order: Mapped[Order] = relationship(back_populates="boms")
    template = relationship("Template")
    lines: Mapped[list[BOMLine]] = relationship(back_populates="bom", cascade="all, delete-orphan", order_by="BOMLine.seq")
    write_backs: Mapped[list[WriteBack]] = relationship(back_populates="bom")
    __table_args__ = (UniqueConstraint("order_id", "version", name="uq_bom_order_version"),)


class BOMLine(Base):
    """A frozen line. Everything needed to reproduce the number is stored on the row."""

    __tablename__ = "bom_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    bom_id: Mapped[int] = mapped_column(ForeignKey("boms.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    component_line_id: Mapped[int | None] = mapped_column(ForeignKey("template_lines.id"))  # null = extra line
    material_id: Mapped[int | None] = mapped_column(ForeignKey("materials.id"))
    material_name: Mapped[str] = mapped_column(String(255))
    usage: Mapped[str | None] = mapped_column(String(120))
    cost_tag: Mapped[str | None] = mapped_column(String(60))
    cost_head: Mapped[str | None] = mapped_column(String(60))
    work_centre: Mapped[str | None] = mapped_column(String(60))
    uom: Mapped[str | None] = mapped_column(String(20))
    qty_formula: Mapped[str | None] = mapped_column(Text)
    qty_auto: Mapped[float | None] = mapped_column(Numeric(14, 4))  # what the formula produced
    qty_final: Mapped[float] = mapped_column(Numeric(14, 4))  # after override
    override_note: Mapped[str | None] = mapped_column(String(255))
    swapped_from: Mapped[str | None] = mapped_column(String(255))
    rate: Mapped[float] = mapped_column(Numeric(14, 4), default=0)
    rate_source: Mapped[str | None] = mapped_column(String(20))  # bom | iflow:BS | iflow:NS | formula | manual
    rate_date: Mapped[date | None] = mapped_column(Date)
    rate_stale: Mapped[bool] = mapped_column(Boolean, default=False)
    wastage_pct: Mapped[float] = mapped_column(Numeric(6, 2), default=0)
    total_pkr: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    total_with_wastage_pkr: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    error: Mapped[str | None] = mapped_column(String(255))
    warning: Mapped[str | None] = mapped_column(String(255))  # non-blocking, e.g. rate in a different UOM
    rate_uom: Mapped[str | None] = mapped_column(String(20))

    bom: Mapped[BOM] = relationship(back_populates="lines")


class WriteBack(Base):
    """Audit of what was pushed to the order system (Airtable) for a BOM."""

    __tablename__ = "write_backs"
    id: Mapped[int] = mapped_column(primary_key=True)
    bom_id: Mapped[int] = mapped_column(ForeignKey("boms.id"), index=True)
    target: Mapped[str] = mapped_column(String(20), default="airtable")
    fields_sent: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | sent | failed
    error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bom: Mapped[BOM] = relationship(back_populates="write_backs")
