import type { DraftBody, LineEdit, ParamEdit, Problem, Template } from '../api/types'

/** Variables every template gets from the order; a parameter may not reuse these names. */
export const ORDER_PARAMS = ['Length_in', 'Width_in', 'Area_sqft']

export const DEFAULT_FROM_ORDER = [
  { value: 'finish', label: 'Finish' },
  { value: 'width_in', label: 'Width (in)' },
  { value: 'height_in', label: 'Height (in)' },
]

/** Mirrors backend/app/seed/templates.py::sanitize_param: 'Alu/SS face Area' -> 'Alu_SS_face_Area'. */
export function sanitizeParamName(label: string): string {
  let s = label.trim().replace(/[^A-Za-z0-9_]+/g, '_').replace(/^_+|_+$/g, '')
  if (s && /^[0-9]/.test(s)) s = '_' + s
  return s || 'Param'
}

export const isValidParamName = (name: string) => /^[A-Za-z_][A-Za-z0-9_]*$/.test(name)

/** Rows get a client key so React and the problem map survive reordering. */
export interface ParamRow extends ParamEdit {
  key: string
  /** Set once the user has typed a parameter name by hand; until then it follows the label. */
  nameTouched: boolean
}

export interface LineRow extends LineEdit {
  key: string
  /** For display only; the API wants the id. */
  material_name: string | null
}

export interface Draft {
  parameters: ParamRow[]
  lines: LineRow[]
  notes: string | null
}

let nextKey = 1
export const newKey = () => String(nextKey++)

export function draftFromTemplate(t: Template): Draft {
  return {
    notes: t.notes,
    parameters: t.parameters.map((p) => ({
      key: newKey(),
      nameTouched: p.param_name !== sanitizeParamName(p.label),
      label: p.label,
      param_name: p.param_name,
      uom: p.uom,
      input_type: p.input_type === 'select' ? 'select' : 'number',
      options: p.options,
      default_value: p.default_value,
      default_from_order: p.default_from_order,
      required: p.required,
    })),
    lines: t.lines.map((l) => ({
      key: newKey(),
      material_id: l.material_id,
      material_name: l.material_name,
      material_name_hint: l.material_id ? null : l.material_name,
      qty_formula: l.qty_formula,
      unit_cost_formula: l.unit_cost_formula,
      uom: l.uom,
      usage: l.usage,
      cost_tag: l.cost_tag,
      work_centre: l.work_centre,
      wastage_pct: l.wastage_pct,
      optional: l.optional,
      notes: l.notes,
    })),
  }
}

export function toBody(draft: Draft): DraftBody {
  return {
    notes: draft.notes,
    parameters: draft.parameters.map(({ key: _k, nameTouched: _t, ...p }) => ({ ...p, param_name: p.param_name.trim() })),
    lines: draft.lines.map(({ key: _k, material_name: _n, ...l }) => l),
  }
}

export const emptyParam = (): ParamRow => ({
  key: newKey(),
  nameTouched: false,
  label: '',
  param_name: '',
  uom: null,
  input_type: 'number',
  options: [],
  default_value: null,
  default_from_order: null,
  required: true,
})

export const emptyLine = (): LineRow => ({
  key: newKey(),
  material_id: null,
  material_name: null,
  material_name_hint: null,
  qty_formula: '',
  unit_cost_formula: null,
  uom: null,
  usage: null,
  cost_tag: null,
  work_centre: null,
  wastage_pct: null,
  optional: false,
  notes: null,
})

export const duplicateLine = (line: LineRow): LineRow => ({ ...line, key: newKey(), notes: null })

export function move<T>(items: T[], from: number, to: number): T[] {
  if (to < 0 || to >= items.length || from === to) return items
  const out = [...items]
  const [item] = out.splice(from, 1)
  out.splice(to, 0, item)
  return out
}

export interface ProblemIndex {
  params: Map<number, string[]>
  lines: Map<number, string[]>
  template: string[]
}

/** Groups problems by the row they name. Positions are the body's indexes, which match the draft's order. */
export function indexProblems(problems: Problem[]): ProblemIndex {
  const out: ProblemIndex = { params: new Map(), lines: new Map(), template: [] }
  for (const p of problems) {
    const m = /^(param|line):(\d+)$/.exec(p.where)
    if (!m) {
      out.template.push(p.message)
      continue
    }
    const map = m[1] === 'param' ? out.params : out.lines
    const i = Number(m[2])
    map.set(i, [...(map.get(i) ?? []), p.message])
  }
  return out
}

/** Cost tags in use on the lines, in first-seen order, for the QTY()/COST() chips. */
export function costTagsPresent(lines: Pick<LineEdit, 'cost_tag'>[]): string[] {
  const seen = new Set<string>()
  for (const l of lines) {
    const tag = l.cost_tag?.trim()
    if (tag) seen.add(tag)
  }
  return [...seen]
}

/** Inserts `text` at the caret of a text field and returns the new value and caret. */
export function insertAt(value: string, start: number, end: number, text: string): { value: string; caret: number } {
  const needsSpaceBefore = start > 0 && !/[\s(]$/.test(value.slice(0, start))
  const insert = (needsSpaceBefore ? ' ' : '') + text
  return { value: value.slice(0, start) + insert + value.slice(end), caret: start + insert.length }
}

/** Comma-separated options for a select, trimmed and de-duplicated. */
export const parseOptions = (text: string) => [...new Set(text.split(',').map((s) => s.trim()).filter(Boolean))]

/** Line keys in a template diff look like "name|usage|seq"; show them as "name · usage". */
export function describeLineKey(key: string): string {
  const [name, usage] = key.split('|')
  return usage ? `${name} · ${usage}` : name
}
