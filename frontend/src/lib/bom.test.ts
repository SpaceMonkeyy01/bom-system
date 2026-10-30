import { describe, expect, it } from 'vitest'
import type { BomLine, ComponentLine, Parameter } from '../api/types'
import { buildRequest, buildRows, type DraftExtra, frozenRows, isEdited, isHideable, isUnpriced, missingRequired, parseQty, qtyText, rateWarning } from './bom'

function line(over: Partial<BomLine> = {}): BomLine {
  return {
    id: null,
    seq: 0,
    component_line_id: 1,
    material_id: 1,
    material_name: 'SS Metal',
    usage: null,
    cost_tag: 'Metal',
    cost_head: 'Metal',
    work_centre: null,
    uom: 'Sqft',
    qty_formula: '1',
    qty_auto: 1,
    qty_final: 1,
    override_note: null,
    rate: 10,
    rate_source: 'bom',
    rate_date: null,
    rate_stale: false,
    wastage_pct: 0,
    total_pkr: 10,
    total_with_wastage_pkr: 10,
    error: null,
    warning: null,
    rate_uom: null,
    ...over,
  }
}

const extra = (key: string, name = key): DraftExtra => ({ key, material_id: 9, name, qty: 2, cost_tag: 'Misc', uom: 'Piece' })

describe('buildRequest', () => {
  it('keeps blanks (they override a default to 0) and leaves client keys out of extras', () => {
    const req = buildRequest({
      orderId: 1,
      templateId: 2,
      params: { Depth: '' },
      overrides: { 5: 0 },
      extras: [extra('a', 'Tape')],
      miscPct: 0,
    })
    expect(req).toEqual({
      order_id: 1,
      template_id: 2,
      parameters: { Depth: '' },
      overrides: { 5: 0 },
      extras: [{ material_id: 9, name: 'Tape', qty: 2, cost_tag: 'Misc', uom: 'Piece' }],
      misc_pct: 0,
    })
  })
})

describe('buildRows', () => {
  const lines = [line({ component_line_id: 1 }), line({ component_line_id: 2 }), line({ component_line_id: null, material_name: 'A' }), line({ component_line_id: null, material_name: 'B' })]

  it('marks overridden lines and carries template flags', () => {
    const notes = [{ id: 2, notes: 'check me' }] as ComponentLine[]
    const rows = buildRows(lines.slice(0, 2), [], [], { 2: 5 }, notes)
    expect(rows.map((r) => r.overridden)).toEqual([false, true])
    expect(rows[1].flag).toBe('check me')
  })

  it('treats an override of zero as overridden', () => {
    expect(buildRows([line({ component_line_id: 7 })], [], [], { 7: 0 })[0].overridden).toBe(true)
  })

  it('matches extras to lines by the position they had in that preview', () => {
    const rows = buildRows(lines, ['a', 'b'], [extra('a'), extra('b')], {})
    expect(rows.slice(2).map((r) => [r.extraKey, r.line.material_name, r.pending])).toEqual([
      ['a', 'A', false],
      ['b', 'B', false],
    ])
  })

  it('drops a removed extra at once, without shifting the other onto the wrong line', () => {
    const rows = buildRows(lines, ['a', 'b'], [extra('b')], {})
    expect(rows.slice(2).map((r) => [r.extraKey, r.line.material_name])).toEqual([['b', 'B']])
  })

  it('shows a new extra as pending until a preview includes it', () => {
    const rows = buildRows(lines, ['a', 'b'], [extra('a'), extra('b'), extra('c', 'New')], {})
    expect(rows[4].pending).toBe(true)
    expect(rows[4].line.material_name).toBe('New')
    expect(rows[4].line.total_with_wastage_pkr).toBe(0)
  })
})

