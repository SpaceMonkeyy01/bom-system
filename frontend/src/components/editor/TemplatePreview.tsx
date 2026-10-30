import { Alert, Badge, Group, Paper, Select, Text } from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { api, errorMessage } from '../../api/client'
import type { Bom, Order, Template } from '../../api/types'
import { buildRows, type ParamValue } from '../../lib/bom'
import { fmtPkr, fmtSize } from '../../lib/format'
import { BomLinesTable } from '../BomLinesTable'
import { ParameterForm } from '../ParameterForm'
import { TotalsPanel } from '../TotalsPanel'

interface Props {
  /** The template as last saved: preview runs against the database, not the editor's unsaved rows. */
  template: Template
  /** Bumped on every save so the preview refetches. */
  revision: number
  unsavedChanges: boolean
}

export function TemplatePreview({ template, revision, unsavedChanges }: Props) {
  const orders = useQuery({ queryKey: ['orders', { scope: 'all', q: '' }], queryFn: ({ signal }) => api<Order[]>('/orders', { query: { limit: 2000 }, signal }) })
  const candidates = useMemo(() => (orders.data ?? []).filter((o) => o.sign_type_id === template.sign_type_id), [orders.data, template.sign_type_id])
  const [orderId, setOrderId] = useState<number | null>(null)
  const [params, setParams] = useState<Record<string, ParamValue>>({})
  const [debounced] = useDebouncedValue(params, 300)

  // Nothing to run against until the orders are known; with none of this sign type the API would only answer 400.
  const canPreview = orderId !== null || (orders.isSuccess && candidates.length > 0)
  const preview = useQuery({
    queryKey: ['template-preview', template.id, revision, orderId, debounced],
    queryFn: ({ signal }) => api<Bom>(`/templates/${template.id}/preview`, { json: { order_id: orderId, parameters: debounced }, signal }),
    enabled: canPreview,
    retry: false,
    placeholderData: (prev) => prev,
  })
  const bom = preview.data
  const rows = useMemo(() => (bom ? buildRows(bom.lines, [], [], {}, template.lines) : []), [bom, template.lines])
  const order = candidates.find((o) => o.id === (orderId ?? bom?.order_id))

  return (
    <Paper withBorder p="xs" className="preview-panel" data-testid="preview-panel">
      <Group justify="space-between" mb={4} wrap="nowrap">
        <Text size="sm" fw={700}>
          Preview
        </Text>
        {unsavedChanges && (
          <Badge size="sm" color="orange" variant="light" tt="none">
            shows the saved draft — save to refresh
          </Badge>
        )}
      </Group>
      <Select
        size="xs"
        mb={6}
        searchable
        clearable
        aria-label="Preview order"
        placeholder={candidates.length ? 'Most recent order of this sign type' : 'No orders of this sign type yet'}
        data={candidates.map((o) => ({ value: String(o.id), label: `${o.code} · ${fmtSize(o.width_in, o.height_in)} · ${o.finish ?? '—'}` }))}
        value={orderId === null ? null : String(orderId)}
        onChange={(v) => setOrderId(v ? Number(v) : null)}
      />
      {order && (
        <Text size="xs" c="dimmed" mb={4}>
          {order.code}: {fmtSize(order.width_in, order.height_in)} in, {order.finish ?? 'no finish'}, {order.led_color ?? 'no LED'}
        </Text>
      )}
      {template.parameters.length > 0 && (
        <ParameterForm
          parameters={template.parameters}
          values={{ ...bom?.parameters, ...params }}
          entered={params}
          errors={bom?.input_errors ?? {}}
          onChange={(name, value) => setParams((p) => ({ ...p, [name]: value }))}
        />
      )}
      {preview.isError ? (
        <Alert color="red" p="xs" mt={6}>
          <Text size="xs">{errorMessage(preview.error)}</Text>
        </Alert>
      ) : bom ? (
        <div className="preview-lines">
          <Group justify="space-between" mt={6} mb={2}>
            <Text size="sm" fw={700}>
              PKR {fmtPkr(bom.grand_total_pkr)}
            </Text>
            <Group gap={4}>
              {bom.lines.some((l) => l.error) && (
                <Badge size="xs" color="red" variant="light" tt="none">
                  {bom.lines.filter((l) => l.error).length} formula errors
                </Badge>
              )}
              {preview.isFetching && (
                <Text size="xs" c="dimmed">
                  updating…
                </Text>
              )}
            </Group>
          </Group>
          <BomLinesTable rows={rows} />
          <div style={{ marginTop: 8 }}>
            <TotalsPanel bom={bom} />
          </div>
        </div>
      ) : (
        <Text size="xs" c="dimmed" mt={6}>
          {preview.isFetching ? 'Calculating…' : orders.isSuccess && !canPreview ? 'No orders of this sign type yet, so there is nothing to preview against. Map an Airtable name to it first.' : 'No preview.'}
        </Text>
      )}
    </Paper>
  )
}
