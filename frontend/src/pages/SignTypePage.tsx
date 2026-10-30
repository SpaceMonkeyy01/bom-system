import { Anchor, Badge, Button, Group, Paper, Select, SimpleGrid, Stack, Table, Text, Title } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { SignType, TemplateDiff, TemplateSummary } from '../api/types'
import { PageError, PageLoader } from '../components/PageState'
import { describeLineKey } from '../lib/templates'

/** One sign type's versions, with a diff between any two. */
export function SignTypePage() {
  const signTypeId = Number(useParams().signTypeId)
  const signTypes = useQuery({ queryKey: ['sign-types'], queryFn: ({ signal }) => api<SignType[]>('/sign-types', { signal }) })
  const versions = useQuery({
    queryKey: ['sign-type-templates', signTypeId],
    queryFn: ({ signal }) => api<TemplateSummary[]>(`/sign-types/${signTypeId}/templates`, { signal }),
  })
  const [pick, setPick] = useState<{ a: number | null; b: number | null }>({ a: null, b: null })

  if (signTypes.isPending || versions.isPending) return <PageLoader />
  if (signTypes.isError) return <PageError title="Couldn’t load sign types" error={signTypes.error} />
  if (versions.isError) return <PageError title="Couldn’t load versions" error={versions.error} />
  const signType = signTypes.data.find((s) => s.id === signTypeId)
  if (!signType) return <PageError title="Sign type not found" error={new Error(`No sign type ${signTypeId}`)} />

  const list = [...versions.data].sort((x, y) => y.version - x.version)
  // Default comparison: the published version and the newest other one, older → newer so "added" means added.
  const published = list.find((t) => t.status === 'published')
  const other = list.find((t) => t.id !== published?.id)
  const pair = [published ?? list[1], other ?? list[0]].filter((t): t is TemplateSummary => !!t).sort((x, y) => x.version - y.version)
  const a = pick.a ?? pair[0]?.id ?? null
  const b = pick.b ?? pair[1]?.id ?? null

  return (
    <Stack gap="sm">
      <Group justify="space-between">
        <Group gap="sm">
          <Anchor component={Link} to="/templates" size="xs">
            Templates
          </Anchor>
          <Text size="xs" c="dimmed">
            /
          </Text>
          <Title order={5}>{signType.name}</Title>
          {signType.code && (
            <Badge size="sm" variant="light" color="gray">
              {signType.code}
            </Badge>
          )}
        </Group>
        {signType.aliases.length > 0 && (
          <Text size="xs" c="dimmed" maw={600} truncate>
            Also known as: {signType.aliases.join(', ')}
          </Text>
        )}
      </Group>

      <div className="table-wrap">
        <Table className="dense-table" highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Version</Table.Th>
              <Table.Th>Status</Table.Th>
              <Table.Th>Source</Table.Th>
              <Table.Th className="num">Lines</Table.Th>
              <Table.Th className="num">Flagged</Table.Th>
              <Table.Th aria-label="Actions" />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {list.map((t) => (
              <Table.Tr key={t.id} data-testid={`version-${t.version}`}>
                <Table.Td>
                  <Anchor component={Link} to={`/templates/${t.id}`} size="xs" fw={600}>
                    v{t.version}
                  </Anchor>
                </Table.Td>
                <Table.Td>
                  <Badge size="xs" variant="light" color={t.status === 'published' ? 'green' : t.status === 'draft' ? 'blue' : 'gray'} tt="none">
                    {t.status}
                  </Badge>
                </Table.Td>
                <Table.Td>{t.source ?? '—'}</Table.Td>
                <Table.Td className="num">{t.line_count}</Table.Td>
                <Table.Td className="num">{t.flagged_lines || ''}</Table.Td>
                <Table.Td className="nowrap">
                  <Button size="compact-xs" variant="subtle" onClick={() => setPick((p) => ({ ...p, a: t.id }))} disabled={a === t.id}>
                    Compare from
                  </Button>
                  <Button size="compact-xs" variant="subtle" onClick={() => setPick((p) => ({ ...p, b: t.id }))} disabled={b === t.id}>
                    to
                  </Button>
                </Table.Td>
              </Table.Tr>
            ))}
            {list.length === 0 && (
              <Table.Tr>
                <Table.Td colSpan={6}>
                  <Text size="xs" c="dimmed">
                    No template yet for this sign type.
                  </Text>
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </div>

      {list.length >= 2 && (
        <Paper withBorder p="xs" data-testid="diff-panel">
          <Group gap="xs" mb="xs">
            <Text size="sm" fw={700}>
              Changes
            </Text>
            <Select size="xs" w={150} aria-label="From version" data={list.map((t) => ({ value: String(t.id), label: `v${t.version} (${t.status})` }))} value={a === null ? null : String(a)} onChange={(v) => setPick((p) => ({ ...p, a: v ? Number(v) : null }))} allowDeselect={false} />
            <Text size="xs">→</Text>
            <Select size="xs" w={150} aria-label="To version" data={list.map((t) => ({ value: String(t.id), label: `v${t.version} (${t.status})` }))} value={b === null ? null : String(b)} onChange={(v) => setPick((p) => ({ ...p, b: v ? Number(v) : null }))} allowDeselect={false} />
          </Group>
          {a !== null && b !== null && a !== b ? <DiffView a={a} b={b} /> : <Text size="xs" c="dimmed">Pick two different versions.</Text>}
        </Paper>
      )}
    </Stack>
  )
}

function DiffView({ a, b }: { a: number; b: number }) {
  const diff = useQuery({ queryKey: ['template-diff', a, b], queryFn: ({ signal }) => api<TemplateDiff>(`/templates/${a}/diff/${b}`, { signal }) })
  if (diff.isPending) return <PageLoader />
  if (diff.isError) return <PageError title="Couldn’t compare" error={diff.error} />
  const d = diff.data
  const total = d.params_added.length + d.params_removed.length + d.params_changed.length + d.lines_added.length + d.lines_removed.length + d.lines_changed.length
  if (total === 0)
    return (
      <Text size="xs" c="dimmed">
        No differences in inputs or lines.
      </Text>
    )
  const col = (title: string, items: string[], color: string, format: (s: string) => string = (s) => s) =>
    items.length > 0 && (
      <div>
        <Text size="xs" fw={600} c={color} mb={2}>
          {title} ({items.length})
        </Text>
        {items.map((k) => (
          <Text size="xs" key={k}>
            {format(k)}
          </Text>
        ))}
      </div>
    )
  return (
    <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
      <Stack gap="xs">
        {col('Inputs added', d.params_added, 'green.8')}
        {col('Inputs removed', d.params_removed, 'red.8')}
        {col('Inputs changed', d.params_changed, 'orange.8')}
      </Stack>
      <Stack gap="xs">
        {col('Lines added', d.lines_added, 'green.8', describeLineKey)}
        {col('Lines removed', d.lines_removed, 'red.8', describeLineKey)}
      </Stack>
      <Stack gap="xs">{col('Lines changed', d.lines_changed, 'orange.8', describeLineKey)}</Stack>
    </SimpleGrid>
  )
}
