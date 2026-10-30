import { Alert, Anchor, Badge, Button, Group, Paper, Stack, Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import type { Bom, Order, Template } from '../api/types'
import { useAuth } from '../auth/AuthProvider'
import { BomLinesTable } from '../components/BomLinesTable'
import { OrderFacts } from '../components/OrderFacts'
import { PageError, PageLoader } from '../components/PageState'
import { TotalsPanel } from '../components/TotalsPanel'
import { frozenRows, isImported } from '../lib/bom'
import { fmtDate, fmtUsd } from '../lib/format'

const BAR_HEIGHT = 46

export function BomDetailPage() {
  const bomId = Number(useParams().bomId)
  return <BomDetail key={bomId} bomId={bomId} />
}

/** A saved BOM, exactly as it was frozen. Nothing here recalculates. */
function BomDetail({ bomId }: { bomId: number }) {
  const location = useLocation()
  const navigate = useNavigate()
  const { canWrite } = useAuth()
  const [justSaved] = useState(() => !!(location.state as { justSaved?: boolean } | null)?.justSaved)

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
  const order = useQuery({
    queryKey: ['order', orderId],
    queryFn: ({ signal }) => api<Order>(`/orders/${orderId}`, { signal }),
    enabled: orderId !== undefined,
  })
  const versions = useQuery({
    queryKey: ['order-boms', orderId],
    queryFn: ({ signal }) => api<Bom[]>(`/orders/${orderId}/boms`, { signal }),
    enabled: orderId !== undefined,
  })
  const templateId = bom.data?.template_id
  const template = useQuery({
    queryKey: ['template', templateId],
    queryFn: ({ signal }) => api<Template>(`/templates/${templateId}`, { signal }),
    enabled: templateId !== undefined && templateId !== null,
  })

  const rows = useMemo(() => (bom.data ? frozenRows(bom.data) : []), [bom.data])

  if (bom.isPending) return <PageLoader />
  if (bom.isError) return <PageError title="Couldn’t load this BOM" error={bom.error} />
  const saved = bom.data

  // Labels and units come from the template; a saved BOM still reads fine without them.
  const paramInfo = new Map(template.data?.parameters.map((p) => [p.param_name, p]))
  const parameters = Object.entries(saved.parameters)

  return (
    <div className="bom-page">
      <aside className="bom-side">
        {order.data && <OrderFacts order={order.data} />}
        {parameters.length > 0 && (
          <Paper withBorder p="xs">
            <Text size="xs" fw={600} mb={2}>
              Parameters
            </Text>
            <Stack gap={2}>
              {parameters.map(([name, value]) => {
                const info = paramInfo.get(name)
                return (
                  <div className="fact" key={name}>
                    <Text span size="xs" c="dimmed">
                      {info?.label ?? name.replace(/_/g, ' ')}
                    </Text>
                    <Text span size="xs" fw={500}>
                      {value === null || value === '' ? '—' : `${value}${info?.uom ? ` ${info.uom}` : ''}`}
                    </Text>
                  </div>
                )
              })}
            </Stack>
          </Paper>
        )}
      </aside>

      <section className="bom-main">
        <Paper withBorder className="bom-bar" style={{ minHeight: BAR_HEIGHT }}>
          <Group gap="sm" wrap="nowrap">
            <Anchor component={Link} to={`/orders/${saved.order_id}`} size="sm" fw={700} className="nowrap">
              {saved.order_code}
            </Anchor>
            <Text size="sm" fw={700} className="nowrap">
              BOM v{saved.version}
            </Text>
            <Badge size="sm" color="green" variant="light" tt="none">
              {saved.status}
            </Badge>
            <Text size="xs" c="dimmed" className="nowrap" visibleFrom="sm">
              {/* imported dates are unreliable for now (API_REQUESTS.md #4) */}
              {isImported(saved) ? 'From the old sheet' : `Saved ${fmtDate(saved.saved_at)}`}
            </Text>
          </Group>
          <Group gap={4} wrap="nowrap">
            {(versions.data?.length ?? 0) > 1 &&
              [...versions.data!]
                .sort((a, b) => a.version - b.version)
                .map((v) => (
                  <Button
                    key={v.id}
                    size="compact-xs"
                    variant={v.id === saved.id ? 'filled' : 'default'}
                    component={Link}
                    to={`/boms/${v.id}`}
                    aria-current={v.id === saved.id ? 'page' : undefined}
                  >
                    v{v.version}
                  </Button>
                ))}
            {canWrite && (
              <Button size="xs" ml={6} variant="light" component={Link} to={`/orders/${saved.order_id}/bom`}>
                New version
              </Button>
            )}
          </Group>
        </Paper>

        {justSaved && (
          <Alert color="green" p="xs" mt={6} mb={6}>
            <Text size="xs">Saved as version {saved.version}.</Text>
          </Alert>
        )}

        <BomLinesTable rows={rows} stickyOffset={BAR_HEIGHT} />

        <div className="bom-below">
          <TotalsPanel bom={saved} />
          <Paper withBorder p="xs">
            <Stack gap={4}>
              <div className="fact">
                <Text span size="xs" c="dimmed">
                  Box dimension
                </Text>
                <Text span size="xs" fw={500}>
                  {saved.box_dimension ?? '—'}
                </Text>
              </div>
              <div className="fact">
                <Text span size="xs" c="dimmed">
                  Est. shipment
                </Text>
                <Text span size="xs" fw={500}>
                  {fmtUsd(saved.est_shipment_cost_usd)}
                </Text>
              </div>
              {saved.notes && (
                <Text size="xs" style={{ whiteSpace: 'pre-wrap' }}>
                  {saved.notes}
                </Text>
              )}
            </Stack>
          </Paper>
        </div>
      </section>
    </div>
  )
}
