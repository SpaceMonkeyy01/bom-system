import type { Bom, BomLine, BomRequest, ComponentLine, Parameter } from '../api/types'
import type { Tone } from '../theme'

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

/** True when a saved line's quantity differs from what its formula gave. */
export const isEdited = (line: BomLine) => line.qty_auto !== null && Math.abs(line.qty_auto - line.qty_final) > 1e-6

export const isImported = (bom: Pick<Bom, 'status'>) => bom.status === 'imported'

/**
 * Rows for a saved BOM. Added lines are always shown, even at zero: someone put them there on purpose. On a BOM
 * imported from the old sheet no line has a template line, so that doesn't mean it was added.
 */
export const frozenRows = (bom: Pick<Bom, 'lines' | 'status'>): LineRow[] =>
  bom.lines.map((line, i) => ({
    key: `saved-${line.id ?? i}`,
    line,
    overridden: isEdited(line) || (line.component_line_id === null && !isImported(bom)),
  }))

/** Zero-quantity lines are hidden by default, but never ones that need attention or that someone edited. */
export function isHideable(row: LineRow): boolean {
  return row.line.qty_final === 0 && !row.line.error && !row.overridden && !row.extraKey
}

/** A blank required input counts as 0 in the engine, so it would save a wrong BOM without any error. */
export function missingRequired(parameters: Parameter[], values: Record<string, ParamValue | null | undefined>): Parameter[] {
  return parameters.filter((p) => {
    if (!p.required) return false
    const value = values[p.param_name]
    return value === undefined || value === null || value === ''
  })
}

/** Why a line's cost can't be trusted: priced at nothing because there's no rate, though it has a quantity. */
export const isUnpriced = (line: BomLine) => line.rate_source === 'none' && line.qty_final > 0 && !line.error

/** Rate-source tag per DESIGN.md: iFlow → done, supplier → info, BOM → neutral (pending when stale), manual → neutral. */
export function rateTag(line: Pick<BomLine, 'rate_source' | 'rate_stale' | 'rate_date'>): { tone: Tone; label: string } {
  const src = line.rate_source
  if (!src || src === 'none') return { tone: 'missing', label: 'No rate' }
  if (src === 'formula') return { tone: 'neutral', label: 'Formula' }
  if (src === 'manual') return { tone: 'neutral', label: 'Manual' }
  if (src === 'sheet') return { tone: 'neutral', label: 'Sheet' }
  if (src.startsWith('iflow')) return { tone: 'done', label: `iFlow${src.includes(':') ? ` · ${src.split(':')[1]}` : ''}` }
  if (src.startsWith('supplier')) return { tone: 'info', label: `Supplier${src.includes(':') ? ` · ${src.split(':').slice(1).join(':')}` : ''}` }
  if (src === 'bom') return line.rate_stale ? { tone: 'pending', label: `BOM · stale${line.rate_date ? ` (${monthYear(line.rate_date)})` : ''}` } : { tone: 'neutral', label: 'BOM' }
  return { tone: 'neutral', label: src }
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const monthYear = (iso: string) => {
  const [y, m] = iso.slice(0, 10).split('-').map(Number)
  return y && m ? `${MONTHS[m - 1]} ${String(y).slice(2)}` : iso
}

export interface CheckItem {
  tag: 'To do' | 'Check' | 'OK'
  text: string
  /** Parameter names to jump to, when the item is about inputs. */
  params?: string[]
}

/** The "Before you save" checklist: blockers first, then things worth a look, then what is fine. */
export function saveChecklist(args: { missing: Parameter[]; inputErrors: Record<string, string>; lines: BomLine[] }): { items: CheckItem[]; blocked: boolean } {
  const { missing, inputErrors, lines } = args
  const items: CheckItem[] = []
  if (missing.length) items.push({ tag: 'To do', text: `Fill in ${missing.map((p) => p.label).join(', ')}.`, params: missing.map((p) => p.param_name) })
  const badInputs = Object.entries(inputErrors)
  if (badInputs.length) items.push({ tag: 'To do', text: `Fix ${badInputs.map(([k, v]) => `${k}: ${v}`).join('; ')}.`, params: badInputs.map(([k]) => k) })
  const errors = lines.filter((l) => l.error).length
  if (errors) items.push({ tag: 'To do', text: `${errors} line${errors === 1 ? ' has' : 's have'} a formula error. The template needs fixing before this can be saved.` })
  const blocked = items.length > 0

  const unpriced = lines.filter(isUnpriced).length
  if (unpriced) items.push({ tag: 'Check', text: `${unpriced} line${unpriced === 1 ? ' has' : 's have'} no rate and cost${unpriced === 1 ? 's' : ''} nothing.` })
  const mismatched = lines.filter(rateWarning).length
  if (mismatched) items.push({ tag: 'Check', text: `${mismatched} line${mismatched === 1 ? ' uses' : 's use'} a rate in a different unit.` })
  else if (lines.length) items.push({ tag: 'OK', text: 'All units match their rates.' })
  const stale = lines.filter((l) => l.rate_stale && l.rate_source !== 'none' && l.qty_final > 0)
  if (stale.length) {
    const oldest = stale.map((l) => l.rate_date).filter((d): d is string => !!d).sort()[0]
    items.push({ tag: 'Check', text: `${stale.length} line${stale.length === 1 ? ' uses' : 's use'} a stale rate${oldest ? ` from ${monthYear(oldest)}` : ''}.` })
  } else if (lines.length && !unpriced) items.push({ tag: 'OK', text: 'All lines priced with current rates.' })
  return { items, blocked }
}

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
