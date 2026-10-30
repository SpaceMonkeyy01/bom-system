import { useState } from 'react'
import type { OrderImage } from '../api/types'
import { displayableImages } from '../lib/images'

/** First displayable image of an order, or a placeholder when there is none or it fails to load. */
export function OrderThumb({ images, size = 36 }: { images: OrderImage[]; size?: number }) {
  const image = displayableImages(images)[0]
  const [failedUrl, setFailedUrl] = useState<string | null>(null)
  const style = { width: size, height: size }

  if (!image || failedUrl === image.url) return <div className="thumb thumb-empty" style={style} aria-label="No image" />
  return (
    <img
      className="thumb"
      style={style}
      src={image.url}
      alt={image.filename ?? ''}
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setFailedUrl(image.url ?? null)}
    />
  )
}
