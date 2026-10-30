import { Anchor, Badge, Group, Paper, Stack, Text } from '@mantine/core'
import { useState } from 'react'
import type { Order, OrderImage } from '../api/types'
import { fmtDate, fmtSize, isOverdue } from '../lib/format'
import { displayableImages, otherAttachments } from '../lib/images'

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="fact">
      <Text span size="xs" c="dimmed">
        {label}
      </Text>
      <Text span size="xs" fw={500}>
        {children ?? '—'}
      </Text>
    </div>
  )
}

function FactImage({ image }: { image: OrderImage }) {
  const [failed, setFailed] = useState(false)
  return (
    <a href={image.url} target="_blank" rel="noreferrer" title={image.filename}>
      {failed ? (
        <span className="fact-image fact-image-broken">{image.filename ?? 'Image'}</span>
      ) : (
        <img className="fact-image" src={image.url} alt={image.filename ?? ''} loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)} />
      )}
    </a>
  )
}

export function OrderFacts({ order }: { order: Order }) {
  const images = displayableImages(order.images)
  const files = otherAttachments(order.images)
  const overdue = isOverdue(order.dispatch_by)

  return (
    <Paper withBorder p="xs">
      <Stack gap={4}>
        <Group justify="space-between" wrap="nowrap">
          <Text fw={700} size="sm">
            {order.code}
          </Text>
          {order.status && (
            <Badge size="xs" variant="light" color="gray" tt="none" maw={150}>
              {order.status}
            </Badge>
          )}
        </Group>
        <Fact label="Account">{[order.account_name, order.country].filter(Boolean).join(', ') || null}</Fact>
        <Fact label="Sign type">
          {order.sign_type_raw ?? order.sign_type_name}
          {order.sign_type_id === null && (
            <Badge ml={4} size="xs" color="red" variant="light">
              Unmapped
            </Badge>
          )}
        </Fact>
        {order.sign_type_name && order.sign_type_name !== order.sign_type_raw && <Fact label="Mapped to">{order.sign_type_name}</Fact>}
        <Fact label="Size (W × H in)">{fmtSize(order.width_in, order.height_in)}</Fact>
        <Fact label="Finish">{order.finish}</Fact>
        <Fact label="LED">{order.led_color}</Fact>
        <Fact label="Usage">{order.usage}</Fact>
        <Fact label="Dispatch by">
          <Text span size="xs" fw={overdue ? 700 : 500} c={overdue ? 'red' : undefined}>
            {fmtDate(order.dispatch_by)}
          </Text>
        </Fact>
        {order.special_notes && (
          <div className="fact-notes">
            <Text size="xs" c="dimmed">
              Notes
            </Text>
            <Text size="xs" style={{ whiteSpace: 'pre-wrap' }}>
              {order.special_notes}
            </Text>
          </div>
        )}
        {images.length > 0 && (
          <Group gap={4} mt={2}>
            {images.map((image) => (
              <FactImage key={image.url} image={image} />
            ))}
          </Group>
        )}
        {files.length > 0 && (
          <Group gap={8}>
            {files.map((file) => (
              <Anchor key={file.url} href={file.url} target="_blank" rel="noreferrer" size="xs">
                {file.filename ?? file.kind ?? 'File'}
              </Anchor>
            ))}
          </Group>
        )}
      </Stack>
    </Paper>
  )
}
