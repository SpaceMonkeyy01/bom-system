import { Alert, Anchor, Button, Center, Group, Loader, Paper, Text } from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import type { Bom, Order, SignType, Template } from '../api/types'
import { useAuth } from '../auth/AuthProvider'
import { BomLinesTable } from '../components/BomLinesTable'
import { OrderFacts } from '../components/OrderFacts'
import { ParameterForm } from '../components/ParameterForm'
import { QtyInput } from '../components/QtyInput'
import { TemplatePicker } from '../components/TemplatePicker'
import { type BomDraft, buildRequest, buildRows, type DraftExtra, type ParamValue } from '../lib/bom'
import { fmtPkr } from '../lib/format'

const PREVIEW_DEBOUNCE_MS = 300
const BAR_HEIGHT = 46

export function CreateBomPage() {
  const orderId = Number(useParams().orderId)
  const { canWrite } = useAuth()
  // Preview and save both need bom:write, so anyone else gets the read-only order page.
  if (!canWrite) return <Navigate to={`/orders/${orderId}`} replace />
  return <CreateBom key={orderId} orderId={orderId} />
}

function CreateBom({ orderId }: { orderId: number }) {
  const order = useQuery({
    queryKey: ['order', orderId],
    queryFn: ({ signal }) => api<Order>(`/orders/${orderId}`, { signal }),
  })
  const signTypes = useQuery({
    queryKey: ['sign-types'],
    queryFn: ({ signal }) => api<SignType[]>('/sign-types', { signal }),
  })

  const [pickedSignTypeId, setPickedSignTypeId] = useState<number | null | undefined>(undefined)
  const [pickedTemplateId, setPickedTemplateId] = useState<number | null>(null)
  const [params, setParams] = useState<Record<string, ParamValue>>({})
  const [overrides, setOverrides] = useState<Record<number, number>>({})
  const [extras] = useState<DraftExtra[]>([])

  const publishedId = signTypes.data?.find((s) => s.id === order.data?.sign_type_id)?.published_template_id ?? null
  const templateId = publishedId ?? pickedTemplateId
  const signTypeId = pickedSignTypeId !== undefined ? pickedSignTypeId : (order.data?.sign_type_id ?? null)

  const template = useQuery({
    queryKey: ['template', templateId],
    queryFn: ({ signal }) => api<Template>(`/templates/${templateId}`, { signal }),
    enabled: templateId !== null,
  })

  const draft = useMemo<BomDraft | null>(
    () => (templateId === null ? null : { orderId, templateId, params, overrides, extras, miscPct: null }),
    [orderId, templateId, params, overrides, extras],
  )
  const [debounced] = useDebouncedValue(draft, PREVIEW_DEBOUNCE_MS)

  const preview = useQuery({
    queryKey: ['bom-preview', debounced],
    queryFn: async ({ signal }) => ({
      bom: await api<Bom>('/boms/preview', { json: buildRequest(debounced!), signal }),
      extraKeys: debounced!.extras.map((e) => e.key),
    }),
    enabled: debounced !== null,
    retry: false,
    gcTime: 60_000,
    // Keep the table steady while editing, but never show another template's lines.
    placeholderData: (previous, previousQuery) =>
      (previousQuery?.queryKey[1] as BomDraft | null)?.templateId === debounced?.templateId ? previous : undefined,
  })

  // The debounce trails a template switch, so this also guards against one render of the old template's lines.
  const current = debounced?.templateId === templateId ? preview.data : undefined
  const bom = current?.bom

  // Defaults come from the server. What the user typed wins; whatever they left alone stays out of the request.
  const values = { ...bom?.parameters, ...params }

  const rows = useMemo(
    () => (current ? buildRows(current.bom.lines, current.extraKeys, extras, overrides, template.data?.lines) : []),
    [current, extras, overrides, template.data],
  )

  function chooseTemplate(id: number | null) {
    setPickedTemplateId(id)
    // Overrides are keyed by the old template's line ids, and its inputs don't apply to the new one.
    setParams({})
    setOverrides({})
  }

  if (order.isPending || signTypes.isPending) {
    return (
      <Center p="xl">
        <Loader />
      </Center>
    )
  }
  if (order.isError || signTypes.isError) {
    return (
      <Alert color="red" title="Couldn’t load this order">
        <Text size="sm" mb="xs">
          {errorMessage(order.error ?? signTypes.error)}
        </Text>
        <Anchor component={Link} to="/" size="sm">
          Back to the queue
        </Anchor>
      </Alert>
    )
  }

  const updating = draft !== debounced || preview.isFetching

  return (
    <div className="bom-page">
      <aside className="bom-side">
        <OrderFacts order={order.data} />
        {order.data.bom_count > 0 && (
          <Alert color="blue" p="xs">
            <Text size="xs">
              This order already has {order.data.bom_count} saved version{order.data.bom_count === 1 ? '' : 's'}.{' '}
              <Anchor component={Link} to={`/orders/${orderId}`} size="xs">
                See them
              </Anchor>
              . Saving here adds a new one.
            </Text>
          </Alert>
        )}
        {publishedId === null ? (
          <TemplatePicker
            order={order.data}
            signTypes={signTypes.data}
            signTypeId={signTypeId}
            templateId={pickedTemplateId}
            onSignTypeChange={(id) => {
              setPickedSignTypeId(id)
              chooseTemplate(null)
            }}
            onTemplateChange={chooseTemplate}
          />
        ) : (
          template.data && (
            <Text size="xs" c="dimmed">
              Template: {template.data.sign_type_name} v{template.data.version} ({template.data.status})
            </Text>
          )
        )}
        {template.isError && (
          <Alert color="red" p="xs">
            <Text size="xs">{errorMessage(template.error)}</Text>
          </Alert>
        )}
        {template.data && (
          <ParameterForm
            parameters={template.data.parameters}
            values={values}
            errors={bom?.input_errors ?? {}}
            onChange={(name, value) => setParams((prev) => ({ ...prev, [name]: value }))}
          />
        )}
      </aside>

      <section className="bom-main">
        <Paper withBorder className="bom-bar" style={{ minHeight: BAR_HEIGHT }}>
          <Group gap="lg" wrap="nowrap">
            <Text size="sm" fw={700}>
              {bom ? `PKR ${fmtPkr(bom.grand_total_pkr)}` : '—'}
            </Text>
            {updating && templateId !== null && <Loader size={14} aria-label="Updating" />}
          </Group>
        </Paper>

        {templateId === null ? (
          <Paper withBorder p="xl">
            <Center>
              <Text c="dimmed" size="sm">
                Choose a template to see the lines.
              </Text>
            </Center>
          </Paper>
        ) : preview.isError ? (
          <Alert color="red" title="Couldn’t calculate this BOM" mb="xs">
            <Text size="sm" mb="xs">
              {errorMessage(preview.error)}
            </Text>
            <Button size="xs" variant="default" onClick={() => preview.refetch()}>
              Try again
            </Button>
          </Alert>
        ) : !bom ? (
          <Center p="xl">
            <Loader />
          </Center>
        ) : (
          <BomLinesTable
            rows={rows}
            stickyOffset={BAR_HEIGHT}
            renderQty={(row) => {
              const id = row.line.component_line_id
              if (id === null) return row.line.qty_final
              return (
                <>
                  <QtyInput
                    value={row.line.qty_final}
                    label={`Quantity of ${row.line.material_name}`}
                    edited={row.overridden}
                    onChange={(qty) => setOverrides((prev) => ({ ...prev, [id]: qty }))}
                    onClear={() =>
                      setOverrides((prev) => {
                        const { [id]: _removed, ...rest } = prev
                        return rest
                      })
                    }
                  />
                  <button
                    type="button"
                    className="qty-reset"
                    style={{ visibility: row.overridden ? 'visible' : 'hidden' }}
                    title={`Reset to formula: ${row.line.qty_formula ?? ''} = ${row.line.qty_auto ?? ''}`}
                    aria-label={`Reset ${row.line.material_name} to formula`}
                    onClick={() =>
                      setOverrides((prev) => {
                        const { [id]: _removed, ...rest } = prev
                        return rest
                      })
                    }
                  >
                    ↺
                  </button>
                </>
              )
            }}
          />
        )}
      </section>
    </div>
  )
}
