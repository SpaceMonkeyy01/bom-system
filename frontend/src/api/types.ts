/** Hand-kept mirror of backend/app/api/schemas.py (see /docs for the live contract). */

export type Role = 'admin' | 'template_owner' | 'bom_editor' | 'inventory_manager' | 'viewer'

export interface User {
  id: number
  email: string
  name: string
  role: Role
  active: boolean
  last_login_at: string | null
}

export interface TokenOut {
  access_token: string
  token_type: string
  user: User
}

export interface SignType {
  id: number
  name: string
  code: string | null
  aliases: string[]
  active: boolean
  published_template_id: number | null
  template_count: number
}

export interface TemplateSummary {
  id: number
  sign_type_id: number
  version: number
  status: string
  source: string | null
  line_count: number
  flagged_lines: number
}

export interface Parameter {
  id: number
  seq: number
  label: string
  param_name: string
  uom: string | null
  input_type: string
  options: string[]
  default_value: string | null
  default_from_order: string | null
  required: boolean
}

export interface ComponentLine {
  id: number
  seq: number
  material_id: number | null
  material_name: string | null
  qty_formula: string
  unit_cost_formula: string | null
  uom: string | null
  usage: string | null
  cost_tag: string | null
  work_centre: string | null
  wastage_pct: number | null
  optional: boolean
  notes: string | null
}

export interface Template {
  id: number
  sign_type_id: number
  sign_type_name: string | null
  version: number
  status: string
  source: string | null
  notes: string | null
  published_at: string | null
  parameters: Parameter[]
  lines: ComponentLine[]
}

export interface MaterialSearchResult {
  id: number
  name: string
  category_path: string | null
  uom: string | null
  active: boolean
  rate: number | null
  rate_source: string | null
}

export interface OrderImage {
  kind?: string
  filename?: string
  url?: string
}

export interface Order {
  id: number
  code: string
  account_name: string | null
  country: string | null
  sign_type_raw: string | null
  sign_type_id: number | null
  sign_type_name: string | null
  width_in: number | null
  height_in: number | null
  finish: string | null
  led_color: string | null
  usage: string | null
  special_notes: string | null
  status: string | null
  order_date: string | null
  dispatch_by: string | null
  weekly_bucket: string | null
  images: OrderImage[]
  etsy_price_usd: number | null
  calculator_production_cost_usd: number | null
  airtable_bom_done: boolean
  airtable_bom_price_pkr: number | null
  bom_count: number
  latest_bom_total_pkr: number | null
}

export interface ExtraLineIn {
  material_id: number | null
  name: string
  qty: number
  unit_cost?: number | null
  cost_tag?: string | null
  uom?: string | null
  note?: string | null
}

export interface BomRequest {
  order_id: number
  template_id: number | null
  parameters: Record<string, string | number>
  overrides: Record<number, number>
  extras: ExtraLineIn[]
  misc_pct: number | null
  box_dimension?: string | null
  est_shipment_cost_usd?: number | null
}

export interface BomLine {
  id: number | null
  seq: number
  component_line_id: number | null
  material_id: number | null
  material_name: string
  usage: string | null
  cost_tag: string | null
  cost_head: string | null
  work_centre: string | null
  uom: string | null
  qty_formula: string | null
  qty_auto: number | null
  qty_final: number
  override_note: string | null
  rate: number
  rate_source: string | null
  rate_date: string | null
  rate_stale: boolean
  wastage_pct: number
  total_pkr: number
  total_with_wastage_pkr: number
  error: string | null
  warning: string | null
  rate_uom: string | null
}

export interface Bom {
  id: number | null
  order_id: number
  order_code: string | null
  version: number
  status: string
  template_id: number | null
  parameters: Record<string, string | number>
  area_sqft: number | null
  base_total_pkr: number
  wastage_total_pkr: number
  misc_pct: number
  misc_total_pkr: number
  grand_total_pkr: number
  pkr_per_usd: number
  material_cost_usd: number | null
  production_cost_usd: number | null
  by_cost_head: Record<string, number>
  box_dimension: string | null
  est_shipment_cost_usd: number | null
  notes: string | null
  saved_at: string | null
  lines: BomLine[]
  input_errors: Record<string, string>
}

export interface DashboardSummary {
  orders: number
  orders_with_bom: number
  orders_awaiting_bom: number
  orders_unmapped_sign_type: number
  weekly_buckets: Record<string, number>
}
