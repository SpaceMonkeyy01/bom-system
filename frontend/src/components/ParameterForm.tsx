import { NumberInput, Select, Text } from '@mantine/core'
import type { Parameter } from '../api/types'
import type { ParamValue } from '../lib/bom'

interface Props {
  parameters: Parameter[]
  values: Record<string, ParamValue | null | undefined>
  /** Names the user has entered themselves. Any other value is the template's default. */
  entered: Record<string, ParamValue>
  errors: Record<string, string>
  /** Required inputs still empty; marked so they can be found. */
  missing?: string[]
  onChange: (name: string, value: ParamValue) => void
  columns?: number
  size?: 'xs' | 'sm' | 'md'
}

// The sheets use "N/A - Number" for plain counts, which isn't a unit worth showing.
const unitOf = (p: Parameter) => (p.uom && !/^n\/?a\b/i.test(p.uom) ? p.uom : null)

export function ParameterForm({ parameters, values, entered, errors, missing = [], onChange, columns = 3, size = 'md' }: Props) {
  if (parameters.length === 0) {
    return (
      <Text size="sm" c="var(--slate)">
        This template has no inputs.
      </Text>
    )
  }
  return (
    <div className="param-grid" style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}>
      {parameters.map((p) => {
        const value = values[p.param_name] ?? ''
        const isMissing = missing.includes(p.param_name)
        const cls = isMissing ? 'param-missing' : undefined
        if (p.input_type === 'select') {
          // Sheet-imported options can repeat, and a default may not be listed; the Select needs unique values.
          const options = [...new Set([...p.options, ...(value === '' ? [] : [String(value)])])].filter(Boolean)
          return (
            <Select
              key={p.id}
              id={`param-${p.param_name}`}
              size={size}
              className={cls}
              label={p.label}
              placeholder={isMissing ? 'required' : undefined}
              data={options}
              value={value === '' ? null : String(value)}
              allowDeselect={false}
              withAsterisk={p.required}
              error={errors[p.param_name]}
              onChange={(v) => onChange(p.param_name, v ?? '')}
            />
          )
        }
        const unit = unitOf(p)
        // Defaults look entered but come from the template, so they mustn't read as someone's measurement.
        const isDefault = !(p.param_name in entered) && value !== ''
        return (
          <NumberInput
            key={p.id}
            id={`param-${p.param_name}`}
            size={size}
            label={p.label}
            className={[cls, isDefault ? 'param-default' : ''].filter(Boolean).join(' ') || undefined}
            title={isDefault ? 'Template default, not entered for this order' : undefined}
            placeholder={isMissing ? 'required' : undefined}
            value={value ?? ''}
            hideControls
            allowNegative={false}
            withAsterisk={p.required}
            error={errors[p.param_name]}
            rightSection={unit ? <Text size="xs" c="var(--slate)">{unit}</Text> : undefined}
            rightSectionWidth={unit ? Math.max(28, unit.length * 7 + 14) : undefined}
            rightSectionPointerEvents="none"
            onChange={(v) => onChange(p.param_name, v)}
          />
        )
      })}
    </div>
  )
}
