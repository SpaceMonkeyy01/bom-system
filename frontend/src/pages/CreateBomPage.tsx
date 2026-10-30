import { Alert, Anchor, Badge, Button, Center, Group, List, Loader, NumberInput, Paper, Select, Stack, Table, Text, TextInput } from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useRef, useState } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import type { Bom, MaterialSearchResult, Order, SignType, Template } from '../api/types'
import { useAuth } from '../auth/AuthProvider'
import { AddMaterial } from '../components/AddMaterial'
import { BomLinesTable } from '../components/BomLinesTable'
import { OrderFacts } from '../components/OrderFacts'
import { PageError, PageLoader } from '../components/PageState'
import { ParameterForm } from '../components/ParameterForm'
import { QtyInput } from '../components/QtyInput'
import { TemplatePicker } from '../components/TemplatePicker'
import { TotalsPanel } from '../components/TotalsPanel'
import { type BomDraft, buildRequest, buildRows, type DraftExtra, isUnpriced, type LineRow, missingRequired, type ParamValue, rateWarning } from '../lib/bom'
import { fmtPkr, fmtUsd } from '../lib/format'

const PREVIEW_DEBOUNCE_MS = 300
const BAR_HEIGHT = 46
const DEFAULT_EXTRA_HEAD = 'Misc'

export function CreateBomPage() {
  const orderId = Number(useParams().orderId)
  const { canWrite } = useAuth()
  // Preview and save both need bom:write, so anyone else gets the read-only order page.
  if (!canWrite) return <Navigate to={`/orders/${orderId}`} replace />
  return <CreateBom key={orderId} orderId={orderId} />
}

