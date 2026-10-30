import { NumberInput, Paper, Select, SimpleGrid, Text } from '@mantine/core'
import type { Parameter } from '../api/types'
import type { ParamValue } from '../lib/bom'

interface Props {
  parameters: Parameter[]
  values: Record<string, ParamValue | undefined>
  errors: Record<string, string>
  onChange: (name: string, value: ParamValue) => void
}

export function ParameterForm({ parameters, values, errors, onChange }: Props) {
  if (parameters.length === 0) {
    return (
      <Text size="xs" c="dimmed">
        This template has no parameters.
      </Text>
    )
  }
  return (
    <Paper withBorder p="xs">
      <SimpleGrid cols={2} spacing="xs" verticalSpacing={6}>
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
          return (
            <NumberInput
              key={p.id}
              size="xs"
              label={p.label}
              value={value}
              hideControls
              allowNegative={false}
              withAsterisk={p.required}
              error={errors[p.param_name]}
              rightSection={p.uom ? <Text size="xs" c="dimmed">{p.uom}</Text> : undefined}
              rightSectionWidth={p.uom ? Math.max(28, p.uom.length * 8 + 10) : undefined}
              rightSectionPointerEvents="none"
              onChange={(v) => onChange(p.param_name, v)}
            />
          )
        })}
      </SimpleGrid>
    </Paper>
  )
}
