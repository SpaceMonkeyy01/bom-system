import { Group, Select, Text } from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import type { MaterialSearchResult } from '../api/types'
import { fmtNum } from '../lib/format'

interface Props {
  materialId: number | null
  /** Shown when nothing is being searched; the import keeps the sheet's name even when no material matched. */
  materialName: string | null
  onChange: (material: MaterialSearchResult | null) => void
  disabled?: boolean
  label?: string
}

/** Inline material search for a table row. Only queries once opened, since a template has ~35 of these. */
export function MaterialPicker({ materialId, materialName, onChange, disabled, label }: Props) {
  const [search, setSearch] = useState('')
  const [open, setOpen] = useState(false)
  const [q] = useDebouncedValue(search.trim(), 250)
  const results = useQuery({
    queryKey: ['materials', q],
    queryFn: ({ signal }) => api<MaterialSearchResult[]>('/materials', { query: { q, limit: 30 }, signal }),
    enabled: open,
    placeholderData: keepPreviousData,
  })
  const byId = new Map((results.data ?? []).map((m) => [String(m.id), m]))
  const current = materialId === null ? null : String(materialId)
  // The import writes "(no material)" as the hint when the sheet row had none; that isn't a name worth repeating.
  const hint = materialName && !/^\(no material\)/i.test(materialName) ? materialName : null
  // The current material may not be in the search results, but the Select still needs an option for it.
  const data = [...(results.data ?? []).map((m) => ({ value: String(m.id), label: m.name }))]
  if (current && !byId.has(current)) data.unshift({ value: current, label: hint ?? `#${materialId}` })

  return (
    <Select
      size="xs"
      className={`compact-select material-picker${materialId === null ? ' material-picker-empty' : ''}`}
      aria-label={label ?? 'Material'}
      placeholder={hint ? `${hint} (not matched)` : 'Choose a material'}
      title={hint ? `The sheet called this “${hint}” but no material matched` : undefined}
      searchable
      clearable
      disabled={disabled}
      value={current}
      searchValue={search}
      onSearchChange={setSearch}
      onDropdownOpen={() => setOpen(true)}
      onDropdownClose={() => setOpen(false)}
      data={data}
      filter={({ options }) => options}
      nothingFoundMessage={results.isFetching ? 'Searching…' : 'No materials found'}
      renderOption={({ option }) => {
        const m = byId.get(option.value)
        return (
          <Group justify="space-between" wrap="nowrap" w="100%" gap="xs">
            <Text size="xs">{option.label}</Text>
            {m && (
              <Text size="xs" c={m.rate == null ? 'red' : 'dimmed'} className="nowrap">
                {m.rate == null ? 'no rate' : `${fmtNum(m.rate)} / ${m.rate_uom ?? m.uom ?? '?'}`}
                {m.cost_tag ? ` · ${m.cost_tag}` : ''}
              </Text>
            )}
          </Group>
        )
      }}
      onChange={(value) => {
        onChange(value ? (byId.get(value) ?? null) : null)
        setSearch('')
      }}
    />
  )
}
