import type { BomLine, BomRequest, ComponentLine, Parameter } from '../api/types'

export type ParamValue = string | number

export interface DraftExtra {
  key: string
  material_id: number | null
  name: string
  qty: number
  cost_tag: string | null
  uom: string | null
}

/** Everything that changes the computed lines. Box and shipment are only recorded, so they stay out of it. */
export interface BomDraft {
  orderId: number
  templateId: number
  params: Record<string, ParamValue>
  overrides: Record<number, number>
  extras: DraftExtra[]
  miscPct: number | null
}

export function buildRequest(draft: BomDraft): BomRequest {
  return {
    order_id: draft.orderId,
    template_id: draft.templateId,
    parameters: draft.params,
    overrides: draft.overrides,
    extras: draft.extras.map(({ material_id, name, qty, cost_tag, uom }) => ({ material_id, name, qty, cost_tag, uom })),
    misc_pct: draft.miscPct,
  }
}

export interface LineRow {
  key: string
  line: BomLine
  /** Set on ad-hoc lines added with "Add material". */
  extraKey?: string
  /** Added but not in a preview yet, so its numbers aren't known. */
  pending?: boolean
  overridden: boolean
  /** The template owner's to-do note from the import. */
  flag?: string | null
}

function pendingLine(extra: DraftExtra): BomLine {
  return {
    id: null,
    seq: 0,
    component_line_id: null,
    material_id: extra.material_id,
    material_name: extra.name,
    usage: null,
    cost_tag: extra.cost_tag,
    cost_head: extra.cost_tag,
    work_centre: null,
    uom: extra.uom,
    qty_formula: null,
    qty_auto: null,
    qty_final: extra.qty,
    override_note: null,
    rate: 0,
    rate_source: null,
    rate_date: null,
    rate_stale: false,
    wastage_pct: 0,
    total_pkr: 0,
    total_with_wastage_pkr: 0,
    error: null,
    warning: null,
    rate_uom: null,
  }
}

/**
 * Pairs preview lines with the draft. The API returns extras after the template lines, in request order and with
 * no id, so they're matched by position against the extras that preview was computed from. The draft may already
 * have moved on: a removed extra disappears at once, and a new one shows as pending until its preview arrives.
 */
export function buildRows(
  lines: BomLine[],
  previewExtraKeys: string[],
  extras: DraftExtra[],
  overrides: Record<number, number>,
  templateLines: ComponentLine[] = [],
): LineRow[] {
  const flags = new Map(templateLines.map((l) => [l.id, l.notes]))
  const rows: LineRow[] = []
  const extraLines: BomLine[] = []
  for (const line of lines) {
    const id = line.component_line_id
    if (id === null) {
      extraLines.push(line)
    } else {
      rows.push({ key: `line-${id}`, line, overridden: id in overrides, flag: flags.get(id) })
    }
  }
  for (const extra of extras) {
    const index = previewExtraKeys.indexOf(extra.key)
    const line = index >= 0 ? extraLines[index] : undefined
    rows.push({
      key: `extra-${extra.key}`,
      extraKey: extra.key,
      line: line ?? pendingLine(extra),
      pending: !line,
      overridden: false,
    })
  }
  return rows
}

/** Zero-quantity lines are hidden by default, but never ones that need attention or that someone edited. */
export function isHideable(row: LineRow): boolean {
  return row.line.qty_final === 0 && !row.line.error && !row.overridden && !row.extraKey
}

/** A blank required input counts as 0 in the engine, so it would save a wrong BOM without any error. */
export function missingRequired(parameters: Parameter[], values: Record<string, ParamValue | undefined>): Parameter[] {
  return parameters.filter((p) => {
    if (!p.required) return false
    const value = values[p.param_name]
    return value === undefined || value === ''
  })
}

/** Why a line's cost can't be trusted: priced at nothing because there's no rate, though it has a quantity. */
export const isUnpriced = (line: BomLine) => line.rate_source === 'none' && line.qty_final > 0 && !line.error

/** The API's warning, minus "no rate": that case already has its own badge, and repeating it on every line adds noise. */
export const rateWarning = (line: BomLine) => (line.rate_source === 'none' ? null : line.warning)

/** Quantities come back with long float tails; three decimals is plenty to show and edit. */
export const qtyText = (value: number | null | undefined) =>
  value === null || value === undefined ? '' : String(Number(value.toFixed(3)))

/** Parses a typed quantity. Returns null for anything that isn't a non-negative number. */
export function parseQty(text: string): number | null {
  const cleaned = text.replace(/,/g, '').trim()
  if (cleaned === '') return null
  const value = Number(cleaned)
  return Number.isFinite(value) && value >= 0 ? value : null
}
