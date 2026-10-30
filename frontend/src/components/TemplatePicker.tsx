import { Alert, Select, Stack, Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Order, SignType, TemplateSummary } from '../api/types'

interface Props {
  order: Order
  signTypes: SignType[]
  signTypeId: number | null
  templateId: number | null
  onSignTypeChange: (id: number | null) => void
  onTemplateChange: (id: number | null) => void
}

/** Shown when the order's sign type has no published template, so the choice of a draft is a deliberate one. */
export function TemplatePicker({ order, signTypes, signTypeId, templateId, onSignTypeChange, onTemplateChange }: Props) {
  const templates = useQuery({
    queryKey: ['sign-type-templates', signTypeId],
    queryFn: ({ signal }) => api<TemplateSummary[]>(`/sign-types/${signTypeId}/templates`, { signal }),
    enabled: signTypeId !== null,
  })
  const usable = (templates.data ?? []).filter((t) => t.status !== 'retired')
  const mapped = signTypes.find((s) => s.id === order.sign_type_id)

  return (
    <Alert color="yellow" p="xs" title={<Text size="xs" fw={600}>{mapped ? `“${mapped.name}” has no published template` : 'This order has no mapped sign type'}</Text>}>
      <Stack gap={6}>
        <Text size="xs">Choose a template to cost this order with.</Text>
        <Select
          size="xs"
          label="Sign type"
          searchable
          data={signTypes.filter((s) => s.template_count > 0).map((s) => ({ value: String(s.id), label: s.name }))}
          value={signTypeId === null ? null : String(signTypeId)}
          onChange={(v) => onSignTypeChange(v ? Number(v) : null)}
        />
        <Select
          size="xs"
          label="Template"
          placeholder={signTypeId === null ? 'Pick a sign type first' : usable.length ? 'Choose a template' : 'No templates'}
          disabled={signTypeId === null || usable.length === 0}
          data={usable.map((t) => ({
            value: String(t.id),
            label: `v${t.version} · ${t.status} · ${t.line_count} lines${t.flagged_lines ? ` · ${t.flagged_lines} flagged` : ''}`,
          }))}
          value={templateId === null ? null : String(templateId)}
          onChange={(v) => onTemplateChange(v ? Number(v) : null)}
        />
      </Stack>
    </Alert>
  )
}
