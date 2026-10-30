import { Alert, Anchor, Badge, Button, Center, Group, Loader, SegmentedControl, Table, Text, TextInput } from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { errorMessage } from '../api/client'
import type { Order } from '../api/types'
import { useAuth } from '../auth/AuthProvider'
import { DashboardStrip } from '../components/DashboardStrip'
import { OrderThumb } from '../components/OrderThumb'
import { fmtDate, fmtSize, isOverdue } from '../lib/format'
import { ordersQuery, type OrderScope } from '../lib/orders'

export function QueuePage() {
  const navigate = useNavigate()
  const { canWrite } = useAuth()
  const [search, setSearch] = useState('')
  const [scope, setScope] = useState<OrderScope>('needs_bom')
  const [q] = useDebouncedValue(search.trim(), 250)

  const orders = useQuery({ ...ordersQuery(scope, q), placeholderData: keepPreviousData })

  // Writers go straight to Create BOM; an order that already has a BOM opens on its versions first.
  const orderPath = (o: Order) => (canWrite && o.bom_count === 0 ? `/orders/${o.id}/bom` : `/orders/${o.id}`)

  return (
    <>
      <DashboardStrip />
      <Group mb="xs" gap="sm">
        <TextInput
          placeholder="Search code, account or sign type"
          aria-label="Search orders"
          size="xs"
          w={300}
          value={search}
          onChange={(e) => setSearch(e.currentTarget.value)}
        />
        <SegmentedControl
          size="xs"
          value={scope}
          onChange={(v) => setScope(v as OrderScope)}
          data={[
            { value: 'needs_bom', label: 'Needs BOM' },
            { value: 'all', label: 'All orders' },
          ]}
        />
        {orders.data && (
          <Text size="xs" c="dimmed">
            {orders.data.length} order{orders.data.length === 1 ? '' : 's'}
          </Text>
        )}
        {orders.isFetching && orders.data && <Loader size={14} />}
      </Group>

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
      ) : orders.data.length === 0 ? (
        <Center p="xl">
          <Text c="dimmed">{q ? `No orders match “${q}”.` : 'No orders waiting for a BOM.'}</Text>
        </Center>
      ) : (
        <div className="table-wrap">
          <Table className="dense-table" highlightOnHover stickyHeader>
            <Table.Thead>
              <Table.Tr>
                <Table.Th w={36} aria-label="Image" />
                <Table.Th>Code</Table.Th>
                <Table.Th>Account</Table.Th>
                <Table.Th>Sign type</Table.Th>
                <Table.Th className="num">W × H (in)</Table.Th>
                <Table.Th>Finish</Table.Th>
                <Table.Th>LED</Table.Th>
                <Table.Th>Dispatch by</Table.Th>
                <Table.Th>Weekly bucket</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {orders.data.map((o) => (
                <Table.Tr key={o.id} className="clickable" onClick={() => navigate(orderPath(o))}>
                  <Table.Td>
                    <OrderThumb orderId={o.id} images={o.images} />
                  </Table.Td>
                  <Table.Td className="nowrap">
                    <Anchor component={Link} to={orderPath(o)} size="xs" fw={600} onClick={(e) => e.stopPropagation()}>
                      {o.code}
                    </Anchor>
                    {o.bom_count > 0 && (
                      <Badge ml={6} size="xs" variant="light" color="green" tt="none">
                        v{o.bom_count}
                      </Badge>
                    )}
                  </Table.Td>
                  <Table.Td>{o.account_name ?? '—'}</Table.Td>
                  <Table.Td>
                    <SignTypeCell order={o} />
                  </Table.Td>
                  <Table.Td className="num nowrap">{fmtSize(o.width_in, o.height_in)}</Table.Td>
                  <Table.Td>{o.finish ?? '—'}</Table.Td>
                  <Table.Td>{o.led_color ?? '—'}</Table.Td>
                  <Table.Td className="nowrap" c={isOverdue(o.dispatch_by) ? 'red' : undefined} fw={isOverdue(o.dispatch_by) ? 600 : undefined}>
                    {fmtDate(o.dispatch_by)}
                  </Table.Td>
                  <Table.Td>{o.weekly_bucket ?? '—'}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </div>
      )}
    </>
  )
}

function SignTypeCell({ order }: { order: Order }) {
  const { sign_type_raw: raw, sign_type_id: id, sign_type_name: name } = order
  return (
    <>
      <span>{raw ?? name ?? '—'}</span>
      {id === null ? (
        <Badge ml={6} size="xs" color="red" variant="light">
          Unmapped
        </Badge>
      ) : (
        name &&
        name !== raw && (
          <Text span c="dimmed" size="xs" display="block">
            → {name}
          </Text>
        )
      )}
    </>
  )
}
