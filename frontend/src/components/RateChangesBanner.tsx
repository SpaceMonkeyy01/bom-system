import { Button, Modal, Text, Title } from '@mantine/core'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, errorMessage } from '../api/client'
import type { Bom, BomDiff, RateChanges, RecalcResult } from '../api/types'
import { useAuth } from '../auth/AuthProvider'
import { rateTag } from '../lib/bom'
import { fmtNum, fmtPkr } from '../lib/format'
import { RateTag } from './ui'

/** Loads the rate changes for a saved BOM; shared by the banner and the lines table's "changed" tags. */
export function useRateChanges(bom: Bom) {
  return useQuery({
    queryKey: ['rate-changes', bom.id],
    queryFn: ({ signal }) => api<RateChanges>(`/boms/${bom.id}/rate-changes`, { signal }),
    enabled: bom.id !== null && bom.status !== 'imported',
  })
}

/** The headline on a saved BOM whose rates have moved: what changed, what it would cost today, recalc → preview → save. */
export function RateChangesBanner({ bom, changes }: { bom: Bom; changes: RateChanges | undefined }) {
  const { canWrite } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [dismissed, setDismissed] = useState(false)
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

  if (!changes || changes.count === 0 || dismissed) return null
  const n = changes.count
  const next = bom.version + 1
  const diff = recalc.data?.diff

  return (
    <>
      <section className="banner-pending" aria-labelledby="rc-h" data-testid="rate-changes">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, minWidth: 0 }}>
          <Title order={2} id="rc-h" style={{ color: 'var(--pending)' }}>
            {n} rate{n === 1 ? ' has' : 's have'} changed since this BOM was saved
          </Title>
          <p style={{ margin: 0 }}>
            {diff ? (
              <>
                Recalculating with today’s rates would make it <strong>PKR {fmtPkr(diff.grand_total[1])}</strong> (<Delta diff={diff} />).
              </>
            ) : (
              'Recalculating with today’s rates shows the new total before anything is written.'
            )}{' '}
            Nothing is written until you save the new version.
          </p>
          <table className="mini-table" style={{ width: 'auto' }}>
            <thead>
              <tr>
                <th style={{ background: 'transparent', paddingLeft: 0 }}>Line</th>
                <th style={{ background: 'transparent', textAlign: 'right' }}>Saved</th>
                <th style={{ background: 'transparent', textAlign: 'right' }}>Today</th>
                <th style={{ background: 'transparent' }}>Why</th>
              </tr>
            </thead>
            <tbody>
              {changes.changed_lines.map((c) => {
                const tag = rateTag({ rate_source: c.source, rate_stale: false, rate_date: null })
                return (
                  <tr key={c.line}>
                    <td style={{ paddingLeft: 0, fontWeight: 700, border: 0 }}>{c.line}</td>
                    <td className="num" style={{ border: 0 }}>
                      {fmtNum(c.frozen)}
                    </td>
                    <td className="num" style={{ border: 0, fontWeight: 700 }}>
                      {fmtNum(c.current)}
                    </td>
                    <td style={{ border: 0 }}>
                      <RateTag tone={tag.tone}>{tag.label}</RateTag> rate is current today
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {recalc.isError && (
            <Text size="xs" c="var(--missing)">
              {errorMessage(recalc.error)}
            </Text>
          )}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {canWrite && (
            <Button loading={recalc.isPending} onClick={() => (recalc.data ? setOpen(true) : recalc.mutate())}>
              Recalculate → preview v{next}
            </Button>
          )}
          <Button variant="default" onClick={() => setDismissed(true)}>
            Keep v{bom.version}
          </Button>
        </div>
      </section>
      <Modal opened={open} onClose={() => setOpen(false)} title={`Preview v${next} at today’s rates`} size="xl">
        {diff && <DiffTable diff={diff} />}
        {saveNew.isError && (
          <Text size="xs" c="var(--missing)" mt="xs">
            {errorMessage(saveNew.error)}
          </Text>
        )}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 16 }}>
          <Button variant="default" onClick={() => setOpen(false)}>
            Keep v{bom.version}
          </Button>
          <Button loading={saveNew.isPending} onClick={() => saveNew.mutate()}>
            Save as new version
          </Button>
        </div>
      </Modal>
    </>
  )
}

