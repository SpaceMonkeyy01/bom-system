import { Button, Checkbox, Group, NumberInput, Select, Table, Text, TextInput, Tooltip } from '@mantine/core'
import { type FocusEvent, useRef, useState } from 'react'
import type { CostHead } from '../../api/types'
import { costTagsPresent, duplicateLine, emptyLine, insertAt, type LineRow, move } from '../../lib/templates'
import { MaterialPicker } from '../MaterialPicker'
import { FormulaChips } from './FormulaChips'
import { RowActions } from './ParamsTable'
import { RowProblems } from './RowProblems'

interface Props {
  lines: LineRow[]
  problems: Map<number, string[]>
  paramNames: string[]
  costHeads: CostHead[]
  readOnly: boolean
  onChange: (lines: LineRow[]) => void
}

type FormulaField = 'qty_formula' | 'unit_cost_formula'

export function LinesTable({ lines, problems, paramNames, costHeads, readOnly, onChange }: Props) {
  // The formula field that last had focus, so a chip knows where to insert.
  const activeRef = useRef<{ key: string; field: FormulaField; el: HTMLInputElement } | null>(null)
  const [activeKey, setActiveKey] = useState<string | null>(null)

  const update = (i: number, change: Partial<LineRow>) => onChange(lines.map((l, j) => (j === i ? { ...l, ...change } : l)))

  function insert(text: string) {
    const active = activeRef.current
    if (!active) return
    const i = lines.findIndex((l) => l.key === active.key)
    if (i < 0) return
    const el = active.el
    const { value, caret } = insertAt(el.value, el.selectionStart ?? el.value.length, el.selectionEnd ?? el.value.length, text)
    update(i, { [active.field]: value })
    requestAnimationFrame(() => {
      el.focus()
      el.setSelectionRange(caret, caret)
    })
  }

  const onFormulaFocus = (key: string, field: FormulaField) => (e: FocusEvent<HTMLInputElement>) => {
    activeRef.current = { key, field, el: e.currentTarget }
    setActiveKey(`${key}:${field}`)
  }

  const tags = costTagsPresent(lines)
  const headNames = costHeads.map((h) => h.name)
  const tagOptions = [...new Set([...headNames, ...tags])]
  const wastageOf = (tag: string | null) => costHeads.find((h) => h.name === tag)?.default_wastage_pct

  return (
    <>
      {!readOnly && <FormulaChips paramNames={paramNames} costTags={tags} active={activeKey !== null} onInsert={insert} />}
      <div className="table-wrap editor-table-wrap">
        <Table className="dense-table editor-table lines-editor" data-testid="lines-table">
          <Table.Thead>
            <Table.Tr>
              <Table.Th w={28}>#</Table.Th>
              <Table.Th>Material</Table.Th>
              <Table.Th>Usage</Table.Th>
              <Table.Th>Quantity formula</Table.Th>
              <Table.Th>UOM</Table.Th>
              <Table.Th>Unit cost formula</Table.Th>
              <Table.Th>Cost tag</Table.Th>
              <Table.Th>Work centre</Table.Th>
              <Table.Th className="num">Wastage %</Table.Th>
              <Table.Th>Opt.</Table.Th>
              {!readOnly && <Table.Th aria-label="Actions" />}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {lines.map((l, i) => {
              const probs = problems.get(i)
              const inherited = wastageOf(l.cost_tag)
              return (
                <Table.Tr key={l.key} className={`${probs ? 'row-problem' : ''}${l.notes ? ' row-flagged' : ''}`} data-testid={`line-${i}`}>
                  <Table.Td c="dimmed">{i + 1}</Table.Td>
                  <Table.Td>
                    <MaterialPicker
                      materialId={l.material_id}
                      materialName={l.material_name ?? l.material_name_hint}
                      disabled={readOnly}
                      label={`Material of line ${i + 1}`}
                      onChange={(m) =>
                        update(i, {
                          material_id: m?.id ?? null,
                          material_name: m?.name ?? null,
                          material_name_hint: m ? null : l.material_name_hint,
                          // a fresh line takes the material's unit and cost head; an edited one keeps what was set
                          uom: l.uom ?? m?.uom ?? null,
                          cost_tag: l.cost_tag ?? m?.cost_tag ?? null,
                        })
                      }
                    />
                    {l.notes && (
                      <div className="line-flag-note">
                        <Tooltip label="Flagged by the import" withinPortal>
                          <span className="line-flag">⚑</span>
                        </Tooltip>{' '}
                        {l.notes}
                        {!readOnly && (
                          <button type="button" className="link-button" onClick={() => update(i, { notes: null })} aria-label={`Clear flag on line ${i + 1}`}>
                            clear
                          </button>
                        )}
                      </div>
                    )}
                    <RowProblems messages={probs} />
                  </Table.Td>
                  <Table.Td>
                    <TextInput size="xs" className="compact-number" w={110} aria-label={`Usage of line ${i + 1}`} value={l.usage ?? ''} disabled={readOnly} onChange={(e) => update(i, { usage: e.currentTarget.value || null })} />
                  </Table.Td>
                  <Table.Td>
                    <input
                      className={`formula-input${activeKey === `${l.key}:qty_formula` ? ' formula-input-active' : ''}`}
                      aria-label={`Quantity formula of line ${i + 1}`}
                      value={l.qty_formula}
                      disabled={readOnly}
                      spellCheck={false}
                      onFocus={onFormulaFocus(l.key, 'qty_formula')}
                      onChange={(e) => update(i, { qty_formula: e.currentTarget.value })}
                    />
                  </Table.Td>
                  <Table.Td>
                    <TextInput size="xs" className="compact-number" w={64} aria-label={`Unit of line ${i + 1}`} value={l.uom ?? ''} disabled={readOnly} onChange={(e) => update(i, { uom: e.currentTarget.value || null })} />
                  </Table.Td>
                  <Table.Td>
                    <input
                      className={`formula-input formula-input-cost${activeKey === `${l.key}:unit_cost_formula` ? ' formula-input-active' : ''}`}
                      aria-label={`Unit cost formula of line ${i + 1}`}
                      placeholder="material rate"
                      value={l.unit_cost_formula ?? ''}
                      disabled={readOnly}
                      spellCheck={false}
                      onFocus={onFormulaFocus(l.key, 'unit_cost_formula')}
                      onChange={(e) => update(i, { unit_cost_formula: e.currentTarget.value || null })}
                    />
                  </Table.Td>
                  <Table.Td>
                    <Select
                      size="xs"
                      className="compact-select"
                      w={120}
                      aria-label={`Cost tag of line ${i + 1}`}
                      searchable
                      clearable
                      data={tagOptions}
                      value={l.cost_tag}
                      disabled={readOnly}
                      onChange={(v) => update(i, { cost_tag: v })}
                    />
                  </Table.Td>
                  <Table.Td>
                    <TextInput size="xs" className="compact-number" w={90} aria-label={`Work centre of line ${i + 1}`} value={l.work_centre ?? ''} disabled={readOnly} onChange={(e) => update(i, { work_centre: e.currentTarget.value || null })} />
                  </Table.Td>
                  <Table.Td className="num">
                    <NumberInput
                      size="xs"
                      className="compact-number"
                      w={64}
                      aria-label={`Wastage of line ${i + 1}`}
                      hideControls
                      allowNegative={false}
                      placeholder={inherited !== undefined ? String(inherited) : ''}
                      value={l.wastage_pct ?? ''}
                      disabled={readOnly}
                      onChange={(v) => update(i, { wastage_pct: v === '' ? null : Number(v) })}
                    />
                  </Table.Td>
                  <Table.Td>
                    <Tooltip label="Optional lines may have no material and still publish" withinPortal>
                      <Checkbox size="xs" aria-label={`Line ${i + 1} optional`} checked={l.optional} disabled={readOnly} onChange={(e) => update(i, { optional: e.currentTarget.checked })} />
                    </Tooltip>
                  </Table.Td>
                  {!readOnly && (
                    <Table.Td className="nowrap">
                      <RowActions
                        label={`line ${i + 1}`}
                        onDuplicate={() => onChange([...lines.slice(0, i + 1), duplicateLine(l), ...lines.slice(i + 1)])}
                        onUp={i > 0 ? () => onChange(move(lines, i, i - 1)) : undefined}
                        onDown={i < lines.length - 1 ? () => onChange(move(lines, i, i + 1)) : undefined}
                        onDelete={() => onChange(lines.filter((_, j) => j !== i))}
                      />
                    </Table.Td>
                  )}
                </Table.Tr>
              )
            })}
          </Table.Tbody>
        </Table>
        {!readOnly && (
          <Group p={4} justify="space-between">
            <Button size="compact-xs" variant="subtle" onClick={() => onChange([...lines, emptyLine()])}>
              + Add line
            </Button>
            <Text size="xs" c="dimmed">
              {lines.length} lines · blank wastage uses the cost head’s default
            </Text>
          </Group>
        )}
      </div>
    </>
  )
}
