import { Anchor, Text } from '@mantine/core'
import { useState } from 'react'
import { apiBlob, errorMessage } from '../api/client'
import type { Order } from '../api/types'
import { type Attachment, displayableImages, otherAttachments } from '../lib/images'
import { orderImagePath, useOrderImage } from '../lib/useOrderImage'

// Orders carry about 22 attachments, mostly production photos; three tiles and a "+N" keep the page short.
const SHOWN_FIRST = 2

function Tile({ orderId, image, onOpen }: { orderId: number; image: Attachment; onOpen: (image: Attachment) => void }) {
  const { url, failed, markFailed } = useOrderImage(orderId, image.index)
  if (failed) {
    return (
      <span className="fact-image-broken" title={`${image.filename ?? 'Image'} isn’t available`}>
        {image.filename ?? 'Image'}
      </span>
    )
  }
  return (
    <button type="button" className="fact-image-button" title={image.filename} aria-label={image.filename ?? 'Image'} onClick={() => onOpen(image)}>
      {url && <img className="fact-image" src={url} alt={image.filename ?? ''} onError={markFailed} />}
    </button>
  )
}

/** The order's images as a small grid with a "+N" tile, and its other files as downloads once expanded. */
export function OrderAttachments({ order }: { order: Order }) {
  const [showAll, setShowAll] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const images = displayableImages(order.images)
  const files = otherAttachments(order.images)
  const total = images.length + files.length
  const shown = showAll ? images : images.slice(0, SHOWN_FIRST)
  const more = total - shown.length

  // Opened from a click so the browser allows the new tab, then pointed at the image once it has loaded.
  async function openImage(image: Attachment) {
    setError(null)
    const tab = window.open('', '_blank')
    try {
      const blob = await apiBlob(orderImagePath(order.id, image.index))
      const url = URL.createObjectURL(blob)
      if (tab) tab.location.href = url
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch (err) {
      tab?.close()
      setError(errorMessage(err))
    }
  }

  async function downloadFile(file: Attachment) {
    setError(null)
    try {
      const blob = await apiBlob(orderImagePath(order.id, file.index))
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = file.filename ?? 'attachment'
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  if (total === 0) return <span className="caption">No attachments</span>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <span className="caption body-strong">
        {total} attachment{total === 1 ? '' : 's'}
      </span>
      <div className="attachments">
        {shown.map((image) => (
          <Tile key={image.index} orderId={order.id} image={image} onOpen={openImage} />
        ))}
        {!showAll && more > 0 && (
          <button type="button" className="fact-image-button attachments-more" aria-label={`Show all ${total} attachments`} onClick={() => setShowAll(true)}>
            +{more}
          </button>
        )}
      </div>
      {showAll && files.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
          {files.map((file) => (
            <Anchor key={file.index} component="button" type="button" size="xs" onClick={() => downloadFile(file)}>
              {file.filename ?? file.kind ?? 'File'}
            </Anchor>
          ))}
        </div>
      )}
      {showAll && total > SHOWN_FIRST && (
        <button type="button" className="link-button caption" style={{ alignSelf: 'flex-start' }} onClick={() => setShowAll(false)}>
          Show fewer
        </button>
      )}
      {error && (
        <Text size="xs" c="var(--missing)" role="alert">
          {error}
        </Text>
      )}
    </div>
  )
}
