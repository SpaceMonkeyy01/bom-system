import { Group, Paper, Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { DashboardSummary } from '../api/types'
import { fmtNum } from '../lib/format'

function Card({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <Paper withBorder className="stat-card">
      <Text size="lg" fw={700} lh={1.2} c={color}>
        {fmtNum(value)}
      </Text>
      <Text size="xs" c="dimmed">
        {label}
      </Text>
    </Paper>
  )
}

/** A failure here shouldn't get in the way of the queue underneath, so it just stays out of sight. */
export function DashboardStrip() {
  const { data } = useQuery({
    queryKey: ['dashboard'],
    queryFn: ({ signal }) => api<DashboardSummary>('/dashboard/summary', { signal }),
  })
  if (!data) return null

  const buckets = Object.entries(data.weekly_buckets).sort((a, b) => a[0].localeCompare(b[0]))

  return (
    <Group gap="xs" mb="xs" align="stretch" className="stat-strip" aria-label="Summary">
      <Card label="Awaiting BOM" value={data.orders_awaiting_bom} color={data.orders_awaiting_bom ? 'orange.8' : undefined} />
      <Card label="With BOM" value={data.orders_with_bom} />
      <Card label="All orders" value={data.orders} />
      <Card label="Unmapped sign type" value={data.orders_unmapped_sign_type} color={data.orders_unmapped_sign_type ? 'red.8' : undefined} />
      {buckets.length > 0 && (
        <Paper withBorder className="stat-card stat-buckets">
          <Text size="xs" c="dimmed" mb={2}>
            Orders by weekly bucket
          </Text>
          <Group gap="md">
            {buckets.map(([bucket, count]) => (
              <Text size="xs" key={bucket} className="nowrap">
                {bucket}: <b>{fmtNum(count)}</b>
              </Text>
            ))}
          </Group>
        </Paper>
      )}
    </Group>
  )
}
