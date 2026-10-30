import { type KeyboardEvent, useState } from 'react'
import { parseQty, qtyText } from '../lib/bom'

interface Props {
  value: number
  label: string
  edited?: boolean
  onChange: (qty: number) => void
  /** Called when the field is left empty. */
  onClear: () => void
}

/** Enter and the up/down arrows move between rows, so a column of quantities can be typed without the mouse. */
function moveFocus(e: KeyboardEvent<HTMLInputElement>) {
  const step = e.key === 'ArrowUp' ? -1 : e.key === 'ArrowDown' || e.key === 'Enter' ? 1 : 0
  if (!step) return
  e.preventDefault()
  const inputs = Array.from(document.querySelectorAll<HTMLInputElement>('input[data-qty-input]'))
  inputs[inputs.indexOf(e.currentTarget) + step]?.focus()
}

export function QtyInput({ value, label, edited, onChange, onClear }: Props) {
  // What's being typed. Only while focused; otherwise the field shows the computed value.
  const [draft, setDraft] = useState<string | null>(null)
  const invalid = draft !== null && draft.trim() !== '' && parseQty(draft) === null

  return (
    <input
      className={`qty-input${edited ? ' qty-input-edited' : ''}${invalid ? ' qty-input-invalid' : ''}`}
      data-qty-input
      inputMode="decimal"
      aria-label={label}
      aria-invalid={invalid}
      value={draft ?? qtyText(value)}
      onFocus={(e) => e.currentTarget.select()}
      onChange={(e) => {
        const text = e.currentTarget.value
        setDraft(text)
        const qty = parseQty(text)
        if (qty !== null) onChange(qty)
      }}
      onBlur={() => {
        // An emptied field only counts once they leave it: clearing it to retype mustn't reset the line.
        if (draft !== null && draft.trim() === '') onClear()
        setDraft(null)
      }}
      onKeyDown={moveFocus}
    />
  )
}