describe('isHideable', () => {
  const row = (over: Partial<BomLine>, overridden = false, extraKey?: string) => ({ key: 'k', line: line(over), overridden, extraKey })

  it('hides plain zero-quantity lines only', () => {
    expect(isHideable(row({ qty_final: 0 }))).toBe(true)
    expect(isHideable(row({ qty_final: 1 }))).toBe(false)
  })

  it('never hides errors, edits or added lines', () => {
    expect(isHideable(row({ qty_final: 0, error: 'bad' }))).toBe(false)
    expect(isHideable(row({ qty_final: 0 }, true))).toBe(false)
    expect(isHideable(row({ qty_final: 0 }, false, 'a'))).toBe(false)
  })
})

describe('missingRequired', () => {
  const p = (param_name: string, required: boolean) => ({ param_name, required }) as Parameter

  it('finds blank required inputs, and counts zero as filled in', () => {
    const params = [p('A', true), p('B', true), p('C', false), p('D', true)]
    expect(missingRequired(params, { A: '', B: 0, D: 3 }).map((x) => x.param_name)).toEqual(['A'])
    expect(missingRequired([p('A', true)], {}).length).toBe(1)
    expect(missingRequired([p('A', true)], { A: null }).length).toBe(1)
  })
})

describe('isUnpriced', () => {
  it('flags a line with a quantity and no rate', () => {
    expect(isUnpriced(line({ rate_source: 'none', qty_final: 2 }))).toBe(true)
    expect(isUnpriced(line({ rate_source: 'none', qty_final: 0 }))).toBe(false)
    expect(isUnpriced(line({ rate_source: 'bom', qty_final: 2 }))).toBe(false)
    expect(isUnpriced(line({ rate_source: 'none', qty_final: 2, error: 'bad' }))).toBe(false)
  })
})

describe('saved BOMs', () => {
  it('spots edited quantities, allowing for float noise', () => {
    expect(isEdited(line({ qty_auto: 5, qty_final: 7 }))).toBe(true)
    expect(isEdited(line({ qty_auto: 9.6, qty_final: 9.600000000000001 }))).toBe(false)
    expect(isEdited(line({ qty_auto: null, qty_final: 7 }))).toBe(false)
  })

  it('keeps edited-to-zero and added lines visible but hides plain zero lines', () => {
    const rows = frozenRows({
      status: 'saved',
      lines: [
        line({ id: 1, qty_auto: 0, qty_final: 0 }),
        line({ id: 2, qty_auto: 5, qty_final: 0 }),
        line({ id: 3, component_line_id: null, qty_auto: null, qty_final: 0 }),
      ],
    })
    expect(rows.map(isHideable)).toEqual([true, false, false])
  })

  it('hides zero lines on imported BOMs, where no line has a template line', () => {
    const rows = frozenRows({
      status: 'imported',
      lines: [line({ id: 1, component_line_id: null, qty_auto: 0, qty_final: 0 }), line({ id: 2, component_line_id: null, qty_auto: 3, qty_final: 3 })],
    })
    expect(rows.map(isHideable)).toEqual([true, false])
  })
})

describe('rateWarning', () => {
  it('passes on a unit mismatch but not the no-rate case, which has its own badge', () => {
    expect(rateWarning(line({ warning: 'Rate is per Kg', rate_source: 'bom' }))).toBe('Rate is per Kg')
    expect(rateWarning(line({ warning: 'No rate found', rate_source: 'none' }))).toBeNull()
    expect(rateWarning(line())).toBeNull()
  })
})

describe('quantities', () => {
  it('shows up to three decimals without a float tail', () => {
    expect(qtyText(9.600000000000001)).toBe('9.6')
    expect(qtyText(1.23456)).toBe('1.235')
    expect(qtyText(0)).toBe('0')
    expect(qtyText(null)).toBe('')
  })

  it('parses typed quantities', () => {
    expect(parseQty('12.5')).toBe(12.5)
    expect(parseQty(' 1,000 ')).toBe(1000)
    expect(parseQty('0')).toBe(0)
    expect(parseQty('')).toBeNull()
    expect(parseQty('abc')).toBeNull()
    expect(parseQty('-1')).toBeNull()
    expect(parseQty('Infinity')).toBeNull()
  })
})
