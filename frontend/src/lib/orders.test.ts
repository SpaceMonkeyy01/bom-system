import { describe, expect, it } from 'vitest'
import type { SignType } from '../api/types'
import { orderStatus, templateProblem } from './orders'

const today = new Date(2026, 9, 30)
const base = { bom_count: 0, dispatch_by: '2026-11-05', airtable_bom_done: false, status: 'New' }

describe('orderStatus', () => {
  it('puts a saved BOM first, whatever the date', () => {
    expect(orderStatus({ ...base, bom_count: 2, dispatch_by: '2026-10-01' }, today)).toEqual({ tone: 'done', word: 'BOM saved' })
  })

  it('reads urgency from the dispatch date', () => {
    expect(orderStatus({ ...base, dispatch_by: '2026-10-28' }, today).word).toBe('Overdue')
    expect(orderStatus({ ...base, dispatch_by: '2026-10-30' }, today).word).toBe('Due today')
    expect(orderStatus({ ...base, dispatch_by: '2026-10-31' }, today).word).toBe('Needs BOM')
    expect(orderStatus({ ...base, dispatch_by: null }, today).word).toBe('Needs BOM')
  })

  it('treats an order done in Airtable as not needing one', () => {
    expect(orderStatus({ ...base, airtable_bom_done: true, dispatch_by: '2026-10-01' }, today).word).toBe('Done in sheet')
  })
})

describe('templateProblem', () => {
  const signTypes = [
    { id: 1, published_template_id: 9 },
    { id: 2, published_template_id: null },
  ] as SignType[]

  it('names the Airtable text when nothing matched it', () => {
    expect(templateProblem({ sign_type_id: null, sign_type_raw: 'Fancy Sign' }, signTypes)).toBe('Unmapped: “Fancy Sign”')
    expect(templateProblem({ sign_type_id: null, sign_type_raw: null }, signTypes)).toBe('No sign type')
  })

  it('flags a mapped sign type with nothing published', () => {
    expect(templateProblem({ sign_type_id: 2, sign_type_raw: 'x' }, signTypes)).toBe('No published template')
    expect(templateProblem({ sign_type_id: 1, sign_type_raw: 'x' }, signTypes)).toBeNull()
    expect(templateProblem({ sign_type_id: 2, sign_type_raw: 'x' }, undefined)).toBeNull()
  })
})
