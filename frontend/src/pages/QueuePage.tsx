import { Alert, Anchor, Button, Center, Loader, Select, Text, TextInput } from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import type { DashboardSummary, Order, SignType, UnmappedName } from '../api/types'
import { useAuth } from '../auth/AuthProvider'
import { OrderThumb } from '../components/OrderThumb'
import { HeroNumber, PageHeader, StatusPill } from '../components/ui'
import { agoWords, dispatchWords, fmtDate, fmtPkr, fmtSize, isOverdue } from '../lib/format'
import { type OrderScope, ordersQuery, orderStatus, templateProblem } from '../lib/orders'

interface SyncStatus {
  configured: boolean
  last_synced_at: string | null
}

export function QueuePage() {
  const navigate = useNavigate()
  const { canWrite } = useAuth()
  const [params, setParams] = useSearchParams()
  const scope: OrderScope = params.get('show') === 'all' ? 'all' : 'needs_bom'
  const search = params.get('q') ?? ''
  const bucket = params.get('week') ?? ''
  const [q] = useDebouncedValue(search.trim(), 250)
  const setParam = (key: string, value: string) =>
    setParams(
      (p) => {
        if (value) p.set(key, value)
        else p.delete(key)
        return p
      },
      { replace: true },
    )

  const orders = useQuery({ ...ordersQuery(scope, q), placeholderData: keepPreviousData })
  const needsBom = useQuery(ordersQuery('needs_bom'))
  const signTypes = useQuery({ queryKey: ['sign-types'], queryFn: ({ signal }) => api<SignType[]>('/sign-types', { signal }) })
  const unmapped = useQuery({ queryKey: ['unmapped'], queryFn: ({ signal }) => api<UnmappedName[]>('/sign-types/unmapped', { signal }) })
  const summary = useQuery({ queryKey: ['dashboard'], queryFn: ({ signal }) => api<DashboardSummary>('/dashboard/summary', { signal }) })
  const sync = useQuery({ queryKey: ['sync-status'], queryFn: ({ signal }) => api<SyncStatus>('/sync/airtable/status', { signal }), staleTime: 60_000 })

  const rows = useMemo(() => (orders.data ?? []).filter((o) => !bucket || o.weekly_bucket === bucket), [orders.data, bucket])
  const buckets = Object.keys(summary.data?.weekly_buckets ?? {})
    .filter((k) => k !== '(none)')
    .sort()

  // Hero numbers, all from the same lists the table shows.
  const waiting = needsBom.data ?? []
  const overdue = waiting.filter((o) => isOverdue(o.dispatch_by)).length
  const noTemplate = waiting.filter((o) => templateProblem(o, signTypes.data) !== null).length
  const withBom = summary.data?.orders_with_bom

  // Writers go straight to Create BOM; an order that already has a BOM opens on its versions first.
  const orderPath = (o: Order) => (canWrite && o.bom_count === 0 ? `/orders/${o.id}/bom` : `/orders/${o.id}`)
  const synced = agoWords(sync.data?.last_synced_at)

  return (
    <>
      <PageHeader
        title="Orders"
        description="Orders from Airtable, soonest dispatch first. Cost the ones that still need a BOM."
        actions={
          <>
            <span className="caption">{sync.data ? (sync.data.configured ? (synced ? `Synced ${synced}` : 'Not synced yet') : 'Airtable not connected') : ''}</span>
            <Button variant="default" component={Link} to="/sync">
              Pull from Airtable
            </Button>
            <Button variant="default" component={Link} to="/sync">
              Upload CSV
            </Button>
          </>
        }
      />

      <section aria-label="Summary" className="heroes">
        <HeroNumber
          value={needsBom.data ? waiting.length : '…'}
          tone={waiting.length ? 'pending' : 'done'}
          sentence={`order${waiting.length === 1 ? '' : 's'} need${waiting.length === 1 ? 's' : ''} a BOM`}
          caption={overdue ? `${overdue} past ${overdue === 1 ? 'its' : 'their'} dispatch date` : 'none overdue'}
          captionTone={overdue ? 'missing' : undefined}
          to="/?show=needs_bom"
          testId="hero-needs-bom"
        />
        <HeroNumber
          value={needsBom.data && signTypes.data ? noTemplate : '…'}
          tone={noTemplate ? 'missing' : 'done'}
          sentence={`waiting order${noTemplate === 1 ? '' : 's'} ${noTemplate === 1 ? 'has' : 'have'} a sign type with no template`}
          caption={unmapped.data ? `${unmapped.data.length} Airtable name${unmapped.data.length === 1 ? '' : 's'} to map` : undefined}
          to="/templates"
          testId="hero-no-template"
        />
        <HeroNumber
          value={withBom ?? '…'}
          sentence={`order${withBom === 1 ? '' : 's'} ${withBom === 1 ? 'has' : 'have'} a BOM`}
          caption={summary.data ? `of ${summary.data.orders} in Airtable this month` : undefined}
          to="/?show=all"
          testId="hero-with-bom"
        />
      </section>

      <div className="filters">
        <TextInput
          placeholder="Search code, account or sign type"
          aria-label="Search orders"
          w={320}
          maw="100%"
          value={search}
          onChange={(e) => setParam('q', e.currentTarget.value)}
        />
        <div role="group" aria-label="Show" className="segmented">
          <button type="button" aria-pressed={scope === 'needs_bom'} onClick={() => setParam('show', '')}>
            Needs BOM{needsBom.data ? ` · ${waiting.length}` : ''}
          </button>
          <button type="button" aria-pressed={scope === 'all'} onClick={() => setParam('show', 'all')}>
            All{summary.data ? ` · ${summary.data.orders}` : ''}
          </button>
        </div>
        {buckets.length > 0 && (
          <Select aria-label="Week" w={200} placeholder="Any week" clearable data={buckets} value={bucket || null} onChange={(v) => setParam('week', v ?? '')} />
        )}
        {orders.isFetching && orders.data && <Loader size={14} />}
      </div>

      {orders.isError ? (
        <Alert color="red" title="Couldn’t load orders">
          <Text size="sm" mb="xs">
            {errorMessage(orders.error)}
          </Text>
          <Button size="xs" variant="default" onClick={() => orders.refetch()}>
            Try again
          </Button>
        </Alert>
      ) : orders.isPending ? (
        <Center p="xl">
          <Loader />
        </Center>
      ) : rows.length === 0 ? (
        <Center p="xl">
          <Text c="var(--slate)">{q ? `No orders match “${q}”.` : bucket ? `No orders in ${bucket}.` : 'No orders waiting for a BOM.'}</Text>
        </Center>
      ) : (
        <>
          <div className="card table-wrap only-desktop">
            <table className="tbl tbl-tall mantine-Table-table" data-testid="orders-table">
              <thead>
                <tr>
                  <th style={{ width: 120 }}>Status</th>
                  <th>Order</th>
                  <th>Sign type</th>
                  <th className="num">W × H (in)</th>
                  <th>Finish · LED</th>
                  <th>Dispatch by</th>
                  <th style={{ width: 150 }} aria-label="Action" />
                </tr>
              </thead>
              <tbody>
                {rows.map((o) => {
                  const st = orderStatus(o)
                  const problem = templateProblem(o, signTypes.data)
                  const late = isOverdue(o.dispatch_by)
                  const due = st.word === 'Due today'
                  return (
                    <tr key={o.id} className="clickable" onClick={() => navigate(orderPath(o))}>
                      <td>
                        <StatusPill tone={st.tone}>{st.word}</StatusPill>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                          <OrderThumb orderId={o.id} images={o.images} size={32} />
                          <div style={{ minWidth: 0 }}>
                            <Link to={orderPath(o)} className="row-link" onClick={(e) => e.stopPropagation()}>
                              {o.code}
                            </Link>
                            <div className="caption">{[o.account_name, o.country].filter(Boolean).join(' · ') || '—'}</div>
                          </div>
                        </div>
                      </td>
                      <td>
                        {o.sign_type_name ?? o.sign_type_raw ?? '—'}
                        {problem ? (
                          <div className="caption" style={{ color: 'var(--pending)', fontWeight: 700 }}>
                            {problem}
                          </div>
                        ) : (
                          o.sign_type_raw && o.sign_type_raw !== o.sign_type_name && <div className="caption">Airtable: “{o.sign_type_raw}”</div>
                        )}
                      </td>
                      <td className="num">{fmtSize(o.width_in, o.height_in)}</td>
                      <td>{[o.finish, o.led_color].filter(Boolean).join(' · ') || '—'}</td>
                      <td>
                        <span style={late ? { color: 'var(--missing)', fontWeight: 700 } : due ? { color: 'var(--pending)', fontWeight: 700 } : undefined}>{fmtDate(o.dispatch_by)}</span>
                        <div className="caption">{o.status?.toLowerCase().includes('shipped') ? 'shipped' : dispatchWords(o.dispatch_by)}</div>
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        {o.bom_count > 0 ? (
                          <Button size="compact-md" variant="default" component={Link} to={`/orders/${o.id}`} onClick={(e) => e.stopPropagation()}>
                            v{o.bom_count}
                            {o.latest_bom_total_pkr != null ? ` · PKR ${fmtPkr(o.latest_bom_total_pkr)}` : ''}
                          </Button>
                        ) : canWrite ? (
                          <Button size="compact-md" component={Link} to={`/orders/${o.id}/bom`} onClick={(e) => e.stopPropagation()}>
                            Create BOM
                          </Button>
                        ) : (
                          <Anchor component={Link} to={`/orders/${o.id}`} size="sm" onClick={(e) => e.stopPropagation()}>
                            View
                          </Anchor>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          <div className="card order-cards only-phone" data-testid="orders-cards">
            {rows.map((o) => {
              const st = orderStatus(o)
              const problem = templateProblem(o, signTypes.data)
              const late = isOverdue(o.dispatch_by)
              return (
                <Link key={o.id} to={orderPath(o)} className="order-card">
                  <div className="order-card-top">
                    <StatusPill tone={st.tone}>{st.word}</StatusPill>
                    <strong>{o.code}</strong>
                    <span className="caption" style={{ marginLeft: 'auto', ...(late ? { color: 'var(--missing)', fontWeight: 700 } : {}) }}>
                      {o.bom_count > 0 ? `v${o.bom_count}` : fmtDate(o.dispatch_by)}
                    </span>
                  </div>
                  <div>
                    {o.sign_type_name ?? o.sign_type_raw ?? 'No sign type'}
                    {o.width_in != null && o.height_in != null ? ` · ${fmtSize(o.width_in, o.height_in)} in` : ''}
                  </div>
                  <div className="caption">{[o.account_name, o.finish, o.led_color].filter(Boolean).join(' · ')}</div>
                  {problem && (
                    <div className="caption" style={{ color: 'var(--pending)', fontWeight: 700 }}>
                      {problem}
                    </div>
                  )}
                </Link>
              )
            })}
          </div>

          <p className="caption" style={{ margin: 0 }}>
            Showing {rows.length} of {summary.data?.orders ?? '…'} orders · soonest dispatch first · imported October BOMs are marked “sheet” on the BOM page.
          </p>
        </>
      )}
    </>
  )
}
