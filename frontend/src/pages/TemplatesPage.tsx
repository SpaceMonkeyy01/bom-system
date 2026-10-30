import { Alert, Anchor, Badge, Button, Group, Modal, Paper, Select, Stack, Table, Text, TextInput, Title } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import type { FlaggedTemplate, Order, SignType, Template, TemplateSummary, UnmappedName } from '../api/types'
import { useAuth } from '../auth/AuthProvider'
import { PageError, PageLoader } from '../components/PageState'

const signTypesQuery = { queryKey: ['sign-types'], queryFn: ({ signal }: { signal: AbortSignal }) => api<SignType[]>('/sign-types', { signal }) }

export function TemplatesPage() {
  const signTypes = useQuery(signTypesQuery)
  if (signTypes.isPending) return <PageLoader />
  if (signTypes.isError) return <PageError title="Couldn’t load sign types" error={signTypes.error} />
  return (
    <div className="templates-page">
      <section>
        <SignTypesTable signTypes={signTypes.data} />
      </section>
      <aside className="templates-side">
        <FlaggedPanel />
        <UnmappedPanel signTypes={signTypes.data} />
      </aside>
    </div>
  )
}

// ---------------------------------------------------------------- sign types

function SignTypesTable({ signTypes }: { signTypes: SignType[] }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { canEditTemplates } = useAuth()
  const [filter, setFilter] = useState('')
  const [error, setError] = useState<string | null>(null)

  // One call, cached: counting 474 orders in the browser is cheaper than a new endpoint.
  const orders = useQuery({ queryKey: ['orders', { scope: 'all', q: '' }], queryFn: ({ signal }) => api<Order[]>('/orders', { query: { limit: 2000 }, signal }) })
  const orderCounts = useMemo(() => {
    const counts = new Map<number, number>()
    for (const o of orders.data ?? []) if (o.sign_type_id !== null) counts.set(o.sign_type_id, (counts.get(o.sign_type_id) ?? 0) + 1)
    return counts
  }, [orders.data])

  // Which sign types have a draft, and which version is published. Fetched per sign type with templates (~35 calls, tiny).
  const withTemplates = signTypes.filter((s) => s.template_count > 0)
  const versions = useQuery({
    queryKey: ['sign-type-versions', withTemplates.map((s) => s.id)],
    queryFn: async ({ signal }) => {
      const entries = await Promise.all(withTemplates.map(async (s) => [s.id, await api<TemplateSummary[]>(`/sign-types/${s.id}/templates`, { signal })] as const))
      return new Map(entries)
    },
  })

  const openEditor = useMutation({
    mutationFn: async (s: SignType) => {
      const draft = versions.data?.get(s.id)?.find((t) => t.status === 'draft')
      if (draft) return draft.id
      const created = await api<Template>('/templates/drafts', { json: { sign_type_id: s.id } })
      return created.id
    },
    onSuccess: (id) => {
      queryClient.invalidateQueries({ queryKey: ['sign-type-versions'] })
      queryClient.invalidateQueries({ queryKey: ['sign-types'] })
      navigate(`/templates/${id}`)
    },
    onError: (e) => setError(errorMessage(e)),
  })

  const q = filter.trim().toLowerCase()
  const rows = signTypes.filter((s) => !q || s.name.toLowerCase().includes(q) || s.aliases.some((a) => a.toLowerCase().includes(q)))

  return (
    <>
      <Group justify="space-between" mb="xs">
        <Group gap="sm">
          <Title order={5}>Sign types</Title>
          <TextInput size="xs" w={240} placeholder="Filter by name or alias" aria-label="Filter sign types" value={filter} onChange={(e) => setFilter(e.currentTarget.value)} />
          <Text size="xs" c="dimmed">
            {signTypes.filter((s) => s.published_template_id).length} of {signTypes.length} have a published template
          </Text>
        </Group>
        {canEditTemplates && <NewSignTypeButton />}
      </Group>
      {error && (
        <Alert color="red" p="xs" mb="xs" withCloseButton onClose={() => setError(null)}>
          <Text size="xs">{error}</Text>
        </Alert>
      )}
      <div className="table-wrap">
        <Table className="dense-table" highlightOnHover stickyHeader>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Sign type</Table.Th>
              <Table.Th>Code</Table.Th>
              <Table.Th>Published</Table.Th>
              <Table.Th>Draft</Table.Th>
              <Table.Th className="num">Orders</Table.Th>
              <Table.Th>Aliases</Table.Th>
              <Table.Th aria-label="Actions" />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {rows.map((s) => {
              const list = versions.data?.get(s.id) ?? []
              const published = list.find((t) => t.status === 'published')
              const draft = list.find((t) => t.status === 'draft')
              const count = orderCounts.get(s.id) ?? 0
              return (
                <Table.Tr key={s.id} data-testid={`sign-type-${s.id}`}>
                  <Table.Td>
                    <Anchor component={Link} to={`/sign-types/${s.id}`} size="xs" fw={600}>
                      {s.name}
                    </Anchor>
                    {!s.active && (
                      <Badge ml={6} size="xs" color="gray" variant="light">
                        inactive
                      </Badge>
                    )}
                  </Table.Td>
                  <Table.Td>{s.code ?? '—'}</Table.Td>
                  <Table.Td>
                    {published ? (
                      <Anchor component={Link} to={`/templates/${published.id}`} size="xs">
                        v{published.version} · {published.line_count} lines
                      </Anchor>
                    ) : (
                      <Badge size="xs" color={count ? 'red' : 'gray'} variant="light" tt="none">
                        {s.template_count ? 'none published' : 'no template'}
                      </Badge>
                    )}
                  </Table.Td>
                  <Table.Td>
                    {draft ? (
                      <Anchor component={Link} to={`/templates/${draft.id}`} size="xs">
                        v{draft.version}
                        {draft.flagged_lines ? ` · ${draft.flagged_lines} flagged` : ''}
                      </Anchor>
                    ) : (
                      <Text size="xs" c="dimmed">
                        —
                      </Text>
                    )}
                  </Table.Td>
                  <Table.Td className="num">{orders.data ? count : '…'}</Table.Td>
                  <Table.Td>
                    <Text size="xs" c="dimmed" lineClamp={1} maw={260} title={s.aliases.join(', ')}>
                      {s.aliases.join(', ')}
                    </Text>
                  </Table.Td>
                  <Table.Td className="nowrap">
                    {canEditTemplates ? (
                      <Button size="compact-xs" variant={draft ? 'light' : 'default'} loading={openEditor.isPending && openEditor.variables?.id === s.id} onClick={() => openEditor.mutate(s)}>
                        {draft ? 'Edit draft' : published ? 'New draft' : 'Create'}
                      </Button>
                    ) : (
                      published && (
                        <Button size="compact-xs" variant="default" component={Link} to={`/templates/${published.id}`}>
                          View
                        </Button>
                      )
                    )}
                  </Table.Td>
                </Table.Tr>
              )
            })}
          </Table.Tbody>
        </Table>
      </div>
    </>
  )
}

