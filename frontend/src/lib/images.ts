import type { OrderImage } from '../api/types'

const IMAGE_EXT = /\.(png|jpe?g|gif|webp|bmp|avif)$/i
const FILE_EXT = /\.[a-z0-9]{1,5}$/i

const isHttp = (url: string | undefined): url is string => !!url && /^https?:\/\//i.test(url)

function extensionSource(img: OrderImage): string {
  if (img.filename && FILE_EXT.test(img.filename)) return img.filename
  try {
    return new URL(img.url ?? '').pathname
  } catch {
    return ''
  }
}

/** True for attachments a browser can show. Orders list CDR and PDF files too, often first. */
export function isDisplayable(img: OrderImage): boolean {
  if (!isHttp(img.url)) return false
  const source = extensionSource(img)
  if (IMAGE_EXT.test(source)) return true
  if (FILE_EXT.test(source)) return false
  return img.kind !== 'cdr' && img.kind !== 'pdf'
}

export const displayableImages = (images: OrderImage[] | null | undefined) => (images ?? []).filter(isDisplayable)

/** Everything else worth linking to, e.g. the CDR design file. */
export const otherAttachments = (images: OrderImage[] | null | undefined) =>
  (images ?? []).filter((img) => isHttp(img.url) && !isDisplayable(img))
