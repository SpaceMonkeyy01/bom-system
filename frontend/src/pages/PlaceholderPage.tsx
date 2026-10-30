import { Text } from '@mantine/core'
import { PageHeader, Section } from '../components/ui'

const PAGES: Record<string, { title: string; description: string; body: string }> = {
  inventory: {
    title: 'Inventory',
    description: 'Materials, stock from iFlow, rates and suppliers.',
    body: 'Not built yet. Stock uploads, the review queue, rate history and merges are available through the API; the screen is next.',
  },
  sync: {
    title: 'Airtable sync',
    description: 'Orders come in from Airtable; BOM prices go back.',
    body: 'Not built yet. Pulls run every 15 minutes on the server; the CSV upload fallback and the write-back log will be shown here.',
  },
  reports: {
    title: 'Reports',
    description: 'Weekly funds and material totals from saved BOMs.',
    body: 'Not built yet. The weekly-funds and by-material reports exist in the API, including xlsx downloads.',
  },
}

export function PlaceholderPage({ page }: { page: keyof typeof PAGES }) {
  const p = PAGES[page]
  return (
    <>
      <PageHeader title={p.title} description={p.description} />
      <Section>
        <Text size="sm" c="var(--slate)">
          {p.body}
        </Text>
      </Section>
    </>
  )
}
