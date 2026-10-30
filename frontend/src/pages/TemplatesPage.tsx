import { Alert, Button, Modal, Select, Stack, Text, TextInput } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import type { FlaggedTemplate, Order, SignType, Template, TemplateSummary, UnmappedName } from '../api/types'
import { useAuth } from '../auth/AuthProvider'
import { PageError, PageLoader } from '../components/PageState'
import { HeroNumber, PageHeader, StatusPill } from '../components/ui'
import { describeKinds } from '../lib/templates'

type Sort = 'orders' | 'attention' | 'name'
const TODO_SHOWN = 6
const UNMAPPED_SHOWN = 5

export function TemplatesPage() {
  const { canEditTemplates } = useAuth()
  const signTypes = useQuery({ queryKey: ['sign-types'], queryFn: ({ signal }) => api<SignType[]>('/sign-types', { signal }) })
  const flagged = useQuery({ queryKey: ['flagged'], queryFn: ({ signal }) => api<FlaggedTemplate[]>('/templates/flagged', { signal }) })
  const unmapped = useQuery({ queryKey: ['unmapped'], queryFn: ({ signal }) => api<UnmappedName[]>('/sign-types/unmapped', { signal }) })
  // One cached call: counting orders per sign type in the browser is cheaper than a new endpoint.
  const orders = useQuery({ queryKey: ['orders', { scope: 'all', q: '' }], queryFn: ({ signal }) => api<Order[]>('/orders', { query: { limit: 2000 }, signal }) })
  const withTemplates = (signTypes.data ?? []).filter((s) => s.template_count > 0)
  const versions = useQuery({
    queryKey: ['sign-type-versions', withTemplates.map((s) => s.id)],
    queryFn: async ({ signal }) => new Map(await Promise.all(withTemplates.map(async (s) => [s.id, await api<TemplateSummary[]>(`/sign-types/${s.id}/templates`, { signal })] as const))),
    enabled: signTypes.isSuccess,
  })
  const [newOpen, setNewOpen] = useState<{ name: string; mapFrom?: string } | null>(null)

  const orderCounts = useMemo(() => {
    const counts = new Map<number, number>()
    for (const o of orders.data ?? []) if (o.sign_type_id !== null) counts.set(o.sign_type_id, (counts.get(o.sign_type_id) ?? 0) + 1)
    return counts
  }, [orders.data])

  if (signTypes.isPending) return <PageLoader />
  if (signTypes.isError) return <PageError title="Couldn’t load sign types" error={signTypes.error} />

  const total = signTypes.data.length
  const withTemplate = withTemplates.length
  const published = signTypes.data.filter((s) => s.published_template_id).length
  const flaggedLines = (flagged.data ?? []).flatMap((t) => t.flagged)
  const kinds = describeKinds(flaggedLines.map((f) => f.problem))
  const unmappedOrders = (unmapped.data ?? []).reduce((n, u) => n + u.orders, 0)

  return (
    <>
      <PageHeader
        title="Templates"
        description="One template per sign type. Orders can only be costed against a published version."
        actions={canEditTemplates && <Button onClick={() => setNewOpen({ name: '' })}>New sign type</Button>}
      />

      <section aria-label="Summary" className="heroes">
        <HeroNumber
          value={`${published} of ${withTemplate}`}
          tone={published === withTemplate && withTemplate > 0 ? 'done' : 'missing'}
          sentence={`imported template${withTemplate === 1 ? ' is' : 's are'} published`}
          caption={versions.data ? `${[...versions.data.values()].filter((v) => v.some((t) => t.status === 'draft')).length} drafts in progress · ${total} sign types` : `${total} sign types`}
          to="#sign-types"
          testId="hero-published"
        />
        <HeroNumber
          value={flagged.data ? flaggedLines.length : '…'}
          tone={flaggedLines.length ? 'pending' : 'done'}
          sentence={`flagged line${flaggedLines.length === 1 ? '' : 's'} to resolve`}
          caption={flagged.data ? (kinds || 'nothing flagged') : undefined}
          to="#todo"
          testId="hero-flagged"
        />
        <HeroNumber
          value={unmapped.data ? unmapped.data.length : '…'}
          tone={unmapped.data?.length ? 'pending' : 'done'}
          sentence={`Airtable name${unmapped.data?.length === 1 ? ' maps' : 's map'} to no sign type`}
          caption={unmapped.data ? `${unmappedOrders} order${unmappedOrders === 1 ? '' : 's'} blocked until mapped` : undefined}
          to="#unmapped"
          testId="hero-unmapped"
        />
      </section>

      <div className="templates-grid">
        <SignTypesTable signTypes={signTypes.data} versions={versions.data} orderCounts={orderCounts} ordersLoaded={orders.isSuccess} />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20, minWidth: 0 }}>
          <TodoPanel flagged={flagged} signTypes={signTypes.data} orderCounts={orderCounts} />
          <UnmappedPanel unmapped={unmapped} signTypes={signTypes.data} onNewSignType={(name) => setNewOpen({ name, mapFrom: name })} />
        </div>
      </div>

      {newOpen && <NewSignTypeModal initial={newOpen} onClose={() => setNewOpen(null)} />}
    </>
  )
}

