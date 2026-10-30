import { Alert, Button, Select, Text, Title } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { Bom, BomDiff, Order, Template } from '../api/types'
import { useAuth } from '../auth/AuthProvider'
import { BomLinesTable } from '../components/BomLinesTable'
import { PageError, PageLoader } from '../components/PageState'
import { RateChangesBanner, useRateChanges } from '../components/RateChangesBanner'
import { TotalsPanel } from '../components/TotalsPanel'
import { PageHeader, RateTag, Section, StatusPill } from '../components/ui'
import { frozenRows, isImported } from '../lib/bom'
import { fmtDate, fmtNum, fmtPkr, fmtSize, fmtUsd } from '../lib/format'

interface WriteBack {
  id: number
  bom_id: number
  status: string
  error: string | null
  sent_at: string | null
  created_at: string
}

export function BomDetailPage() {
  const bomId = Number(useParams().bomId)
  return <BomDetail key={bomId} bomId={bomId} />
}

/** A saved BOM, exactly as it was frozen. Nothing here recalculates unless asked. */
function BomDetail({ bomId }: { bomId: number }) {
  const location = useLocation()
  const navigate = useNavigate()
  const { canWrite } = useAuth()
  const [justSaved] = useState(() => !!(location.state as { justSaved?: boolean } | null)?.justSaved)
  const [compareWith, setCompareWith] = useState<number | null>(null)

  // The browser keeps history state across a refresh, which would announce the save again.
  useEffect(() => {
    if (location.state) navigate(location.pathname, { replace: true, state: null })
  }, [location.state, location.pathname, navigate])

  const bom = useQuery({
    queryKey: ['bom', bomId],
    queryFn: ({ signal }) => api<Bom>(`/boms/${bomId}`, { signal }),
    staleTime: Infinity, // a saved BOM never changes
  })
  const orderId = bom.data?.order_id
  const order = useQuery({ queryKey: ['order', orderId], queryFn: ({ signal }) => api<Order>(`/orders/${orderId}`, { signal }), enabled: orderId !== undefined })
  const versions = useQuery({ queryKey: ['order-boms', orderId], queryFn: ({ signal }) => api<Bom[]>(`/orders/${orderId}/boms`, { signal }), enabled: orderId !== undefined })
  const templateId = bom.data?.template_id
  const template = useQuery({ queryKey: ['template', templateId], queryFn: ({ signal }) => api<Template>(`/templates/${templateId}`, { signal }), enabled: templateId != null })
  const writeBacks = useQuery({ queryKey: ['write-backs'], queryFn: ({ signal }) => api<WriteBack[]>('/sync/write-backs', { signal }), staleTime: 60_000 })
  const diff = useQuery({
    queryKey: ['bom-diff', compareWith, bomId],
    queryFn: ({ signal }) => api<BomDiff>(`/boms/${compareWith}/diff/${bomId}`, { signal }),
    enabled: compareWith !== null,
  })

  const rows = useMemo(() => (bom.data ? frozenRows(bom.data) : []), [bom.data])
  const changes = useRateChanges(bom.data ?? ({ id: null, status: 'imported' } as unknown as Bom))
  const changedNames = useMemo(() => new Set((changes.data?.changed_lines ?? []).map((c) => c.line)), [changes.data])

  if (bom.isPending) return <PageLoader />
  if (bom.isError) return <PageError title="Couldn’t load this BOM" error={bom.error} />
  const saved = bom.data
  const o = order.data
  const list = [...(versions.data ?? [])].sort((a, b) => b.version - a.version)
  const previous = list.find((v) => v.version < saved.version)
  const lastWriteBack = (writeBacks.data ?? []).filter((w) => w.bom_id === saved.id).sort((a, b) => (b.sent_at ?? b.created_at).localeCompare(a.sent_at ?? a.created_at))[0]
  const written = saved.status === 'written_back' || lastWriteBack?.status === 'sent'

  // Labels and units come from the template; a saved BOM still reads fine without them.
  const paramInfo = new Map(template.data?.parameters.map((p) => [p.param_name, p]))
  const parameters = Object.entries(saved.parameters)

  const statusPill = isImported(saved) ? (
    <StatusPill tone="neutral">Imported from the sheet</StatusPill>
  ) : written ? (
    <StatusPill tone="info">Written back to Airtable</StatusPill>
  ) : (
    <StatusPill tone="done">BOM saved</StatusPill>
  )
  const description = [
    template.data ? `${template.data.sign_type_name} v${template.data.version}` : isImported(saved) ? 'From the October sheet' : null,
    isImported(saved) ? null : `saved ${fmtDate(saved.saved_at)}`,
    saved.notes?.match(/recalculated from v\d+/)?.[0] ?? null,
    o ? `${fmtSize(o.width_in, o.height_in)} in · ${[o.finish, o.led_color].filter(Boolean).join(' · ')}` : null,
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <>
      <PageHeader
        crumbs={[{ label: 'Orders', to: '/' }, { label: saved.order_code ?? `Order ${saved.order_id}`, to: `/orders/${saved.order_id}` }, { label: `BOM v${saved.version}` }]}
        title={`${saved.order_code ?? ''} · BOM v${saved.version}`}
        pills={statusPill}
        description={description}
        actions={
          <>
            {list.length > 1 && (
              <Select
                aria-label="Version"
                w={260}
                data={list.map((v) => ({ value: String(v.id), label: `v${v.version} · ${isImported(v) ? 'sheet' : fmtDate(v.saved_at)} · PKR ${fmtPkr(v.grand_total_pkr)}${v.id === saved.id ? ' (current)' : ''}` }))}
                value={String(saved.id)}
                allowDeselect={false}
                onChange={(v) => v && Number(v) !== saved.id && navigate(`/boms/${v}`)}
              />
            )}
            {previous && (
              <Button variant="default" onClick={() => setCompareWith(compareWith === previous.id ? null : previous.id)} aria-pressed={compareWith === previous.id}>
                {compareWith === previous.id ? 'Hide comparison' : `Compare with v${previous.version}`}
              </Button>
            )}
            {canWrite && (
              <Button component={Link} to={`/orders/${saved.order_id}/bom`}>
                New version
              </Button>
            )}
          </>
        }
      />

      {justSaved && (
        <Alert color="green" p="sm">
          <Text size="sm">Saved as version {saved.version}.</Text>
        </Alert>
      )}

      <RateChangesBanner bom={saved} changes={changes.data} />

      {compareWith !== null && previous && (
        <Section id="compare" title={`Changes from v${previous.version} to v${saved.version}`}>
          {diff.isPending ? <PageLoader /> : diff.isError ? <PageError title="Couldn’t compare" error={diff.error} /> : <CompareView diff={diff.data} />}
        </Section>
      )}

      <div className="detail">
        <div className="detail-main" data-testid="bom-main">
          <BomLinesTable rows={rows} meta="Rates frozen at save" changed={changedNames} />
          {parameters.length > 0 && (
            <Section id="inputs-used" title="Inputs used">
              <div className="inputs-used">
                {parameters.map(([name, value]) => {
                  const info = paramInfo.get(name)
                  return (
                    <div key={name}>
                      <div className="caption">{info?.label ?? name.replace(/_/g, ' ')}</div>
                      <strong>{value === null || value === '' ? '—' : `${value}${info?.uom ? ` ${info.uom}` : ''}`}</strong>
                    </div>
                  )
                })}
              </div>
            </Section>
          )}
        </div>

        <aside className="rail" data-testid="bom-bar" aria-label="Totals">
          <TotalsPanel bom={saved} />
          <section className="card card-body" aria-labelledby="at-h" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <Title order={2} id="at-h" style={{ fontSize: 14, lineHeight: '20px' }}>
              Airtable
            </Title>
            <dl className="kv">
              <dt>BOM Price</dt>
              <dd>{fmtUsd(saved.material_cost_usd)}</dd>
              <dt>Production cost</dt>
              <dd>{fmtUsd(saved.production_cost_usd)}</dd>
              <dt>Box</dt>
              <dd>{saved.box_dimension ?? '—'}</dd>
              <dt>Est. shipment</dt>
              <dd>{fmtUsd(saved.est_shipment_cost_usd)}</dd>
              <dt>Misc</dt>
              <dd>{fmtNum(saved.misc_pct)} %</dd>
            </dl>
            {isImported(saved) ? (
              <span className="caption">Historical record; nothing to write back.</span>
            ) : written ? (
              <span className="caption" style={{ color: 'var(--done)', fontWeight: 700 }}>
                Written back{lastWriteBack?.sent_at ? ` ${fmtDate(lastWriteBack.sent_at)}` : ''}
              </span>
            ) : lastWriteBack?.status === 'failed' ? (
              <span className="caption" style={{ color: 'var(--missing)', fontWeight: 700 }}>
                Write-back failed{lastWriteBack.error ? `: ${lastWriteBack.error}` : ''}
              </span>
            ) : (
              <RateTag tone="neutral">Not written back</RateTag>
            )}
            {saved.notes && !/^\s*\[recalculated/.test(saved.notes) && <span className="caption">{saved.notes}</span>}
          </section>
        </aside>
      </div>
    </>
  )
}

function CompareView({ diff }: { diff: BomDiff }) {
  const [before, after] = diff.grand_total
  const label = (key: string) => key.replace('|', ' · ').replace(/ · $/, '')
  const total = diff.changed.length + diff.added.length + diff.removed.length
  return (
    <>
      <p style={{ margin: '0 0 8px' }}>
        PKR {fmtPkr(before)} → <strong>PKR {fmtPkr(after)}</strong> ({diff.delta_pkr > 0 ? '+' : ''}
        {fmtPkr(diff.delta_pkr)}){diff.template_changed ? ' · different template versions' : ''}
      </p>
      {total === 0 ? (
        <Text size="sm" c="var(--slate)">
          No line differs.
        </Text>
      ) : (
        <ul className="checklist">
          {diff.changed.map((c) => (
            <li key={c.line}>
              <RateTag tone="pending">changed</RateTag>
              <span>
                {label(c.line)}: qty {fmtNum(c.qty[0], 3)} → {fmtNum(c.qty[1], 3)}, rate {fmtNum(c.rate[0])} → {fmtNum(c.rate[1])}, total {fmtPkr(c.total[0])} → {fmtPkr(c.total[1])}
              </span>
            </li>
          ))}
          {diff.added.map((c) => (
            <li key={`a-${c.line}`}>
              <RateTag tone="done">added</RateTag>
              <span>
                {label(c.line)}: {fmtNum(c.qty, 3)} × {fmtNum(c.rate)} = {fmtPkr(c.total)}
              </span>
            </li>
          ))}
          {diff.removed.map((c) => (
            <li key={`r-${c.line}`}>
              <RateTag tone="missing">removed</RateTag>
              <span>
                {label(c.line)}: was {fmtPkr(c.total)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}
