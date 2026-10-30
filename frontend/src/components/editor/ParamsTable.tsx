import { Autocomplete, Button, Checkbox, Group, Select, Table, Text, TextInput } from '@mantine/core'
import { DEFAULT_FROM_ORDER, emptyParam, isValidParamName, move, parseOptions, type ParamRow, sanitizeParamName } from '../../lib/templates'
import { RowProblems } from './RowProblems'

interface Props {
  params: ParamRow[]
  problems: Map<number, string[]>
  uoms: string[]
  readOnly: boolean
  onChange: (params: ParamRow[]) => void
}

export function ParamsTable({ params, problems, uoms, readOnly, onChange }: Props) {
  const update = (i: number, change: Partial<ParamRow>) => onChange(params.map((p, j) => (j === i ? { ...p, ...change } : p)))

  return (
    <div className="table-wrap editor-table-wrap">
      <Table className="dense-table editor-table" data-testid="params-table">
        <Table.Thead>
          <Table.Tr>
            <Table.Th w={28}>#</Table.Th>
            <Table.Th>Label</Table.Th>
            <Table.Th>Name in formulas</Table.Th>
            <Table.Th>UOM</Table.Th>
            <Table.Th>Type</Table.Th>
            <Table.Th>Choices</Table.Th>
            <Table.Th>Default</Table.Th>
            <Table.Th>From order</Table.Th>
            <Table.Th>Req.</Table.Th>
            {!readOnly && <Table.Th aria-label="Actions" />}
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {params.map((p, i) => {
            const probs = problems.get(i)
            const nameBad = !isValidParamName(p.param_name.trim())
            return (
              <Table.Tr key={p.key} className={probs ? 'row-problem' : undefined} data-testid={`param-${i}`}>
                <Table.Td c="dimmed">{i + 1}</Table.Td>
                <Table.Td>
                  <TextInput
                    size="xs"
                    className="compact-number"
                    aria-label={`Label of input ${i + 1}`}
                    value={p.label}
                    disabled={readOnly}
                    onChange={(e) => {
                      const label = e.currentTarget.value
                      // the identifier follows the label until someone edits it directly
                      update(i, p.nameTouched ? { label } : { label, param_name: sanitizeParamName(label) })
                    }}
                  />
                  <RowProblems messages={probs} />
                </Table.Td>
                <Table.Td>
                  <TextInput
                    size="xs"
                    className={`compact-number formula-font${nameBad ? ' input-bad' : ''}`}
                    aria-label={`Formula name of input ${i + 1}`}
                    value={p.param_name}
                    disabled={readOnly}
                    onChange={(e) => update(i, { param_name: e.currentTarget.value, nameTouched: true })}
                    onBlur={() => {
                      // tidy what was typed; blanking it hands control back to the label
                      if (!p.param_name.trim()) update(i, { param_name: sanitizeParamName(p.label), nameTouched: false })
                      else if (nameBad) update(i, { param_name: sanitizeParamName(p.param_name) })
                    }}
                  />
                </Table.Td>
                <Table.Td>
                  <Autocomplete
                    size="xs"
                    className="compact-number"
                    w={90}
                    aria-label={`Unit of input ${i + 1}`}
                    data={uoms}
                    value={p.uom ?? ''}
                    disabled={readOnly}
                    onChange={(v) => update(i, { uom: v || null })}
                  />
                </Table.Td>
                <Table.Td>
                  <Select
                    size="xs"
                    className="compact-select"
                    w={92}
                    aria-label={`Type of input ${i + 1}`}
                    data={[
                      { value: 'number', label: 'number' },
                      { value: 'select', label: 'dropdown' },
                    ]}
                    value={p.input_type}
                    allowDeselect={false}
                    disabled={readOnly}
                    onChange={(v) => update(i, { input_type: v === 'select' ? 'select' : 'number' })}
                  />
                </Table.Td>
                <Table.Td>
                  {p.input_type === 'select' ? (
                    <TextInput
                      size="xs"
                      className="compact-number"
                      w={180}
                      aria-label={`Choices of input ${i + 1}`}
                      placeholder="Matt, Gloss, Satin"
                      defaultValue={p.options.join(', ')}
                      disabled={readOnly}
                      onBlur={(e) => update(i, { options: parseOptions(e.currentTarget.value) })}
                    />
                  ) : (
                    <Text size="xs" c="dimmed">
                      —
                    </Text>
                  )}
                </Table.Td>
                <Table.Td>
                  <TextInput
                    size="xs"
                    className="compact-number"
                    w={70}
                    aria-label={`Default of input ${i + 1}`}
                    value={p.default_value ?? ''}
                    disabled={readOnly}
                    onChange={(e) => update(i, { default_value: e.currentTarget.value || null })}
                  />
                </Table.Td>
                <Table.Td>
                  <Select
                    size="xs"
                    className="compact-select"
                    w={110}
                    aria-label={`Order field for input ${i + 1}`}
                    placeholder="—"
                    clearable
                    data={DEFAULT_FROM_ORDER}
                    value={p.default_from_order}
                    disabled={readOnly}
                    onChange={(v) => update(i, { default_from_order: v })}
                  />
                </Table.Td>
                <Table.Td>
                  <Checkbox size="xs" aria-label={`Input ${i + 1} required`} checked={p.required} disabled={readOnly} onChange={(e) => update(i, { required: e.currentTarget.checked })} />
                </Table.Td>
                {!readOnly && (
                  <Table.Td className="nowrap">
                    <RowActions
                      onUp={i > 0 ? () => onChange(move(params, i, i - 1)) : undefined}
                      onDown={i < params.length - 1 ? () => onChange(move(params, i, i + 1)) : undefined}
                      onDelete={() => onChange(params.filter((_, j) => j !== i))}
                      label={`input ${i + 1}`}
                    />
                  </Table.Td>
                )}
              </Table.Tr>
            )
          })}
          {params.length === 0 && (
            <Table.Tr>
              <Table.Td colSpan={10}>
                <Text size="xs" c="dimmed">
                  No inputs. Formulas can still use Length_in, Width_in and Area_sqft from the order.
                </Text>
              </Table.Td>
            </Table.Tr>
          )}
        </Table.Tbody>
      </Table>
      {!readOnly && (
        <Group p={4}>
          <Button size="compact-xs" variant="subtle" onClick={() => onChange([...params, emptyParam()])}>
            + Add input
          </Button>
        </Group>
      )}
    </div>
  )
}

export function RowActions({ onUp, onDown, onDelete, onDuplicate, label }: { onUp?: () => void; onDown?: () => void; onDelete: () => void; onDuplicate?: () => void; label: string }) {
  return (
    <span className="row-actions">
      {onDuplicate && (
        <button type="button" title="Duplicate" aria-label={`Duplicate ${label}`} onClick={onDuplicate}>
          ⧉
        </button>
      )}
      <button type="button" title="Move up" aria-label={`Move ${label} up`} disabled={!onUp} onClick={onUp}>
        ↑
      </button>
      <button type="button" title="Move down" aria-label={`Move ${label} down`} disabled={!onDown} onClick={onDown}>
        ↓
      </button>
      <button type="button" className="danger" title="Delete" aria-label={`Delete ${label}`} onClick={onDelete}>
        ×
      </button>
    </span>
  )
}
