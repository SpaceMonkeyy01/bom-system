import { NumberInput, Paper, Select, SimpleGrid, Text } from '@mantine/core'
import type { Parameter } from '../api/types'
import type { ParamValue } from '../lib/bom'

interface Props {
  parameters: Parameter[]
  values: Record<string, ParamValue | undefined>
  /** Names the user has entered themselves. Any other value is the template's default. */
  entered: Record<string, ParamValue>
  errors: Record<string, string>
  onChange: (name: string, value: ParamValue) => void
}

// The sheets use "N/A - Number" for plain counts, which isn't a unit worth showing.
const unitOf = (p: Parameter) => (p.uom && !/^n\/?a\b/i.test(p.uom) ? p.uom : null)

export function ParameterForm({ parameters, values, entered, errors, onChange }: Props) {
  if (parameters.length === 0) {
    return (
      <Text size="xs" c="dimmed">
        This template has no parameters.
      </Text>
    )
  }
  return (
    <Paper withBorder p="xs">
      <SimpleGrid cols={2} spacing="xs" verticalSpacing={6} style={{ alignItems: 'end' }}>
        {parameters.map((p) => {
          const value = values[p.param_name] ?? ''
          if (p.input_type === 'select') {
            // Sheet-imported options can repeat, and a default may not be listed; the Select needs unique values.
            const options = [...new Set([...p.options, ...(value === '' ? [] : [String(value)])])].filter(Boolean)
            return (
              <Select
                key={p.id}
                size="xs"
                label={p.label}
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
          // Defaults look entered but are often just 1.0 from the sheet, so they mustn't read as someone's measurement.
          const isDefault = !(p.param_name in entered) && value !== ''
          return (
            <NumberInput
              key={p.id}
              size="xs"
              label={p.label}
              className={isDefault ? 'param-default' : undefined}
              title={isDefault ? 'Template default, not entered for this order' : undefined}
              value={value}
              hideControls
              allowNegative={false}
              withAsterisk={p.required}
              error={errors[p.param_name]}
              rightSection={unit ? <Text size="xs" c="dimmed">{unit}</Text> : undefined}
              rightSectionWidth={unit ? Math.max(28, unit.length * 7 + 10) : undefined}
              rightSectionPointerEvents="none"
              onChange={(v) => onChange(p.param_name, v)}
            />
          )
        })}
      </SimpleGrid>
    </Paper>
  )
}
