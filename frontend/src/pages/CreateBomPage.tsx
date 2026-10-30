import { Alert, Anchor, Button, Loader, NumberInput, Select, Text, TextInput, Title } from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useRef, useState } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import type { Bom, CostHead, MaterialSearchResult, Order, SignType, Template } from '../api/types'
import { useAuth } from '../auth/AuthProvider'
import { AddMaterial } from '../components/AddMaterial'
import { BomLinesTable } from '../components/BomLinesTable'
import { OrderAttachments } from '../components/OrderAttachments'
import { PageError, PageLoader } from '../components/PageState'
import { ParameterForm } from '../components/ParameterForm'
import { QtyInput } from '../components/QtyInput'
import { TemplatePicker } from '../components/TemplatePicker'
import { TotalsPanel } from '../components/TotalsPanel'
import { PageHeader, RateTag, Section, StatusPill } from '../components/ui'
import { type BomDraft, buildRequest, buildRows, type DraftExtra, type LineRow, missingRequired, type ParamValue, saveChecklist } from '../lib/bom'
import { fmtDate, fmtNum, fmtSize } from '../lib/format'
import { orderStatus } from '../lib/orders'

const PREVIEW_DEBOUNCE_MS = 300
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
  const order = useQuery({ queryKey: ['order', orderId], queryFn: ({ signal }) => api<Order>(`/orders/${orderId}`, { signal }) })
  const signTypes = useQuery({ queryKey: ['sign-types'], queryFn: ({ signal }) => api<SignType[]>('/sign-types', { signal }) })

  const [pickedSignTypeId, setPickedSignTypeId] = useState<number | null | undefined>(undefined)
  const [pickedTemplateId, setPickedTemplateId] = useState<number | null>(null)
  const [changingTemplate, setChangingTemplate] = useState(false)
  const [params, setParams] = useState<Record<string, ParamValue>>({})
  const [overrides, setOverrides] = useState<Record<number, number>>({})
  const [extras, setExtras] = useState<DraftExtra[]>([])
  const [miscInput, setMiscInput] = useState<string | number | undefined>(undefined)
  const [boxDimension, setBoxDimension] = useState('')
  const [shipmentUsd, setShipmentUsd] = useState<string | number>('')
  const nextExtraKey = useRef(1)

  const publishedId = signTypes.data?.find((s) => s.id === order.data?.sign_type_id)?.published_template_id ?? null
  // A picked template wins over the published one, so "Change template" works even when one is published.
  const templateId = pickedTemplateId ?? publishedId
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

  const headList = useQuery({ queryKey: ['cost-heads'], queryFn: ({ signal }) => api<CostHead[]>('/cost-heads', { signal }), staleTime: 5 * 60_000 })
  // A material's tag can be an alias rather than a head's name, and the picker must be able to show it.
  const costHeads = useMemo(
    () => [...new Set([...(headList.data ?? []).map((h) => h.name), DEFAULT_EXTRA_HEAD, ...extras.flatMap((e) => (e.cost_tag ? [e.cost_tag] : []))])],
    [headList.data, extras],
  )

  const save = useMutation({
    mutationFn: () =>
      api<Bom>('/boms', {
        json: { ...buildRequest(draft!), box_dimension: boxDimension.trim() || null, est_shipment_cost_usd: shipmentUsd === '' ? null : Number(shipmentUsd) },
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
    if (id !== null) setChangingTemplate(false)
  }
  function clearOverride(id: number) {
    setOverrides((prev) => {
      const { [id]: _removed, ...rest } = prev
      return rest
    })
  }
  function addExtra(material: MaterialSearchResult) {
    const key = String(nextExtraKey.current++)
    setExtras((prev) => [...prev, { key, material_id: material.id, name: material.name, qty: 1, cost_tag: material.cost_tag ?? DEFAULT_EXTRA_HEAD, uom: material.uom }])
  }
  function updateExtra(key: string, change: Partial<DraftExtra>) {
    setExtras((prev) => prev.map((e) => (e.key === key ? { ...e, ...change } : e)))
  }

  if (order.isPending || signTypes.isPending) return <PageLoader />
  if (order.isError || signTypes.isError) return <PageError title="Couldn’t load this order" error={order.error ?? signTypes.error} />
  const o = order.data

  const updating = draft !== debounced || preview.isFetching
  const lines = bom?.lines ?? []
  const missing = template.data ? missingRequired(template.data.parameters, values) : []
  const checklist = saveChecklist({ missing, inputErrors: bom?.input_errors ?? {}, lines })
  // Never save a figure nobody has seen: wait until the preview matches what's on screen.
  const canSave = !!bom && !updating && !preview.isError && !checklist.blocked && !save.isPending
  const requiredCount = template.data?.parameters.filter((p) => p.required).length ?? 0
  const st = orderStatus(o)
  // With nothing published the choice of a draft must stay visible and changeable; otherwise it's behind "Change template".
  const showPicker = templateId === null || changingTemplate || publishedId === null

  const renderQty = (row: LineRow) => {
    const { line, extraKey } = row
    if (extraKey) {
      const extra = extras.find((e) => e.key === extraKey)
      return (
        <>
          <QtyInput value={extra?.qty ?? line.qty_final} label={`Quantity of ${line.material_name}`} onChange={(qty) => updateExtra(extraKey, { qty })} onClear={() => updateExtra(extraKey, { qty: 0 })} />
          <span className="qty-reset" style={{ visibility: 'hidden' }} aria-hidden>
            ↺
          </span>
        </>
      )
    }
    const id = line.component_line_id!
    return (
      <>
        <QtyInput value={line.qty_final} label={`Quantity of ${line.material_name}`} edited={row.overridden} onChange={(qty) => setOverrides((prev) => ({ ...prev, [id]: qty }))} onClear={() => clearOverride(id)} />
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
    <div data-testid="create-bom" style={{ display: 'contents' }}>
      <PageHeader
        crumbs={[{ label: 'Orders', to: '/' }, { label: o.code }]}
        title={o.code}
        pills={
          <>
            <StatusPill tone={st.tone}>
              {st.word}
              {o.dispatch_by && st.word !== 'BOM saved' ? ` · ${fmtDate(o.dispatch_by)}` : ''}
            </StatusPill>
            {o.status && <StatusPill tone="neutral">{o.status}</StatusPill>}
          </>
        }
        description={[o.sign_type_name ?? o.sign_type_raw, [o.account_name, o.country].filter(Boolean).join(', '), o.width_in != null && o.height_in != null ? `${fmtSize(o.width_in, o.height_in)} in` : null, o.finish, o.led_color, o.usage].filter(Boolean).join(' · ')}
        actions={
          <>
            {template.data && (
              <span className="caption">
                Template: <strong>{template.data.sign_type_name} v{template.data.version}</strong> ({template.data.status})
              </span>
            )}
            {templateId !== null && (
              <Button variant="default" onClick={() => setChangingTemplate((v) => !v)}>
                {changingTemplate ? 'Keep template' : 'Change template'}
              </Button>
            )}
          </>
        }
      />

      {o.bom_count > 0 && (
        <Alert color="gray" p="sm">
          <Text size="sm">
            This order already has {o.bom_count} saved version{o.bom_count === 1 ? '' : 's'}.{' '}
            <Anchor component={Link} to={`/orders/${orderId}`} size="sm">
              See them
            </Anchor>
            . Saving here adds a new one.
          </Text>
        </Alert>
      )}

      {showPicker && (
        <TemplatePicker
          order={o}
          signTypes={signTypes.data}
          signTypeId={signTypeId}
          templateId={pickedTemplateId}
          onSignTypeChange={(id) => {
            setPickedSignTypeId(id)
            chooseTemplate(null)
          }}
          onTemplateChange={chooseTemplate}
        />
      )}
      {template.isError && (
        <Alert color="red" p="xs">
          <Text size="xs">{errorMessage(template.error)}</Text>
        </Alert>
      )}

      <div className="detail">
        <div className="detail-main">
          {template.data && (
            <Section id="inputs" title="Inputs" meta={missing.length ? <span style={{ color: 'var(--pending)', fontWeight: 700 }}>{missing.length} of {requiredCount} still empty</span> : requiredCount ? 'All filled in' : undefined}>
              <ParameterForm
                parameters={template.data.parameters}
                values={values}
                entered={params}
                errors={bom?.input_errors ?? {}}
                missing={missing.map((p) => p.param_name)}
                onChange={(name, value) => setParams((prev) => ({ ...prev, [name]: value }))}
              />
              {o.width_in != null && o.height_in != null && (
                <p className="caption" style={{ margin: '12px 0 0' }}>
                  Width {fmtNum(o.width_in, 3)} in, height {fmtNum(o.height_in, 3)} in and area {fmtNum((Number(o.width_in) * Number(o.height_in)) / 144, 2)} ft² come from the order and are available to formulas.
                </p>
              )}
            </Section>
          )}

          {templateId === null ? (
            <Section>
              <Text c="var(--slate)" size="sm">
                Choose a template to see the lines.
              </Text>
            </Section>
          ) : preview.isError ? (
            <Alert color="red" title="Couldn’t calculate this BOM">
              <Text size="sm" mb="xs">
                {errorMessage(preview.error)}
              </Text>
              <Button size="xs" variant="default" onClick={() => preview.refetch()}>
                Try again
              </Button>
            </Alert>
          ) : !bom ? (
            <PageLoader />
          ) : (
            <BomLinesTable
              rows={rows}
              meta={updating ? 'updating…' : undefined}
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
                  <button type="button" className="line-remove" aria-label={`Remove ${row.line.material_name}`} title="Remove this line" onClick={() => setExtras((prev) => prev.filter((e) => e.key !== row.extraKey))}>
                    ×
                  </button>
                )
              }
              footer={<AddMaterial onAdd={addExtra} />}
            />
          )}

          <section className="card card-body order-context" aria-labelledby="order-notes-h">
            <div style={{ minWidth: 0 }}>
              <Title order={2} id="order-notes-h">
                Order notes
              </Title>
              <p className="fact-notes" style={{ margin: '8px 0 0' }}>
                {o.special_notes ?? <span className="caption">No notes on this order.</span>}
              </p>
            </div>
            <OrderAttachments order={o} />
          </section>
        </div>

        <aside className="rail" data-testid="bom-bar" aria-label="Totals and checklist">
          {bom ? (
            <TotalsPanel bom={bom} miscInput={<NumberInput size="xs" w={64} aria-label="Misc percent" className="compact-number" hideControls allowNegative={false} value={miscInput ?? bom.misc_pct} placeholder={String(bom.misc_pct)} onChange={setMiscInput} />}>
              <div className="rule-top" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <TextInput label="Box dimension" placeholder="e.g. 24 × 16 × 6 in" value={boxDimension} onChange={(e) => setBoxDimension(e.currentTarget.value)} />
                <NumberInput label="Est. shipment (USD)" placeholder="0.00" hideControls allowNegative={false} value={shipmentUsd} onChange={setShipmentUsd} />
              </div>
            </TotalsPanel>
          ) : (
            <section className="card card-body totals" data-testid="totals">
              <span className="caption body-strong">Grand total (PKR)</span>
              <span className="hero-value">—</span>
            </section>
          )}
          <section className="card card-body" data-testid="checklist" aria-labelledby="ready-h">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
              <Title order={2} id="ready-h" style={{ fontSize: 14, lineHeight: '20px' }}>
                Before you save
              </Title>
              {bom && checklist.blocked && (
                <span className="caption" style={{ color: 'var(--pending)', fontWeight: 700 }}>
                  Can’t save yet
                </span>
              )}
              {updating && templateId !== null && <Loader size={14} aria-label="Updating" />}
            </div>
            {bom ? (
              <ul className="checklist" style={{ marginTop: 10 }}>
                {checklist.items.map((item) => (
                  <li key={item.text}>
                    <RateTag tone={item.tag === 'OK' ? 'done' : 'pending'}>{item.tag}</RateTag>
                    <span>
                      {item.params?.length ? (
                        <>
                          Fill in{' '}
                          {item.params.map((name, i) => {
                            const label = template.data?.parameters.find((p) => p.param_name === name)?.label ?? name
                            return (
                              <span key={name}>
                                {i > 0 && (i === item.params!.length - 1 ? ' and ' : ', ')}
                                <a href={`#param-${name}`} onClick={(e) => { e.preventDefault(); document.getElementById(`param-${name}`)?.focus() }}>
                                  {label}
                                </a>
                              </span>
                            )
                          })}
                          {item.tag === 'To do' && item.text.startsWith('Fix') ? `: ${item.text.slice(4)}` : '.'}
                        </>
                      ) : (
                        item.text
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="caption" style={{ margin: '8px 0 0' }}>
                {templateId === null ? 'Choose a template first.' : 'Calculating…'}
              </p>
            )}
            {save.isError && (
              <Text size="xs" c="var(--missing)" mt="sm" role="alert">
                {errorMessage(save.error)}
              </Text>
            )}
            <Button fullWidth mt="md" disabled={!canSave} loading={save.isPending} onClick={() => save.mutate()}>
              Save BOM
            </Button>
            <span className="caption" style={{ display: 'block', marginTop: 8 }}>
              Saving writes BOM Price, production cost and BOM Done back to Airtable.
            </span>
          </section>
        </aside>
      </div>
    </div>
  )
}
