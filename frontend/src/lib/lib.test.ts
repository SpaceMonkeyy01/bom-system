import { describe, expect, it } from 'vitest'
import { fmtDate, fmtNum, fmtPkr, fmtSize, fmtUsd, isOverdue } from './format'
import { displayableImages, isDisplayable, otherAttachments } from './images'

describe('format', () => {
  it('formats ISO dates without a timezone shift', () => {
    expect(fmtDate('2026-11-01')).toBe('1 Nov 2026')
    expect(fmtDate('2026-11-01T23:30:00+00:00')).toBe('1 Nov 2026')
    expect(fmtDate(null)).toBe('—')
  })

  it('treats only dates before today as overdue', () => {
    const today = new Date(2026, 9, 30)
    expect(isOverdue('2026-10-29', today)).toBe(true)
    expect(isOverdue('2026-10-30', today)).toBe(false)
    expect(isOverdue('2026-11-01', today)).toBe(false)
    expect(isOverdue(null, today)).toBe(false)
  })

  it('formats numbers and shows a dash for nothing, but keeps zero', () => {
    expect(fmtNum(1234.5678)).toBe('1,234.57')
    expect(fmtNum(0)).toBe('0')
    expect(fmtNum(null)).toBe('—')
    expect(fmtPkr(20733.9)).toBe('20,734')
    expect(fmtUsd(92.1)).toBe('$92.10')
    expect(fmtUsd(0)).toBe('$0.00')
    expect(fmtUsd(null)).toBe('—')
  })

  it('formats a size only when both sides are known', () => {
    expect(fmtSize(48, 24.5)).toBe('48 × 24.5')
    expect(fmtSize(48, null)).toBe('—')
  })
})

describe('images', () => {
  const cdr = { kind: 'cdr', filename: 'art.cdr', url: 'https://x.test/a' }
  const pdf = { kind: 'pdf', filename: 'spec.pdf', url: 'https://x.test/b' }
  const png = { kind: 'design', filename: 'face.PNG', url: 'https://x.test/c' }

  it('skips CDR and PDF files to find the first real image, keeping its position for the API', () => {
    expect(displayableImages([cdr, pdf, png])[0]).toEqual({ ...png, index: 2 })
    expect(otherAttachments([cdr, pdf, png])).toEqual([
      { ...cdr, index: 0 },
      { ...pdf, index: 1 },
    ])
  })

  it('recognises the image types real orders use, but not videos', () => {
    for (const filename of ['a.jfif', 'a.svg', 'a.avif', 'a.webp', 'a.jpeg']) {
      expect(isDisplayable({ kind: 'photo', filename, url: 'https://x.test/a' })).toBe(true)
    }
    expect(isDisplayable({ kind: 'photo', filename: 'clip.mp4', url: 'https://x.test/a' })).toBe(false)
  })

  it('goes by the file type even if the kind says design', () => {
    expect(isDisplayable({ kind: 'design', filename: 'art.cdr', url: 'https://x.test/a' })).toBe(false)
  })

  it('falls back to the URL path, then the kind, when the name has no extension', () => {
    expect(isDisplayable({ kind: 'cdr', filename: 'artwork', url: 'https://x.test/a.png' })).toBe(true)
    expect(isDisplayable({ kind: 'photo', filename: 'IMG', url: 'https://x.test/abc' })).toBe(true)
    expect(isDisplayable({ kind: 'cdr', filename: 'art', url: 'https://x.test/abc' })).toBe(false)
  })

  it('never treats a non-http URL as usable', () => {
    const bad = { kind: 'design', filename: 'x.png', url: 'javascript:alert(1)' }
    expect(isDisplayable(bad)).toBe(false)
    expect(otherAttachments([bad])).toEqual([])
  })

  it('handles missing data', () => {
    expect(displayableImages(null)).toEqual([])
    expect(displayableImages([{}])).toEqual([])
  })
})