function Delta({ diff }: { diff: BomDiff }) {
  const [before] = diff.grand_total
  const pct = before ? (diff.delta_pkr / before) * 100 : 0
  const up = diff.delta_pkr > 0
  return (
    <span className={up ? 'delta-up' : diff.delta_pkr < 0 ? 'delta-down' : undefined}>
      {up ? '+' : ''}
      {fmtPkr(diff.delta_pkr)}, {up ? '+' : ''}
      {fmtNum(pct, 1)} %
    </span>
  )
}

const lineLabel = (key: string) => key.replace('|', ' · ').replace(/ · $/, '')

function DiffTable({ diff }: { diff: BomDiff }) {
  const [before, after] = diff.grand_total
  return (
    <>
      <p style={{ margin: '0 0 12px' }}>
        Grand total <strong>PKR {fmtPkr(before)}</strong> → <strong>PKR {fmtPkr(after)}</strong> (<Delta diff={diff} />)
        {diff.template_changed && <RateTag tone="info">uses the current published template</RateTag>}
      </p>
      {diff.changed.length + diff.added.length + diff.removed.length === 0 ? (
        <Text size="sm" c="var(--slate)">
          No line differs.
        </Text>
      ) : (
        <div className="card table-wrap">
          <table className="tbl tbl-dense mantine-Table-table">
            <thead>
              <tr>
                <th>Line</th>
                <th className="num">Qty</th>
                <th className="num">Rate</th>
                <th>Source</th>
                <th className="num">Total</th>
                <th className="num">Δ</th>
              </tr>
            </thead>
            <tbody>
              {diff.changed.map((c) => (
                <tr key={c.line}>
                  <td>{lineLabel(c.line)}</td>
                  <td className="num">{c.qty[0] === c.qty[1] ? fmtNum(c.qty[1], 3) : `${fmtNum(c.qty[0], 3)} → ${fmtNum(c.qty[1], 3)}`}</td>
                  <td className="num">{c.rate[0] === c.rate[1] ? fmtNum(c.rate[1]) : `${fmtNum(c.rate[0])} → ${fmtNum(c.rate[1])}`}</td>
                  <td>{c.rate_source[0] === c.rate_source[1] ? c.rate_source[1] : `${c.rate_source[0]} → ${c.rate_source[1]}`}</td>
                  <td className="num">
                    {fmtPkr(c.total[0])} → {fmtPkr(c.total[1])}
                  </td>
                  <td className={`num ${c.total[1] > c.total[0] ? 'delta-up' : 'delta-down'}`}>
                    {c.total[1] > c.total[0] ? '+' : ''}
                    {fmtPkr(c.total[1] - c.total[0])}
                  </td>
                </tr>
              ))}
              {diff.added.map((c) => (
                <tr key={`a-${c.line}`}>
                  <td>
                    <RateTag tone="done">added</RateTag> {lineLabel(c.line)}
                  </td>
                  <td className="num">{fmtNum(c.qty, 3)}</td>
                  <td className="num">{fmtNum(c.rate)}</td>
                  <td />
                  <td className="num">{fmtPkr(c.total)}</td>
                  <td className="num delta-up">+{fmtPkr(c.total)}</td>
                </tr>
              ))}
              {diff.removed.map((c) => (
                <tr key={`r-${c.line}`}>
                  <td>
                    <RateTag tone="missing">removed</RateTag> {lineLabel(c.line)}
                  </td>
                  <td className="num">{fmtNum(c.qty, 3)}</td>
                  <td className="num">{fmtNum(c.rate)}</td>
                  <td />
                  <td className="num">{fmtPkr(c.total)}</td>
                  <td className="num delta-down">−{fmtPkr(c.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
