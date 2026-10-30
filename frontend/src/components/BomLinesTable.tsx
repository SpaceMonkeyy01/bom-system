import { Group, Switch, Table, Text, Tooltip } from '@mantine/core'
import { type ReactNode, useState } from 'react'
import { isHideable, type LineRow, rateWarning } from '../lib/bom'
import { fmtNum, fmtPkr } from '../lib/format'
import { RateBadge } from './RateBadge'

interface Props {
  rows: LineRow[]
  /** Editable quantity cell; defaults to the plain number. */
  renderQty?: (row: LineRow) => ReactNode
  /** Editable cost head cell; defaults to the plain name. */
  renderCostHead?: (row: LineRow) => ReactNode
  /** Row actions such as removing an added line. Adds a column when given. */
  renderActions?: (row: LineRow) => ReactNode
  /** Extra rows after the lines, such as "Add material". */
  footer?: ReactNode
  /** Height of whatever is stuck above the table, so its header stops below it. */
  stickyOffset?: number
}

export function BomLinesTable({ rows, renderQty, renderCostHead, renderActions, footer, stickyOffset }: Props) {
  const [showZero, setShowZero] = useState(false)
  const hiddenCount = rows.filter(isHideable).length
  const visible = showZero ? rows : rows.filter((r) => !isHideable(r))

  return (
    <>
      <div className="table-wrap table-wrap-page">
        <Table className="dense-table bom-lines" highlightOnHover stickyHeader stickyHeaderOffset={stickyOffset}>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Material</Table.Th>
              <Table.Th>Usage</Table.Th>
              <Table.Th className="num">Qty</Table.Th>
              <Table.Th>UOM</Table.Th>
              <Table.Th className="num">Rate</Table.Th>
              <Table.Th>Rate source</Table.Th>
              <Table.Th className="num">Wastage %</Table.Th>
              <Table.Th className="num">Total + wastage</Table.Th>
              <Table.Th>Cost head</Table.Th>
              {renderActions && <Table.Th w={24} aria-label="Actions" />}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {visible.map((row) => {
              const { line, pending } = row
              return (
                <Table.Tr key={row.key} className={line.error ? 'row-error' : undefined} data-testid={row.key}>
                  <Table.Td>
                    <span className="material-name">{line.material_name}</span>
                    {row.flag && (
                      <Tooltip label={row.flag} withinPortal multiline maw={320}>
                        <span className="line-flag" aria-label={`Flagged: ${row.flag}`}>
                          ⚑
                        </span>
                      </Tooltip>
                    )}
                    {line.error && <div className="line-error">{line.error}</div>}
                    {rateWarning(line) && <div className="line-warning">{rateWarning(line)}</div>}
                    {line.override_note && !renderQty && <div className="line-note">{line.override_note}</div>}
                  </Table.Td>
                  <Table.Td>{line.usage}</Table.Td>
                  <Table.Td className="num nowrap">{renderQty ? renderQty(row) : <FrozenQty row={row} />}</Table.Td>
                  <Table.Td>{line.uom}</Table.Td>
                  <Table.Td className="num">{pending ? '…' : fmtNum(line.rate)}</Table.Td>
                  <Table.Td>{!pending && <RateBadge source={line.rate_source} stale={line.rate_stale} date={line.rate_date} />}</Table.Td>
                  <Table.Td className="num">{pending ? '…' : fmtNum(line.wastage_pct)}</Table.Td>
                  <Table.Td className="num">{pending ? '…' : fmtPkr(line.total_with_wastage_pkr)}</Table.Td>
                  <Table.Td>{renderCostHead ? renderCostHead(row) : line.cost_head}</Table.Td>
                  {renderActions && <Table.Td>{renderActions(row)}</Table.Td>}
                </Table.Tr>
              )
            })}
            {footer}
          </Table.Tbody>
        </Table>
      </div>
      <Group justify="flex-end" mt={4}>
        <Switch
          size="xs"
          checked={showZero}
          onChange={(e) => setShowZero(e.currentTarget.checked)}
          disabled={hiddenCount === 0}
          label={<Text size="xs">Show zero-qty lines ({hiddenCount})</Text>}
        />
      </Group>
    </>
  )
}

function FrozenQty({ row }: { row: LineRow }) {
  const { qty_final: qty, qty_auto: auto, qty_formula: formula } = row.line
  const edited = auto !== null && auto !== qty
  return (
    <>
      {fmtNum(qty, 3)}
      {edited && (
        <Tooltip label={`Edited. Formula ${formula ?? ''} gave ${fmtNum(auto, 3)}`} withinPortal>
          <span className="qty-edited" aria-label="Edited quantity">
            ✎
          </span>
        </Tooltip>
      )}
    </>
  )
}