function CreateBom({ orderId }: { orderId: number }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
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
  const [extras, setExtras] = useState<DraftExtra[]>([])
  const [miscInput, setMiscInput] = useState<string | number | undefined>(undefined)
  const [boxDimension, setBoxDimension] = useState('')
  const [shipmentUsd, setShipmentUsd] = useState<string | number>('')
  const nextExtraKey = useRef(1)

  const publishedId = signTypes.data?.find((s) => s.id === order.data?.sign_type_id)?.published_template_id ?? null
  const templateId = publishedId ?? pickedTemplateId
  const signTypeId = pickedSignTypeId !== undefined ? pickedSignTypeId : (order.data?.sign_type_id ?? null)
  // A cleared box means "use the default", which the server applies.
  const miscPct = miscInput === undefined || miscInput === '' ? null : Number(miscInput)

  const template = useQuery({
    queryKey: ['template', templateId],
    queryFn: ({ signal }) => api<Template>(`/templates/${templateId}`, { signal }),
    enabled: templateId !== null,
  })

  const draft = useMemo<BomDraft | null>(
    () => (templateId === null ? null : { orderId, templateId, params, overrides, extras, miscPct }),
    [orderId, templateId, params, overrides, extras, miscPct],
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

  // Offered on added lines until the API lists cost heads (API_REQUESTS.md #3).
  const costHeads = useMemo(() => {
    const names = new Set<string>([DEFAULT_EXTRA_HEAD, ...extras.flatMap((e) => (e.cost_tag ? [e.cost_tag] : []))])
    for (const line of bom?.lines ?? []) if (line.cost_head) names.add(line.cost_head)
    return [...names].sort()
  }, [bom, extras])

  const save = useMutation({
    mutationFn: () =>
      api<Bom>('/boms', {
        json: {
          ...buildRequest(draft!),
          box_dimension: boxDimension.trim() || null,
          est_shipment_cost_usd: shipmentUsd === '' ? null : Number(shipmentUsd),
        },
      }),
    onSuccess: (saved) => {
      // The order leaves the queue and its version list and dashboard counts have changed.
      for (const key of ['orders', 'order', 'order-boms', 'dashboard']) queryClient.invalidateQueries({ queryKey: [key] })
      navigate(`/boms/${saved.id}`, { state: { justSaved: true } })
    },
  })

  function chooseTemplate(id: number | null) {
    setPickedTemplateId(id)
    // Overrides are keyed by the old template's line ids, and its inputs don't apply to the new one.
    setParams({})
    setOverrides({})
  }

  function clearOverride(id: number) {
    setOverrides((prev) => {
      const { [id]: _removed, ...rest } = prev
      return rest
    })
  }

  function addExtra(material: MaterialSearchResult) {
    const key = String(nextExtraKey.current++)
    setExtras((prev) => [...prev, { key, material_id: material.id, name: material.name, qty: 1, cost_tag: DEFAULT_EXTRA_HEAD, uom: material.uom }])
  }

  function updateExtra(key: string, change: Partial<DraftExtra>) {
    setExtras((prev) => prev.map((e) => (e.key === key ? { ...e, ...change } : e)))
  }

  if (order.isPending || signTypes.isPending) return <PageLoader />
  if (order.isError || signTypes.isError) return <PageError title="Couldn’t load this order" error={order.error ?? signTypes.error} />

  const updating = draft !== debounced || preview.isFetching

  const lines = bom?.lines ?? []
  const errorLines = lines.filter((l) => l.error).length
  const inputErrors = Object.keys(bom?.input_errors ?? {})
  const missing = template.data ? missingRequired(template.data.parameters, values) : []
  const blockers = [
    ...(missing.length ? [`Fill in ${missing.map((p) => p.label).join(', ')}.`] : []),
    ...(inputErrors.length ? [`Fix ${inputErrors.join(', ')}: ${Object.values(bom!.input_errors).join('; ')}.`] : []),
    ...(errorLines ? [`${errorLines} line${errorLines === 1 ? ' has' : 's have'} a formula error. The template needs fixing before this can be saved.`] : []),
  ]
  // Never save a figure nobody has seen: wait until the preview matches what's on screen.
  const canSave = !!bom && !updating && !preview.isError && blockers.length === 0 && !save.isPending

  const unpriced = lines.filter(isUnpriced).length
  const stale = lines.filter((l) => l.rate_stale && l.rate_source !== 'none' && l.qty_final > 0).length
  const mismatched = lines.filter(rateWarning).length

  const renderQty = (row: LineRow) => {
    const { line, extraKey } = row
    if (extraKey) {
      const extra = extras.find((e) => e.key === extraKey)
      return (
        <>
          <QtyInput
            value={extra?.qty ?? line.qty_final}
            label={`Quantity of ${line.material_name}`}
            onChange={(qty) => updateExtra(extraKey, { qty })}
            onClear={() => updateExtra(extraKey, { qty: 0 })}
          />
          {/* no formula to reset to; this only keeps the column lined up with the rows that have the button */}
          <span className="qty-reset" style={{ visibility: 'hidden' }} aria-hidden>
            ↺
          </span>
        </>
      )
    }
    const id = line.component_line_id!
    return (
      <>
        <QtyInput
          value={line.qty_final}
          label={`Quantity of ${line.material_name}`}
          edited={row.overridden}
          onChange={(qty) => setOverrides((prev) => ({ ...prev, [id]: qty }))}
          onClear={() => clearOverride(id)}
        />
        <button
          type="button"
          className="qty-reset"
          style={{ visibility: row.overridden ? 'visible' : 'hidden' }}
          title={`Reset to formula: ${line.qty_formula ?? ''} = ${line.qty_auto ?? ''}`}
          aria-label={`Reset ${line.material_name} to formula`}
          onClick={() => clearOverride(id)}
        >
          ↺
        </button>
      </>
    )
  }

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
            <Text size="sm" fw={700} className="nowrap">
              {bom ? `PKR ${fmtPkr(bom.grand_total_pkr)}` : '—'}
            </Text>
            {bom && (
              <Text size="xs" c="dimmed" className="nowrap" visibleFrom="sm">
                Material {fmtUsd(bom.material_cost_usd)} · Production {fmtUsd(bom.production_cost_usd)}
              </Text>
            )}
            {updating && templateId !== null && <Loader size={14} aria-label="Updating" />}
          </Group>
          <Group gap={6} wrap="nowrap">
            {unpriced > 0 && (
              <Badge size="sm" color="red" variant="light" tt="none">
                {unpriced} no rate
              </Badge>
            )}
            {mismatched > 0 && (
              <Badge size="sm" color="orange" variant="light" tt="none">
                {mismatched} unit mismatch
              </Badge>
            )}
            {stale > 0 && (
              <Badge size="sm" color="orange" variant="light" tt="none">
                {stale} stale
              </Badge>
            )}
            <Button size="xs" disabled={!canSave} loading={save.isPending} onClick={() => save.mutate()}>
              Save BOM
            </Button>
          </Group>
        </Paper>

        {save.isError && (
          <Alert color="red" title="Couldn’t save this BOM" mt={6} mb={6}>
            <Text size="sm">{errorMessage(save.error)}</Text>
          </Alert>
        )}
        {bom && blockers.length > 0 && (
          <Alert color="red" p="xs" mt={6} mb={6} title={<Text size="xs" fw={600}>Can’t save yet</Text>}>
            <List size="xs">
              {blockers.map((reason) => (
                <List.Item key={reason}>{reason}</List.Item>
              ))}
            </List>
          </Alert>
        )}

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
          <>
            <BomLinesTable
              rows={rows}
              stickyOffset={BAR_HEIGHT}
              renderQty={renderQty}
              renderCostHead={(row) =>
                row.extraKey ? (
                  <Select
                    size="xs"
                    className="compact-select"
                    aria-label={`Cost head of ${row.line.material_name}`}
                    data={costHeads}
                    value={extras.find((e) => e.key === row.extraKey)?.cost_tag ?? DEFAULT_EXTRA_HEAD}
                    allowDeselect={false}
                    onChange={(value) => updateExtra(row.extraKey!, { cost_tag: value })}
                  />
                ) : (
                  row.line.cost_head
                )
              }
              renderActions={(row) =>
                row.extraKey && (
                  <button
                    type="button"
                    className="line-remove"
                    aria-label={`Remove ${row.line.material_name}`}
                    title="Remove this line"
                    onClick={() => setExtras((prev) => prev.filter((e) => e.key !== row.extraKey))}
                  >
                    ×
                  </button>
                )
              }
              footer={
                <Table.Tr>
                  <Table.Td colSpan={10}>
                    <AddMaterial onAdd={addExtra} />
                  </Table.Td>
                </Table.Tr>
              }
            />
            <div className="bom-below">
              <TotalsPanel
                bom={bom}
                miscInput={
                  <NumberInput
                    size="xs"
                    w={64}
                    aria-label="Misc percent"
                    className="compact-number"
                    hideControls
                    allowNegative={false}
                    value={miscInput ?? bom.misc_pct}
                    placeholder={String(bom.misc_pct)}
                    onChange={setMiscInput}
                  />
                }
              />
              <Paper withBorder p="xs">
                <Stack gap={6}>
                  <TextInput size="xs" label="Box dimension" value={boxDimension} onChange={(e) => setBoxDimension(e.currentTarget.value)} />
                  <NumberInput size="xs" label="Est. shipment (USD)" hideControls allowNegative={false} value={shipmentUsd} onChange={setShipmentUsd} />
                </Stack>
              </Paper>
            </div>
          </>
        )}
      </section>
    </div>
  )
}
