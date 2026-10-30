import { useInViewport } from '@mantine/hooks'
import { useEffect, useState } from 'react'
import type { OrderImage } from '../api/types'
import { displayableImages } from '../lib/images'
import { useOrderImage } from '../lib/useOrderImage'

/** First displayable image of an order, or a placeholder when there is none or it fails to load. */
export function OrderThumb({ orderId, images, size = 28 }: { orderId: number; images: OrderImage[]; size?: number }) {
  const image = displayableImages(images)[0]
  const { ref, inViewport } = useInViewport()
  const [seen, setSeen] = useState(false)
  useEffect(() => {
    if (inViewport) setSeen(true)
  }, [inViewport])

  // Only fetch rows that have been on screen: the queue can hold hundreds of orders.
  const { url, failed, markFailed } = useOrderImage(orderId, image?.index ?? 0, !!image && seen)
  const style = { width: size, height: size }

  if (!image || failed) return <div className="thumb thumb-empty" style={style} aria-label="No image" />
  if (!url) return <div ref={ref} className="thumb thumb-empty" style={style} aria-label="Loading image" />
  return <img className="thumb" style={style} src={url} alt={image.filename ?? ''} onError={markFailed} />
}
