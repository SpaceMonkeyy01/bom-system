import { Anchor, Badge, Button, Group, Paper, Stack, Text } from '@mantine/core'
import { useState } from 'react'
import { apiBlob, errorMessage } from '../api/client'
import type { Order } from '../api/types'
import { fmtDate, fmtSize, isOverdue } from '../lib/format'
import { type Attachment, displayableImages, otherAttachments } from '../lib/images'
import { orderImagePath, useOrderImage } from '../lib/useOrderImage'

// Orders carry about 22 attachments, mostly production photos, which would push the parameter form off the screen.
const IMAGES_SHOWN_FIRST = 3

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

function FactImage({ orderId, image, onOpen }: { orderId: number; image: Attachment; onOpen: (image: Attachment) => void }) {
  const { url, failed, markFailed } = useOrderImage(orderId, image.index)
  if (failed) {
    return (
      <span className="fact-image fact-image-broken" title={`${image.filename ?? 'Image'} isn’t available`}>
        {image.filename ?? 'Image'}
      </span>
    )
  }
  return (
    <button type="button" className="fact-image-button" title={image.filename} onClick={() => onOpen(image)}>
      {url ? <img className="fact-image" src={url} alt={image.filename ?? ''} onError={markFailed} /> : <span className="fact-image fact-image-broken" />}
    </button>
  )
}

export function OrderFacts({ order }: { order: Order }) {
  const [showAll, setShowAll] = useState(false)
  const [fileError, setFileError] = useState<string | null>(null)
  const images = displayableImages(order.images)
  const files = otherAttachments(order.images)
  const total = images.length + files.length
  const overdue = isOverdue(order.dispatch_by)

  // Opened from a click so the browser allows the new tab, then pointed at the image once it has loaded.
  async function openImage(image: Attachment) {
    setFileError(null)
    const tab = window.open('', '_blank')
    try {
      const blob = await apiBlob(orderImagePath(order.id, image.index))
      const url = URL.createObjectURL(blob)
      if (tab) tab.location.href = url
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch (err) {
      tab?.close()
      setFileError(errorMessage(err))
    }
  }

  async function downloadFile(file: Attachment) {
    setFileError(null)
    try {
      const blob = await apiBlob(orderImagePath(order.id, file.index))
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = file.filename ?? 'attachment'
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch (err) {
      setFileError(errorMessage(err))
    }
  }

  const shownImages = showAll ? images : images.slice(0, IMAGES_SHOWN_FIRST)

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
        {shownImages.length > 0 && (
          <Group gap={4} mt={2}>
            {shownImages.map((image) => (
              <FactImage key={image.index} orderId={order.id} image={image} onOpen={openImage} />
            ))}
          </Group>
        )}
        {showAll && files.length > 0 && (
          <Group gap={8}>
            {files.map((file) => (
              <Anchor key={file.index} component="button" type="button" size="xs" onClick={() => downloadFile(file)}>
                {file.filename ?? file.kind ?? 'File'}
              </Anchor>
            ))}
          </Group>
        )}
        {fileError && (
          <Text size="xs" c="red" role="alert">
            {fileError}
          </Text>
        )}
        {total > shownImages.length && !showAll && (
          <Button variant="subtle" size="compact-xs" onClick={() => setShowAll(true)}>
            Show all {total} attachments
          </Button>
        )}
        {showAll && total > IMAGES_SHOWN_FIRST && (
          <Button variant="subtle" size="compact-xs" onClick={() => setShowAll(false)}>
            Show fewer
          </Button>
        )}
      </Stack>
    </Paper>
  )
}
