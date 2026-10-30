import { Title } from '@mantine/core'
import type { ReactNode } from 'react'
import type { Bom } from '../api/types'
import { fmtNum, fmtPkr, fmtUsd } from '../lib/format'

interface Props {
  bom: Bom
  /** Replaces the printed misc % with an input on the Create BOM page. */
  miscInput?: ReactNode
  /** Fields after the totals, e.g. box dimension and shipment. */
  children?: ReactNode
  /** Lead with the total as a hero number; off in the compact preview rail. */
  hero?: boolean
}

/** The totals card for the right rail: hero total, breakdown, by cost head. */
export function TotalsPanel({ bom, miscInput, children, hero = true }: Props) {
  const heads = Object.entries(bom.by_cost_head)
    .filter(([, amount]) => amount !== 0)
    .sort((a, b) => b[1] - a[1])
  return (
    <section className="card card-body totals" data-testid="totals" aria-label="Totals">
      <div className="hero-total">
        <span className="caption body-strong">Grand total (PKR)</span>
        {hero ? <span className="hero-value" data-testid="grand-total">PKR {fmtPkr(bom.grand_total_pkr)}</span> : <Title order={2} data-testid="grand-total">PKR {fmtPkr(bom.grand_total_pkr)}</Title>}
        <span style={{ color: 'var(--slate)' }}>
          Material (USD) {fmtUsd(bom.material_cost_usd)} · Production (USD) <strong style={{ color: 'var(--ink)' }}>{fmtUsd(bom.production_cost_usd)}</strong>
        </span>
        <span className="caption">at PKR {fmtNum(bom.pkr_per_usd)} per USD</span>
      </div>
      <dl className="kv rule-top">
        <dt>Base</dt>
        <dd>{fmtPkr(bom.base_total_pkr)}</dd>
        <dt>Wastage</dt>
        <dd>{fmtPkr(bom.wastage_total_pkr)}</dd>
        <dt style={{ alignSelf: 'center' }}>{miscInput ? <span className="misc-label">Misc % {miscInput}</span> : `Misc ${fmtNum(bom.misc_pct)} %`}</dt>
        <dd style={{ alignSelf: 'center' }}>{fmtPkr(bom.misc_total_pkr)}</dd>
      </dl>
      <dl className="kv rule-top">
        <dt className="kv-title">By cost head</dt>
        {heads.length === 0 ? (
          <dt>Nothing costed yet</dt>
        ) : (
          heads.map(([head, amount]) => (
            <Fragment key={head}>
              <dt>{head}</dt>
              <dd>{fmtPkr(amount)}</dd>
            </Fragment>
          ))
        )}
      </dl>
      {children}
    </section>
  )
}

import { Fragment } from 'react'
