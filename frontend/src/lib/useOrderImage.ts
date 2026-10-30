import { useEffect, useState } from 'react'
import { apiBlob } from '../api/client'

export const orderImagePath = (orderId: number, index: number) => `/orders/${orderId}/images/${index}`

/**
 * Loads an order attachment through the API, which needs the token and refreshes expired Airtable links, and gives
 * back a URL an <img> can use. Each call can make the backend go to Airtable, so nothing loads until `enabled`.
 */
export function useOrderImage(orderId: number, index: number, enabled = true) {
  const [url, setUrl] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!enabled) return
    const controller = new AbortController()
    let objectUrl: string | null = null
    apiBlob(orderImagePath(orderId, index), { query: { thumb: true }, signal: controller.signal })
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true)
      })
    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [orderId, index, enabled])

  return { url, failed, markFailed: () => setFailed(true) }
}
