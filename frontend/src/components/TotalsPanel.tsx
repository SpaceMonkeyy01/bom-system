import { Divider, Paper, SimpleGrid, Text } from '@mantine/core'
import type { ReactNode } from 'react'
import type { Bom } from '../api/types'
import { fmtNum, fmtPkr, fmtUsd } from '../lib/format'

function Row({ label, children, strong }: { label: ReactNode; children: ReactNode; strong?: boolean }) {
  return (
    <div className="total-row">
      <Text span size="xs" c={strong ? undefined : 'dimmed'} fw={strong ? 700 : undefined}>
        {label}
      </Text>
      <Text span size="xs" fw={strong ? 700 : 500} className="total-value">
        {children}
      </Text>
    </div>
  )
}

/** Read-only unless `miscInput` is given, in which case that input replaces the printed misc %. */
export function TotalsPanel({ bom, miscInput }: { bom: Bom; miscInput?: ReactNode }) {
  const heads = Object.entries(bom.by_cost_head)
    .filter(([, amount]) => amount !== 0)
    .sort((a, b) => b[1] - a[1])

  return (
    <Paper withBorder p="xs">
      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="lg">
        <div>
          <Row label="Base">{fmtPkr(bom.base_total_pkr)}</Row>
          <Row label="Wastage">{fmtPkr(bom.wastage_total_pkr)}</Row>
          <Row label={miscInput ? <span className="misc-label">Misc % {miscInput}</span> : `Misc (${fmtNum(bom.misc_pct)} %)`}>{fmtPkr(bom.misc_total_pkr)}</Row>
          <Divider my={3} />
          <Row label="Grand total (PKR)" strong>
            {fmtPkr(bom.grand_total_pkr)}
          </Row>
          <Row label="Material (USD)" strong>
            {fmtUsd(bom.material_cost_usd)}
          </Row>
          <Row label="Production (USD)" strong>
            {fmtUsd(bom.production_cost_usd)}
          </Row>
          <Text size="xs" c="dimmed" mt={3}>
            at PKR {fmtNum(bom.pkr_per_usd)} per USD
          </Text>
        </div>
        <div>
          <Text size="xs" fw={600} mb={2}>
            By cost head (PKR)
          </Text>
          {heads.length === 0 ? (
            <Text size="xs" c="dimmed">
              Nothing costed yet.
            </Text>
          ) : (
            heads.map(([head, amount]) => (
              <Row key={head} label={head}>
                {fmtPkr(amount)}
              </Row>
            ))
          )}
        </div>
      </SimpleGrid>
    </Paper>
  )
}
