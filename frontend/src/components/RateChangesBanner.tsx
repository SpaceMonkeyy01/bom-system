import { Alert, Badge, Button, Group, Modal, Table, Text } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import type { Bom, BomDiff, RateChanges, RecalcResult } from '../api/types'
import { useAuth } from '../auth/AuthProvider'
import { fmtNum, fmtPkr } from '../lib/format'

/** "Rates have changed since this BOM was saved": shown on saved BOMs with a Recalculate flow behind it. */
export function RateChangesBanner({ bom }: { bom: Bom }) {
  const { canWrite } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const changes = useQuery({
    queryKey: ['rate-changes', bom.id],
    queryFn: ({ signal }) => api<RateChanges>(`/boms/${bom.id}/rate-changes`, { signal }),
    enabled: bom.id !== null && bom.status !== 'imported',
  })
  const recalc = useMutation({
    mutationFn: () => api<RecalcResult>(`/boms/${bom.id}/recalculate`, { method: 'POST' }),
    onSuccess: () => setOpen(true),
  })
  const saveNew = useMutation({
    mutationFn: () => api<Bom>(`/boms/${bom.id}/recalculate/save`, { method: 'POST' }),
    onSuccess: (saved) => {
      for (const key of ['orders', 'order', 'order-boms', 'dashboard', 'rate-changes']) queryClient.invalidateQueries({ queryKey: [key] })
      setOpen(false)
      navigate(`/boms/${saved.id}`, { state: { justSaved: true } })
    },
  })

  if (!changes.data || changes.data.count === 0) return null
  const n = changes.data.count

  return (
    <>
      <Alert color="yellow" p="xs" mt={6} mb={6} data-testid="rate-changes">
        <Group justify="space-between" wrap="nowrap">
          <Text size="xs">
            Rates have changed since this BOM was saved: {n} line{n === 1 ? '' : 's'} would cost differently today (
            {changes.data.changed_lines
              .slice(0, 3)
              .map((c) => `${c.line}: ${fmtNum(c.frozen)} → ${fmtNum(c.current)}`)
              .join('; ')}
            {n > 3 ? '; …' : ''}).
          </Text>
          {canWrite && (
            <Button size="compact-xs" variant="light" color="yellow" loading={recalc.isPending} onClick={() => recalc.mutate()}>
              Recalculate
            </Button>
          )}
        </Group>
        {recalc.isError && (
          <Text size="xs" c="red" mt={4}>
            {errorMessage(recalc.error)}
          </Text>
        )}
      </Alert>
      <Modal opened={open} onClose={() => setOpen(false)} title={`Recalculated v${bom.version} at today’s rates`} size="xl">
        {recalc.data && <DiffTable diff={recalc.data.diff} />}
        {saveNew.isError && (
          <Text size="xs" c="red" mt="xs">
            {errorMessage(saveNew.error)}
          </Text>
        )}
        <Group justify="flex-end" mt="md">
          <Button size="xs" variant="default" onClick={() => setOpen(false)}>
            Close
          </Button>
          <Button size="xs" loading={saveNew.isPending} onClick={() => saveNew.mutate()}>
            Save as new version
          </Button>
        </Group>
      </Modal>
    </>
  )
}

function DiffTable({ diff }: { diff: BomDiff }) {
  const [before, after] = diff.grand_total
  const up = diff.delta_pkr > 0
  return (
    <>
      <Group gap="md" mb="xs">
        <Text size="sm">
          Grand total <b>PKR {fmtPkr(before)}</b> → <b>PKR {fmtPkr(after)}</b>
        </Text>
        <Badge color={diff.delta_pkr === 0 ? 'gray' : up ? 'red' : 'green'} variant="light" tt="none" size="lg">
          {up ? '+' : ''}
          {fmtPkr(diff.delta_pkr)}
        </Badge>
        {diff.template_changed && (
          <Badge color="blue" variant="light" tt="none">
            uses the current published template
          </Badge>
        )}
      </Group>
      {diff.changed.length + diff.added.length + diff.removed.length === 0 ? (
        <Text size="xs" c="dimmed">
          No line differs.
        </Text>
      ) : (
        <div className="table-wrap">
          <Table className="dense-table">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Line</Table.Th>
                <Table.Th className="num">Qty</Table.Th>
                <Table.Th className="num">Rate</Table.Th>
                <Table.Th>Source</Table.Th>
                <Table.Th className="num">Total</Table.Th>
                <Table.Th className="num">Δ</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {diff.changed.map((c) => (
                <Table.Tr key={c.line}>
                  <Table.Td>{c.line.replace('|', ' · ').replace(/ · $/, '')}</Table.Td>
                  <Table.Td className="num">{c.qty[0] === c.qty[1] ? fmtNum(c.qty[1], 3) : `${fmtNum(c.qty[0], 3)} → ${fmtNum(c.qty[1], 3)}`}</Table.Td>
                  <Table.Td className="num">{c.rate[0] === c.rate[1] ? fmtNum(c.rate[1]) : `${fmtNum(c.rate[0])} → ${fmtNum(c.rate[1])}`}</Table.Td>
                  <Table.Td>{c.rate_source[0] === c.rate_source[1] ? c.rate_source[1] : `${c.rate_source[0]} → ${c.rate_source[1]}`}</Table.Td>
                  <Table.Td className="num">
                    {fmtPkr(c.total[0])} → {fmtPkr(c.total[1])}
                  </Table.Td>
                  <Table.Td className="num" c={c.total[1] > c.total[0] ? 'red' : 'green'}>
                    {c.total[1] > c.total[0] ? '+' : ''}
                    {fmtPkr(c.total[1] - c.total[0])}
                  </Table.Td>
                </Table.Tr>
              ))}
              {diff.added.map((c) => (
                <Table.Tr key={`a-${c.line}`}>
                  <Table.Td>
                    <Badge size="xs" color="green" variant="light" mr={4}>
                      added
                    </Badge>
                    {c.line.replace('|', ' · ').replace(/ · $/, '')}
                  </Table.Td>
                  <Table.Td className="num">{fmtNum(c.qty, 3)}</Table.Td>
                  <Table.Td className="num">{fmtNum(c.rate)}</Table.Td>
                  <Table.Td />
                  <Table.Td className="num">{fmtPkr(c.total)}</Table.Td>
                  <Table.Td className="num" c="red">
                    +{fmtPkr(c.total)}
                  </Table.Td>
                </Table.Tr>
              ))}
              {diff.removed.map((c) => (
                <Table.Tr key={`r-${c.line}`}>
                  <Table.Td>
                    <Badge size="xs" color="red" variant="light" mr={4}>
                      removed
                    </Badge>
                    {c.line.replace('|', ' · ').replace(/ · $/, '')}
                  </Table.Td>
                  <Table.Td className="num">{fmtNum(c.qty, 3)}</Table.Td>
                  <Table.Td className="num">{fmtNum(c.rate)}</Table.Td>
                  <Table.Td />
                  <Table.Td className="num">{fmtPkr(c.total)}</Table.Td>
                  <Table.Td className="num" c="green">
                    −{fmtPkr(c.total)}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </div>
      )}
    </>
  )
}
