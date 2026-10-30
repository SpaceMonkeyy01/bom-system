import { Badge, Tooltip } from '@mantine/core'
import { fmtDate } from '../lib/format'

function sourceColor(source: string): string {
  if (source === 'bom') return 'blue'
  if (source.startsWith('iflow')) return 'teal'
  if (source.startsWith('supplier')) return 'violet'
  if (source === 'manual') return 'orange'
  return 'gray'
}

export function RateBadge({ source, stale, date }: { source: string | null; stale: boolean; date: string | null }) {
  if (!source) return null
  // "none" also comes back with stale=true, but the problem is the missing rate, not its age
  if (source === 'none') {
    return (
      <Badge size="xs" color="red" variant="filled">
        no rate
      </Badge>
    )
  }
  return (
    <span className="nowrap">
      <Tooltip label={date ? `Rate from ${fmtDate(date)}` : source} withinPortal>
        <Badge size="xs" color={sourceColor(source)} variant="light" tt="none" maw={130}>
          {source}
        </Badge>
      </Tooltip>
      {stale && (
        <Badge ml={3} size="xs" color="orange" variant="filled" tt="none">
          stale
        </Badge>
      )}
    </span>
  )
}
