from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- sign types & templates


class SignTypeOut(ORMModel):
    id: int
    name: str
    code: str | None
    aliases: list[str]
    active: bool
    published_template_id: int | None = None
    template_count: int = 0


class ParameterOut(ORMModel):
    id: int
    seq: int
    label: str
    param_name: str
    uom: str | None
    input_type: str
    options: list[str]
    default_value: str | None
    default_from_order: str | None
    required: bool


class ComponentLineOut(ORMModel):
    id: int
    seq: int
    material_id: int | None
    material_name: str | None = None
    qty_formula: str
    unit_cost_formula: str | None
    uom: str | None
    usage: str | None
    cost_tag: str | None
    work_centre: str | None
    wastage_pct: float | None
    optional: bool
    notes: str | None


class TemplateOut(ORMModel):
    id: int
    sign_type_id: int
    sign_type_name: str | None = None
    version: int
    status: str
    source: str | None
    notes: str | None
    published_at: datetime | None
    parameters: list[ParameterOut]
    lines: list[ComponentLineOut]


class TemplateSummary(ORMModel):
    id: int
    sign_type_id: int
    version: int
    status: str
    source: str | None
    line_count: int = 0
    flagged_lines: int = 0


# ---------------------------------------------------------------- materials


class RateOut(BaseModel):
    source: str
    rate: float
    effective_from: str
    uom: str | None = None


class MaterialOut(ORMModel):
    id: int
    name: str
    category_path: str | None = None
    uom: str | None = None
    active: bool
    review_status: str
    supplier: str | None
    brand: str | None
    external_keys: list[dict] = []
    rates: list[RateOut] = []
    current_rate: RateOut | None = None


class MaterialSearchOut(BaseModel):
    id: int
    name: str
    category_path: str | None
    uom: str | None
    active: bool
    rate: float | None
    rate_source: str | None


# ---------------------------------------------------------------- orders & BOMs


class OrderOut(ORMModel):
    id: int
    code: str
    account_name: str | None
    country: str | None
    sign_type_raw: str | None
    sign_type_id: int | None
    sign_type_name: str | None = None
    width_in: float | None
    height_in: float | None
    finish: str | None
    led_color: str | None
    usage: str | None
    special_notes: str | None
    status: str | None
    order_date: date | None
    dispatch_by: date | None
    weekly_bucket: str | None
    images: list[dict]
    etsy_price_usd: float | None
    calculator_production_cost_usd: float | None
    airtable_bom_done: bool
    airtable_bom_price_pkr: float | None
    bom_count: int = 0
    latest_bom_total_pkr: float | None = None


class ExtraLineIn(BaseModel):
    material_id: int | None = None
    name: str
    qty: float
    unit_cost: float | None = None
    cost_tag: str | None = None
    uom: str | None = None
    note: str | None = None


class BOMRequestIn(BaseModel):
    order_id: int
    template_id: int | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    overrides: dict[int, float] = Field(default_factory=dict)
    override_notes: dict[int, str] = Field(default_factory=dict)
    extras: list[ExtraLineIn] = Field(default_factory=list)
    misc_pct: float | None = None
    box_dimension: str | None = None
    est_shipment_cost_usd: float | None = None
    notes: str | None = None


class BOMLineOut(ORMModel):
    id: int | None = None
    seq: int
    component_line_id: int | None
    material_id: int | None
    material_name: str
    usage: str | None
    cost_tag: str | None
    cost_head: str | None
    work_centre: str | None
    uom: str | None
    qty_formula: str | None
    qty_auto: float | None
    qty_final: float
    override_note: str | None
    rate: float
    rate_source: str | None
    rate_date: date | None
    rate_stale: bool
    wastage_pct: float
    total_pkr: float
    total_with_wastage_pkr: float
    error: str | None
    warning: str | None = None
    rate_uom: str | None = None


class BOMOut(ORMModel):
    id: int | None = None
    order_id: int
    order_code: str | None = None
    version: int
    status: str
    template_id: int | None
    parameters: dict[str, Any]
    area_sqft: float | None
    base_total_pkr: float
    wastage_total_pkr: float
    misc_pct: float
    misc_total_pkr: float
    grand_total_pkr: float
    pkr_per_usd: float
    material_cost_usd: float | None
    production_cost_usd: float | None
    by_cost_head: dict[str, float]
    box_dimension: str | None
    est_shipment_cost_usd: float | None
    notes: str | None
    saved_at: datetime | None
    lines: list[BOMLineOut]
    input_errors: dict[str, str] = {}
