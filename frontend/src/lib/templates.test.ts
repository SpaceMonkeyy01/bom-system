import { describe, expect, it } from 'vitest'
import type { Template } from '../api/types'
import { classifyProblem, costTagsPresent, describeKinds, describeLineKey, draftFromTemplate, indexProblems, insertAt, isValidParamName, move, parseOptions, sanitizeParamName, toBody } from './templates'

describe('flag kinds', () => {
  it('reads the import notes', () => {
    expect(classifyProblem('no formula in source')).toBe('typed number')
    expect(classifyProblem('Unknown input “Foo”')).toBe('unknown input')
    expect(classifyProblem('Unexpected “face”. Check for a missing + - * or /')).toBe('parse error')
    expect(classifyProblem('Expected “)”')).toBe('parse error')
    expect(classifyProblem('check me')).toBe('other')
  })

  it('summarises them most common first', () => {
    expect(describeKinds(['no formula in source', 'no formula in source', 'Unknown input “x”'])).toBe('2 typed numbers, 1 unknown input')
    expect(describeKinds(['check me'])).toBe('1 other problem')
  })
})

describe('sanitizeParamName', () => {
  it.each([
    ['Alu/SS face Crunched Area', 'Alu_SS_face_Crunched_Area'],
    ['Crunched Area SS(ft2)', 'Crunched_Area_SS_ft2'],
    ['  LOC of SS (Ft) ', 'LOC_of_SS_Ft'],
    ['3D depth', '_3D_depth'],
    ['', 'Param'],
    ['///', 'Param'],
  ])('%s -> %s', (label, expected) => {
    expect(sanitizeParamName(label)).toBe(expected)
  })

  it('always gives a valid identifier', () => {
    for (const label of ['a b', '9', 'x-y', 'é', 'Finish']) expect(isValidParamName(sanitizeParamName(label))).toBe(true)
    expect(isValidParamName('has space')).toBe(false)
  })
})

describe('draft round trip', () => {
  const template = {
    id: 1,
    notes: 'n',
    parameters: [
      { id: 1, seq: 0, label: 'Face Area', param_name: 'Face_Area', uom: 'sqft', input_type: 'number', options: [], default_value: null, default_from_order: null, required: true },
      { id: 2, seq: 1, label: 'Finish', param_name: 'Fin', uom: null, input_type: 'select', options: ['Matt', 'Gloss'], default_value: null, default_from_order: 'finish', required: false },
    ],
    lines: [
      { id: 5, seq: 0, material_id: 7, material_name: 'SS Metal', qty_formula: 'Face_Area * 1.2', unit_cost_formula: null, uom: 'Sqft', usage: 'Face', cost_tag: 'Metal', work_centre: null, wastage_pct: null, optional: false, notes: 'check' },
      { id: 6, seq: 1, material_id: null, material_name: 'Mystery', qty_formula: '1', unit_cost_formula: null, uom: null, usage: null, cost_tag: 'Misc', work_centre: null, wastage_pct: 5, optional: true, notes: null },
    ],
  } as unknown as Template

  it('keeps the API fields and drops the client ones', () => {
    const draft = draftFromTemplate(template)
    const body = toBody(draft)
    expect(body.notes).toBe('n')
    expect(body.parameters[0]).toEqual({ label: 'Face Area', param_name: 'Face_Area', uom: 'sqft', input_type: 'number', options: [], default_value: null, default_from_order: null, required: true })
    expect(body.lines[0]).toEqual({ material_id: 7, material_name_hint: null, qty_formula: 'Face_Area * 1.2', unit_cost_formula: null, uom: 'Sqft', usage: 'Face', cost_tag: 'Metal', work_centre: null, wastage_pct: null, optional: false, notes: 'check' })
    expect('key' in body.lines[0]).toBe(false)
    expect('material_name' in body.lines[0]).toBe(false)
  })

  it('keeps the name of an unresolved material as the hint', () => {
    expect(toBody(draftFromTemplate(template)).lines[1].material_name_hint).toBe('Mystery')
  })

  it('knows when a parameter name was set by hand, so it stops following the label', () => {
    const draft = draftFromTemplate(template)
    expect(draft.parameters[0].nameTouched).toBe(false)
    expect(draft.parameters[1].nameTouched).toBe(true)
  })
})

describe('indexProblems', () => {
  it('groups by row and keeps template-level ones apart', () => {
    const idx = indexProblems([
      { where: 'line:3', message: 'a' },
      { where: 'line:3', message: 'b' },
      { where: 'param:0', message: 'c' },
      { where: 'template', message: 'd' },
      { where: 'odd', message: 'e' },
    ])
    expect(idx.lines.get(3)).toEqual(['a', 'b'])
    expect(idx.params.get(0)).toEqual(['c'])
    expect(idx.template).toEqual(['d', 'e'])
  })
})

describe('helpers', () => {
  it('lists cost tags once, in order, skipping blanks', () => {
    expect(costTagsPresent([{ cost_tag: 'Metal' }, { cost_tag: ' ' }, { cost_tag: 'Paint' }, { cost_tag: 'Metal' }, { cost_tag: null }])).toEqual(['Metal', 'Paint'])
  })

  it('inserts at the caret with a separating space when needed', () => {
    expect(insertAt('Face_Area *', 11, 11, 'Depth')).toEqual({ value: 'Face_Area * Depth', caret: 17 })
    expect(insertAt('', 0, 0, 'Depth')).toEqual({ value: 'Depth', caret: 5 })
    expect(insertAt('QTY(', 4, 4, '"Metal"')).toEqual({ value: 'QTY("Metal"', caret: 11 })
    expect(insertAt('a + b', 2, 3, 'c').value).toBe('a c b')
  })

  it('moves rows within bounds', () => {
    expect(move([1, 2, 3], 0, 2)).toEqual([2, 3, 1])
    expect(move([1, 2, 3], 2, 1)).toEqual([1, 3, 2])
    expect(move([1, 2, 3], 0, -1)).toEqual([1, 2, 3])
    expect(move([1, 2, 3], 2, 3)).toEqual([1, 2, 3])
  })

  it('parses options', () => {
    expect(parseOptions(' Matt, Gloss ,, Matt ')).toEqual(['Matt', 'Gloss'])
  })

  it('describes diff line keys', () => {
    expect(describeLineKey('SS Metal|Face|0')).toBe('SS Metal · Face')
    expect(describeLineKey('SS Metal||3')).toBe('SS Metal')
  })
})
