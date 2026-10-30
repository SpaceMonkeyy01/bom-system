import { Group, Select, Text } from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import type { MaterialSearchResult } from '../api/types'
import { fmtNum } from '../lib/format'

export function AddMaterial({ onAdd }: { onAdd: (material: MaterialSearchResult) => void }) {
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

  return (
    <Select
      size="xs"
      w={380}
      aria-label="Add material"
      placeholder="+ Add material: search by name"
      searchable
      value={null}
      searchValue={search}
      onSearchChange={setSearch}
      onDropdownOpen={() => setOpen(true)}
      onDropdownClose={() => setOpen(false)}
      data={(results.data ?? []).map((m) => ({ value: String(m.id), label: m.name }))}
      filter={({ options }) => options} // the API has already searched
      nothingFoundMessage={results.isFetching ? 'Searching…' : 'No materials found'}
      renderOption={({ option }) => {
        const material = byId.get(option.value)
        return (
          <Group justify="space-between" wrap="nowrap" w="100%" gap="xs">
            <Text size="xs">{option.label}</Text>
            <Text size="xs" c={material?.rate == null ? 'red' : 'dimmed'} className="nowrap">
              {material?.rate == null ? 'no rate' : `${fmtNum(material.rate)} / ${material.rate_uom ?? material.uom ?? '?'}`}
            </Text>
          </Group>
        )
      }}
      onChange={(value) => {
        const material = value ? byId.get(value) : undefined
        if (material) onAdd(material)
        setSearch('')
      }}
    />
  )
}
