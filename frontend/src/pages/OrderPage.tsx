import { Anchor, Badge, Button, Center, Group, Paper, Table, Text, Title } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { Bom, Order } from '../api/types'
import { useAuth } from '../auth/AuthProvider'
import { OrderFacts } from '../components/OrderFacts'
import { PageError, PageLoader } from '../components/PageState'
import { isImported } from '../lib/bom'
import { fmtDate, fmtPkr, fmtUsd } from '../lib/format'

/** An order and its saved BOMs. This is where read-only roles land, and where a new version starts from. */
export function OrderPage() {
  const orderId = Number(useParams().orderId)
  const navigate = useNavigate()
  const { canWrite } = useAuth()
  const order = useQuery({
    queryKey: ['order', orderId],
    queryFn: ({ signal }) => api<Order>(`/orders/${orderId}`, { signal }),
  })
  const boms = useQuery({
    queryKey: ['order-boms', orderId],
    queryFn: ({ signal }) => api<Bom[]>(`/orders/${orderId}/boms`, { signal }),
  })

  if (order.isPending) return <PageLoader />
  if (order.isError) return <PageError title="Couldn’t load this order" error={order.error} />

  const versions = [...(boms.data ?? [])].sort((a, b) => b.version - a.version)

  return (
    <div className="bom-page">
      <aside className="bom-side">
        <OrderFacts order={order.data} />
      </aside>
      <section className="bom-main">
        <Group justify="space-between" mb="xs">
          <Title order={5}>Saved BOMs</Title>
          {canWrite && (
            <Button size="xs" component={Link} to={`/orders/${orderId}/bom`}>
              {versions.length ? 'New version' : 'Create BOM'}
            </Button>
          )}
        </Group>
        {boms.isError ? (
          <PageError title="Couldn’t load the saved BOMs" error={boms.error} />
        ) : boms.isPending ? (
          <PageLoader />
        ) : versions.length === 0 ? (
          <Paper withBorder p="xl">
            <Center>
              <Text c="dimmed" size="sm">
                No BOM has been saved for this order yet.
              </Text>
            </Center>
          </Paper>
        ) : (
          <div className="table-wrap">
            <Table className="dense-table" highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Version</Table.Th>
                  <Table.Th>Status</Table.Th>
                  <Table.Th>Saved</Table.Th>
                  <Table.Th className="num">Grand total (PKR)</Table.Th>
                  <Table.Th className="num">Material (USD)</Table.Th>
                  <Table.Th className="num">Production (USD)</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {versions.map((b) => (
                  <Table.Tr key={b.id} className="clickable" onClick={() => navigate(`/boms/${b.id}`)}>
                    <Table.Td>
                      <Anchor component={Link} to={`/boms/${b.id}`} size="xs" fw={600} onClick={(e) => e.stopPropagation()}>
                        v{b.version}
                      </Anchor>
                    </Table.Td>
                    <Table.Td>
                      <Badge size="xs" variant="light" color="green" tt="none">
                        {b.status}
                      </Badge>
                    </Table.Td>
                    <Table.Td>{isImported(b) ? 'From the old sheet' : fmtDate(b.saved_at)}</Table.Td>
                    <Table.Td className="num">{fmtPkr(b.grand_total_pkr)}</Table.Td>
                    <Table.Td className="num">{fmtUsd(b.material_cost_usd)}</Table.Td>
                    <Table.Td className="num">{fmtUsd(b.production_cost_usd)}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </div>
        )}
      </section>
    </div>
  )
}
