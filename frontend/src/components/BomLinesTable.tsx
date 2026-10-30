import { Checkbox, Title, Tooltip } from '@mantine/core'
import { type ReactNode, useState } from 'react'
import { isEdited, isHideable, type LineRow, rateTag, rateWarning } from '../lib/bom'
import { fmtNum, fmtPkr } from '../lib/format'
import { RateTag } from './ui'

interface Props {
  rows: LineRow[]
  /** Card title; the lines live in their own bordered section. */
  title?: string
  /** Caption after the title, e.g. "Rates frozen at save". */
  meta?: ReactNode
  /** Editable quantity cell; defaults to the plain number. */
  renderQty?: (row: LineRow) => ReactNode
  /** Editable cost head cell; defaults to the plain name. */
  renderCostHead?: (row: LineRow) => ReactNode
  /** Row actions such as removing an added line. Adds a column when given. */
  renderActions?: (row: LineRow) => ReactNode
  /** Content under the table, inside the card, e.g. "Add material". */
  footer?: ReactNode
  compact?: boolean
}

export function BomLinesTable({ rows, title = 'Lines', meta, renderQty, renderCostHead, renderActions, footer, compact }: Props) {
  const [showZero, setShowZero] = useState(false)
  const hiddenCount = rows.filter(isHideable).length
  const visible = showZero ? rows : rows.filter((r) => !isHideable(r))
  const withQty = rows.length - hiddenCount

  return (
    <section className="card bom-lines" data-testid="lines-card">
      <div className="card-head">
        <Title order={2}>{title}</Title>
        <span className="caption">
          {meta ? <>{meta} · </> : null}
          {withQty} with quantity{hiddenCount ? ` · ${hiddenCount} at zero hidden` : ''}
        </span>
        <div className="card-head-right">
          <Checkbox
            size="xs"
            checked={showZero}
            disabled={hiddenCount === 0 && !showZero}
            onChange={(e) => setShowZero(e.currentTarget.checked)}
            label={<span className="caption">Show zero-quantity lines ({hiddenCount})</span>}
          />
        </div>
      </div>
      <div className="table-wrap">
        <table className={`tbl mantine-Table-table${compact ? ' tbl-dense' : ''}`}>
          <thead>
            <tr>
              <th>Material</th>
              <th>Usage</th>
              <th className="num">Qty</th>
              <th>Unit</th>
              <th className="num">Rate</th>
              <th>Rate source</th>
              <th className="num">Wastage</th>
              <th className="num">Total</th>
              <th>Head</th>
              {renderActions && <th style={{ width: 28 }} aria-label="Actions" />}
            </tr>
          </thead>
          <tbody>
            {visible.map((row) => {
              const { line, pending } = row
              const tag = rateTag(line)
              const warning = rateWarning(line)
              return (
                <tr key={row.key} className={line.error ? 'row-error' : undefined} data-testid={row.key}>
                  <td>
                    <strong className="material-name">{line.material_name}</strong>
                    {row.flag && (
                      <Tooltip label={row.flag} withinPortal multiline maw={320}>
                        <span className="line-flag" aria-label={`Flagged: ${row.flag}`}>
                          ⚑
                        </span>
                      </Tooltip>
                    )}
                    {row.extraKey && <div className="caption">Added by you</div>}
                    {line.error && <div className="line-error">{line.error}</div>}
                    {warning && <div className="line-warning">{warning}</div>}
                    {line.override_note && !renderQty && <div className="line-note">{line.override_note}</div>}
                  </td>
                  <td style={{ color: 'var(--slate)' }}>{line.usage}</td>
                  <td className="num nowrap">{renderQty ? renderQty(row) : <FrozenQty row={row} />}</td>
                  <td>{line.uom}</td>
                  <td className="num">{pending ? '…' : fmtNum(line.rate)}</td>
                  <td>{!pending && <RateTag tone={tag.tone}>{tag.label}</RateTag>}</td>
                  <td className="num">{pending ? '…' : `${fmtNum(line.wastage_pct)} %`}</td>
                  <td className="num">
                    <strong>{pending ? '…' : fmtPkr(line.total_with_wastage_pkr)}</strong>
                  </td>
                  <td style={{ color: 'var(--slate)' }}>{renderCostHead ? renderCostHead(row) : line.cost_head}</td>
                  {renderActions && <td>{renderActions(row)}</td>}
                </tr>
              )
            })}
            {visible.length === 0 && (
              <tr>
                <td colSpan={10} className="caption">
                  {rows.length ? 'Every line is at zero. Tick “Show zero-quantity lines” to see them.' : 'No lines.'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {footer && <div className="card-foot">{footer}</div>}
    </section>
  )
}

function FrozenQty({ row }: { row: LineRow }) {
  const { qty_final: qty, qty_auto: auto, qty_formula: formula } = row.line
  return (
    <>
      {fmtNum(qty, 3)}
      {isEdited(row.line) && (
        <Tooltip label={`Edited. Formula ${formula ?? ''} gave ${fmtNum(auto, 3)}`} withinPortal>
          <span className="qty-edited" aria-label="Edited quantity">
            {'✎︎'}
          </span>
        </Tooltip>
      )}
    </>
  )
}