function NewSignTypeButton() {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const create = useMutation({
    mutationFn: () => api<SignType>('/sign-types', { json: { name: name.trim(), code: code.trim() || null, aliases: [], active: true } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sign-types'] })
      setOpen(false)
      setName('')
      setCode('')
    },
  })
  return (
    <>
      <Button size="xs" variant="default" onClick={() => setOpen(true)}>
        New sign type
      </Button>
      <Modal opened={open} onClose={() => setOpen(false)} title="New sign type" size="sm">
        <Stack gap="xs">
          <TextInput size="xs" label="Name" required autoFocus value={name} onChange={(e) => setName(e.currentTarget.value)} />
          <TextInput size="xs" label="Code" placeholder="e.g. 26" value={code} onChange={(e) => setCode(e.currentTarget.value)} />
          {create.isError && (
            <Text size="xs" c="red">
              {errorMessage(create.error)}
            </Text>
          )}
          <Button size="xs" disabled={!name.trim()} loading={create.isPending} onClick={() => create.mutate()}>
            Create
          </Button>
        </Stack>
      </Modal>
    </>
  )
}

// ---------------------------------------------------------------- flagged lines (the template owner's to-do list)

function FlaggedPanel() {
  const flagged = useQuery({ queryKey: ['flagged'], queryFn: ({ signal }) => api<FlaggedTemplate[]>('/templates/flagged', { signal }) })
  const [openId, setOpenId] = useState<number | null>(null)
  if (flagged.isError) return <PageError title="Couldn’t load the to-do list" error={flagged.error} />
  if (!flagged.data) return null
  const total = flagged.data.reduce((n, t) => n + t.flagged.length, 0)

  return (
    <Paper withBorder p="xs" className="todo-panel" data-testid="todo-panel">
      <Group justify="space-between" mb={4}>
        <Title order={5}>To do: flagged lines</Title>
        <Badge color={total ? 'orange' : 'green'} variant="filled" size="lg">
          {total}
        </Badge>
      </Group>
      <Text size="xs" c="dimmed" mb="xs">
        Lines the import couldn’t make sense of, by template. Publishing a template clears its flags.
      </Text>
      {total === 0 ? (
        <Text size="xs">Nothing flagged.</Text>
      ) : (
        <Stack gap={4}>
          {flagged.data.map((t) => {
            const open = openId === t.template_id
            return (
              <div key={t.template_id} className="todo-item">
                <Group justify="space-between" wrap="nowrap" gap="xs">
                  <Anchor component={Link} to={`/templates/${t.template_id}`} size="xs" fw={600} lineClamp={1}>
                    {t.sign_type}
                  </Anchor>
                  <Group gap={4} wrap="nowrap">
                    <Text size="xs" c="dimmed" className="nowrap">
                      v{t.version} {t.status}
                    </Text>
                    <Badge size="xs" color="orange" variant="light">
                      {t.flagged.length}
                    </Badge>
                    <Button size="compact-xs" variant="subtle" onClick={() => setOpenId(open ? null : t.template_id)} aria-expanded={open}>
                      {open ? 'Hide' : 'Show'}
                    </Button>
                  </Group>
                </Group>
                {open && (
                  <Table className="dense-table todo-lines" mt={4}>
                    <Table.Tbody>
                      {t.flagged.map((f) => (
                        <Table.Tr key={f.line_id}>
                          <Table.Td>{f.material ?? '?'}</Table.Td>
                          <Table.Td>
                            <code className="formula">{f.formula}</code>
                          </Table.Td>
                          <Table.Td c="orange.9">{f.problem}</Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                )}
              </div>
            )
          })}
        </Stack>
      )}
    </Paper>
  )
}

// ---------------------------------------------------------------- Airtable names that match no sign type

function UnmappedPanel({ signTypes }: { signTypes: SignType[] }) {
  const queryClient = useQueryClient()
  const { canEditTemplates } = useAuth()
  const unmapped = useQuery({ queryKey: ['unmapped'], queryFn: ({ signal }) => api<UnmappedName[]>('/sign-types/unmapped', { signal }) })
  const [choice, setChoice] = useState<Record<string, string | null>>({})
  const [error, setError] = useState<string | null>(null)

  const map = useMutation({
    mutationFn: async ({ name, signTypeId }: { name: string; signTypeId: number }) => {
      const s = signTypes.find((x) => x.id === signTypeId)!
      return api<SignType>(`/sign-types/${s.id}`, {
        method: 'PATCH',
        json: { name: s.name, code: s.code, aliases: [...new Set([...s.aliases, name])], active: s.active },
      })
    },
    onSuccess: () => {
      // orders got re-mapped on the server, so everything that counts them is stale
      for (const key of ['unmapped', 'sign-types', 'orders', 'dashboard', 'order']) queryClient.invalidateQueries({ queryKey: [key] })
    },
    onError: (e) => setError(errorMessage(e)),
  })

  if (unmapped.isError) return <PageError title="Couldn’t load unmapped names" error={unmapped.error} />
  if (!unmapped.data) return null

  return (
    <Paper withBorder p="xs" data-testid="unmapped-panel">
      <Group justify="space-between" mb={4}>
        <Title order={5}>Unmapped Airtable names</Title>
        <Badge color={unmapped.data.length ? 'red' : 'green'} variant="light" size="lg" tt="none">
          {unmapped.data.reduce((n, u) => n + u.orders, 0)} orders
        </Badge>
      </Group>
      <Text size="xs" c="dimmed" mb="xs">
        Sign-type names typed in Airtable that match nothing here. Mapping one adds it as an alias and re-maps its orders at once.
      </Text>
      {error && (
        <Text size="xs" c="red" mb={4}>
          {error}
        </Text>
      )}
      {unmapped.data.length === 0 ? (
        <Text size="xs">Every order has a sign type.</Text>
      ) : (
        <Table className="dense-table">
          <Table.Tbody>
            {unmapped.data.map((u) => (
              <Table.Tr key={u.name} data-testid="unmapped-row">
                <Table.Td>
                  <Text size="xs" fw={500} lineClamp={2}>
                    {u.name}
                  </Text>
                </Table.Td>
                <Table.Td className="num nowrap">{u.orders}</Table.Td>
                {canEditTemplates && (
                  <Table.Td className="nowrap">
                    <Group gap={4} wrap="nowrap">
                      <Select
                        size="xs"
                        className="compact-select"
                        w={190}
                        searchable
                        placeholder="Map to…"
                        aria-label={`Map ${u.name} to`}
                        data={signTypes.filter((s) => s.active).map((s) => ({ value: String(s.id), label: s.name }))}
                        value={choice[u.name] ?? null}
                        onChange={(v) => setChoice((c) => ({ ...c, [u.name]: v }))}
                      />
                      <Button
                        size="compact-xs"
                        disabled={!choice[u.name]}
                        loading={map.isPending && map.variables?.name === u.name}
                        onClick={() => map.mutate({ name: u.name, signTypeId: Number(choice[u.name]) })}
                      >
                        Map
                      </Button>
                    </Group>
                  </Table.Td>
                )}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Paper>
  )
}