// ---------------------------------------------------------------- sign types

function SignTypesTable({ signTypes, versions, orderCounts, ordersLoaded }: { signTypes: SignType[]; versions: Map<number, TemplateSummary[]> | undefined; orderCounts: Map<number, number>; ordersLoaded: boolean }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { canEditTemplates } = useAuth()
  const [filter, setFilter] = useState('')
  const [sort, setSort] = useState<Sort>('orders')
  const [error, setError] = useState<string | null>(null)

  const openEditor = useMutation({
    mutationFn: async (s: SignType) => {
      const draft = versions?.get(s.id)?.find((t) => t.status === 'draft')
      if (draft) return draft.id
      return (await api<Template>('/templates/drafts', { json: { sign_type_id: s.id } })).id
    },
    onSuccess: (id) => {
      queryClient.invalidateQueries({ queryKey: ['sign-type-versions'] })
      queryClient.invalidateQueries({ queryKey: ['sign-types'] })
      navigate(`/templates/${id}`)
    },
    onError: (e) => setError(errorMessage(e)),
  })

  const q = filter.trim().toLowerCase()
  const info = (s: SignType) => {
    const list = versions?.get(s.id) ?? []
    return { published: list.find((t) => t.status === 'published'), draft: list.find((t) => t.status === 'draft'), orders: orderCounts.get(s.id) ?? 0 }
  }
  const rows = signTypes
    .filter((s) => !q || s.name.toLowerCase().includes(q) || s.aliases.some((a) => a.toLowerCase().includes(q)))
    .sort((a, b) => {
      const ia = info(a)
      const ib = info(b)
      if (sort === 'name') return a.name.localeCompare(b.name)
      if (sort === 'attention') {
        const na = (ia.published ? 0 : 2) + (ia.draft?.flagged_lines ? 1 : 0)
        const nb = (ib.published ? 0 : 2) + (ib.draft?.flagged_lines ? 1 : 0)
        if (na !== nb) return nb - na
      }
      return ib.orders - ia.orders || a.name.localeCompare(b.name)
    })
  const noOrders = signTypes.filter((s) => !orderCounts.get(s.id)).length

  return (
    <section className="card" aria-labelledby="st-h" id="sign-types">
      <div className="card-head">
        <h2 id="st-h" className="mantine-Title-root" style={{ margin: 0, fontSize: 16, lineHeight: '24px', fontWeight: 700, fontFamily: 'inherit' }}>
          Sign types
        </h2>
        <div className="card-head-right">
          <TextInput w={240} placeholder="Filter by name or alias" aria-label="Filter sign types" value={filter} onChange={(e) => setFilter(e.currentTarget.value)} />
          <Select
            aria-label="Show"
            w={170}
            allowDeselect={false}
            data={[
              { value: 'orders', label: 'With orders first' },
              { value: 'attention', label: 'Needs attention' },
              { value: 'name', label: 'A–Z' },
            ]}
            value={sort}
            onChange={(v) => setSort((v as Sort) ?? 'orders')}
          />
        </div>
      </div>
      {error && (
        <Alert color="red" p="xs" m="sm" withCloseButton onClose={() => setError(null)}>
          <Text size="xs">{error}</Text>
        </Alert>
      )}
      <div className="table-wrap">
        <table className="tbl mantine-Table-table">
          <thead>
            <tr>
              <th>Sign type</th>
              <th>Published</th>
              <th>Draft</th>
              <th className="num">Orders</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => {
              const { published, draft, orders } = info(s)
              const meta = [s.code ? `code ${s.code}` : null, s.aliases.length ? `alias ${s.aliases.map((a) => `“${a}”`).join(', ')}` : null].filter(Boolean).join(' · ')
              return (
                <tr key={s.id} data-testid={`sign-type-${s.id}`}>
                  <td>
                    <Link to={`/sign-types/${s.id}`} className="row-link">
                      {s.name}
                    </Link>
                    {!s.active && <StatusPill tone="neutral"> inactive</StatusPill>}
                    {meta && (
                      <div className="caption" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 380 }} title={meta}>
                        {meta}
                      </div>
                    )}
                  </td>
                  <td>
                    {published ? (
                      <Link to={`/templates/${published.id}`} style={{ textDecoration: 'none' }}>
                        <StatusPill tone="done">
                          v{published.version} · {published.line_count} lines
                        </StatusPill>
                      </Link>
                    ) : s.template_count ? (
                      <StatusPill tone="missing">None</StatusPill>
                    ) : (
                      <StatusPill tone={orders ? 'missing' : 'neutral'}>No template</StatusPill>
                    )}
                  </td>
                  <td>
                    {draft ? (
                      <Link to={`/templates/${draft.id}`} className="row-link">
                        v{draft.version}
                        {draft.flagged_lines ? ` · ${draft.flagged_lines} flagged` : ''}
                      </Link>
                    ) : (
                      <span style={{ color: 'var(--slate)' }}>—</span>
                    )}
                  </td>
                  <td className="num" style={orders ? undefined : { color: 'var(--slate)' }}>
                    {ordersLoaded ? orders : '…'}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    {canEditTemplates ? (
                      <Button size="compact-md" variant={draft ? 'filled' : 'default'} loading={openEditor.isPending && openEditor.variables?.id === s.id} onClick={() => openEditor.mutate(s)}>
                        {draft ? 'Edit draft' : published ? 'New draft' : 'Create'}
                      </Button>
                    ) : (
                      published && (
                        <Button size="compact-md" variant="default" component={Link} to={`/templates/${published.id}`}>
                          View
                        </Button>
                      )
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <div className="card-foot caption">
        {rows.length} of {signTypes.length} sign types · sorted by {sort === 'orders' ? 'orders' : sort === 'attention' ? 'what needs attention' : 'name'}
        {ordersLoaded ? ` · ${noOrders} have no orders this month` : ''}
      </div>
    </section>
  )
}

function NewSignTypeModal({ initial, onClose }: { initial: { name: string; mapFrom?: string }; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [name, setName] = useState(initial.name)
  const [code, setCode] = useState('')
  const create = useMutation({
    // Created from an unmapped Airtable name, the name itself becomes the first alias so its orders map at once.
    mutationFn: () => api<SignType>('/sign-types', { json: { name: name.trim(), code: code.trim() || null, aliases: initial.mapFrom && initial.mapFrom !== name.trim() ? [initial.mapFrom] : [], active: true } }),
    onSuccess: () => {
      for (const key of ['sign-types', 'unmapped', 'orders', 'dashboard']) queryClient.invalidateQueries({ queryKey: [key] })
      onClose()
    },
  })
  return (
    <Modal opened onClose={onClose} title="New sign type" size="sm">
      <Stack gap="sm">
        <TextInput label="Name" required autoFocus value={name} onChange={(e) => setName(e.currentTarget.value)} />
        <TextInput label="Code" placeholder="e.g. 26" value={code} onChange={(e) => setCode(e.currentTarget.value)} />
        {initial.mapFrom && (
          <Text size="xs" c="var(--slate)">
            Orders typed as “{initial.mapFrom}” in Airtable will map to it.
          </Text>
        )}
        {create.isError && (
          <Text size="xs" c="var(--missing)">
            {errorMessage(create.error)}
          </Text>
        )}
        <Button disabled={!name.trim()} loading={create.isPending} onClick={() => create.mutate()}>
          Create
        </Button>
      </Stack>
    </Modal>
  )
}

// ---------------------------------------------------------------- to-do: flagged lines, most orders waiting first

function TodoPanel({ flagged, signTypes, orderCounts }: { flagged: ReturnType<typeof useQuery<FlaggedTemplate[]>>; signTypes: SignType[]; orderCounts: Map<number, number> }) {
  const [showAll, setShowAll] = useState(false)
  if (flagged.isError) return <PageError title="Couldn’t load the to-do list" error={flagged.error} />
  const byName = new Map(signTypes.map((s) => [s.name, s.id]))
  const items = (flagged.data ?? [])
    .map((t) => ({ ...t, orders: orderCounts.get(byName.get(t.sign_type) ?? -1) ?? 0 }))
    .sort((a, b) => b.orders - a.orders || b.flagged.length - a.flagged.length)
  const urgent = items.filter((t) => t.orders > 0)
  const quiet = items.filter((t) => t.orders === 0)
  const shown = showAll ? items : urgent.slice(0, TODO_SHOWN)
  const quietFlags = quiet.reduce((n, t) => n + t.flagged.length, 0)

  return (
    <section className="card" aria-labelledby="todo-h" id="todo" data-testid="todo-panel">
      <div className="card-head" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 2 }}>
        <h2 id="todo-h" style={{ margin: 0, fontSize: 16, lineHeight: '24px', fontWeight: 700 }}>
          Your to-do
        </h2>
        <span className="caption">Drafts with the most orders waiting on them first. Publishing clears a template’s flags.</span>
      </div>
      {!flagged.data ? (
        <div className="card-body caption">Loading…</div>
      ) : items.length === 0 ? (
        <div className="card-body">
          <Text size="sm">Nothing flagged.</Text>
        </div>
      ) : (
        <div>
          {shown.map((t) => (
            <Link key={t.template_id} to={`/templates/${t.template_id}`} className="todo-row" data-testid="todo-item">
              <StatusPill tone={t.orders ? 'pending' : 'neutral'} className="todo-count">
                {t.flagged.length}
              </StatusPill>
              <span style={{ flex: 1, minWidth: 0 }}>
                <strong>{t.sign_type}</strong>
                <span className="caption" style={{ display: 'block' }}>
                  {t.orders ? `${t.orders} order${t.orders === 1 ? '' : 's'} · ` : 'v' + t.version + ' ' + t.status + ' · '}
                  {describeKinds(t.flagged.map((f) => f.problem))}
                </span>
              </span>
            </Link>
          ))}
          {!showAll && items.length > shown.length && (
            <button type="button" className="todo-row" style={{ width: '100%', background: 'none', border: 0, cursor: 'pointer', textAlign: 'left' }} onClick={() => setShowAll(true)}>
              <StatusPill tone="neutral" className="todo-count">
                {quietFlags + urgent.slice(TODO_SHOWN).reduce((n, t) => n + t.flagged.length, 0)}
              </StatusPill>
              <span style={{ flex: 1 }}>
                <strong>{items.length - shown.length} more drafts</strong>
                <span className="caption" style={{ display: 'block' }}>
                  {quiet.length ? `${quiet.length} with no orders this month` : 'show all'}
                </span>
              </span>
            </button>
          )}
          {showAll && items.length > TODO_SHOWN && (
            <button type="button" className="link-button caption" style={{ margin: '8px 12px' }} onClick={() => setShowAll(false)}>
              Show fewer
            </button>
          )}
        </div>
      )}
    </section>
  )
}

// ---------------------------------------------------------------- Airtable names that match no sign type

function UnmappedPanel({ unmapped, signTypes, onNewSignType }: { unmapped: ReturnType<typeof useQuery<UnmappedName[]>>; signTypes: SignType[]; onNewSignType: (name: string) => void }) {
  const queryClient = useQueryClient()
  const { canEditTemplates } = useAuth()
  const [showAll, setShowAll] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const map = useMutation({
    mutationFn: async ({ name, signTypeId }: { name: string; signTypeId: number }) => {
      const s = signTypes.find((x) => x.id === signTypeId)!
      return api<SignType>(`/sign-types/${s.id}`, { method: 'PATCH', json: { name: s.name, code: s.code, aliases: [...new Set([...s.aliases, name])], active: s.active } })
    },
    onSuccess: () => {
      // orders got re-mapped on the server, so everything that counts them is stale
      for (const key of ['unmapped', 'sign-types', 'orders', 'dashboard', 'order']) queryClient.invalidateQueries({ queryKey: [key] })
    },
    onError: (e) => setError(errorMessage(e)),
  })
  if (unmapped.isError) return <PageError title="Couldn’t load unmapped names" error={unmapped.error} />
  const list = unmapped.data ?? []
  const shown = showAll ? list : list.slice(0, UNMAPPED_SHOWN)

  return (
    <section className="card" aria-labelledby="um-h" id="unmapped" data-testid="unmapped-panel">
      <div className="card-head" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 2 }}>
        <h2 id="um-h" style={{ margin: 0, fontSize: 16, lineHeight: '24px', fontWeight: 700 }}>
          Airtable names to map
        </h2>
        <span className="caption">Pick a sign type and its orders re-map at once.</span>
      </div>
      {error && (
        <Text size="xs" c="var(--missing)" p="sm">
          {error}
        </Text>
      )}
      {!unmapped.data ? (
        <div className="card-body caption">Loading…</div>
      ) : list.length === 0 ? (
        <div className="card-body">
          <Text size="sm">Every order has a sign type.</Text>
        </div>
      ) : (
        <div>
          {shown.map((u) => (
            <div key={u.name} className="map-row" data-testid="unmapped-row">
              <span style={{ minWidth: 0 }}>
                <strong>{u.name}</strong>
                <span className="caption" style={{ display: 'block' }}>
                  {u.orders} order{u.orders === 1 ? '' : 's'}
                </span>
              </span>
              {canEditTemplates ? (
                <Select
                  size="sm"
                  searchable
                  placeholder="Map to…"
                  aria-label={`Map ${u.name} to`}
                  data={[...signTypes.filter((s) => s.active).map((s) => ({ value: String(s.id), label: s.name })), { value: 'new', label: '+ New sign type…' }]}
                  value={null}
                  disabled={map.isPending && map.variables?.name === u.name}
                  onChange={(v) => {
                    if (v === 'new') onNewSignType(u.name)
                    else if (v) map.mutate({ name: u.name, signTypeId: Number(v) })
                  }}
                />
              ) : (
                <span />
              )}
            </div>
          ))}
          {list.length > UNMAPPED_SHOWN && (
            <button type="button" className="link-button caption" style={{ margin: '10px 12px' }} onClick={() => setShowAll((v) => !v)}>
              {showAll ? 'Show fewer' : `All ${list.length} names`}
            </button>
          )}
        </div>
      )}
    </section>
  )
}

