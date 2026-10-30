import { Group, Text } from '@mantine/core'
import { ORDER_PARAMS } from '../../lib/templates'

interface Props {
  paramNames: string[]
  costTags: string[]
  /** Whether a formula field is focused; chips do nothing otherwise, so they're shown dimmed. */
  active: boolean
  onInsert: (text: string) => void
}

function Chip({ text, title, kind, onInsert }: { text: string; title?: string; kind: 'param' | 'order' | 'fn'; onInsert: (t: string) => void }) {
  return (
    <button
      type="button"
      className={`chip chip-${kind}`}
      title={title ?? `Insert ${text}`}
      // mousedown, not click, so the formula field keeps focus and its caret
      onMouseDown={(e) => {
        e.preventDefault()
        onInsert(text)
      }}
    >
      {text}
    </button>
  )
}

/** Click-to-insert tokens for the focused formula: inputs, the order's size, and QTY()/COST() over the cost tags in use. */
export function FormulaChips({ paramNames, costTags, active, onInsert }: Props) {
  return (
    <div className={`chips${active ? '' : ' chips-idle'}`} aria-label="Formula tokens">
      <Group gap={4} wrap="wrap">
        <Text size="xs" c="dimmed" className="nowrap">
          {active ? 'Insert:' : 'Click a formula, then insert:'}
        </Text>
        {paramNames.map((n) => (
          <Chip key={n} text={n} kind="param" onInsert={onInsert} />
        ))}
        {ORDER_PARAMS.map((n) => (
          <Chip key={n} text={n} kind="order" title={`${n} comes from the order`} onInsert={onInsert} />
        ))}
        {costTags.map((t) => (
          <Chip key={`q-${t}`} text={`QTY("${t}")`} kind="fn" title={`Total quantity of every ${t} line`} onInsert={onInsert} />
        ))}
        {costTags.map((t) => (
          <Chip key={`c-${t}`} text={`COST("${t}")`} kind="fn" title={`Total cost of the other ${t} lines`} onInsert={onInsert} />
        ))}
      </Group>
    </div>
  )
}
