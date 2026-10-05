'use client'

import { useEffect, useRef, useState } from 'react'
import { apiFetch } from '@/lib/api'
import {
  imagesBaseFromSlideUrl,
  inlineAuthenticatedSvgImages,
} from '@/lib/inlineSvgImages'

/** Prepare fetched SVG markup for inline thumbnail injection. */
export function prepareSvgThumbMarkup(raw: string, svgClassName: string, contain: boolean) {
  if (typeof DOMParser === 'undefined') {
    return raw.replace('<svg', `<svg class="${svgClassName}"`)
  }
  const doc = new DOMParser().parseFromString(raw, 'image/svg+xml')
  const root = doc.documentElement
  if (!root || root.nodeName.toLowerCase() !== 'svg') {
    return raw.replace('<svg', `<svg class="${svgClassName}"`)
  }
  root.setAttribute('class', svgClassName)
  root.setAttribute('preserveAspectRatio', 'xMidYMid meet')
  // Authored slide SVGs carry width="1280"/height="720". Left as attributes they
  // paint at that size for the frames before the route stylesheet attaches, so
  // the thumbnail flashes oversized and then snaps down. Size the root inline.
  root.setAttribute('width', '100%')
  root.setAttribute('height', contain ? '100%' : 'auto')
  const fit = contain
    ? 'width:100%;height:100%;display:block;'
    : 'width:100%;height:auto;max-width:100%;max-height:100%;display:block;'
  root.setAttribute('style', `${fit}${root.getAttribute('style') || ''}`)
  return new XMLSerializer().serializeToString(root)
}

function looksLikeRasterUrl(url: string): boolean {
  const path = (url.split('?')[0] || '').toLowerCase()
  return (
    /\.(png|jpe?g|webp|gif)$/.test(path) ||
    path.includes('/preview/') ||
    /\/api\/templates\/[^/]+\/(cover|slides\/)/.test(path)
  )
}

function ThumbError({ alt, contain }: { alt: string; contain: boolean }) {
  return (
    <div
      role="img"
      aria-label={alt ? `${alt} — failed to load` : 'Preview failed to load'}
      className={contain ? 'slide-lightbox-host' : undefined}
      style={{
        display: 'grid',
        placeItems: 'center',
        width: '100%',
        height: contain ? '100%' : 'auto',
        minHeight: contain ? undefined : 72,
        padding: 12,
        boxSizing: 'border-box',
        borderRadius: 8,
        border: '1px dashed color-mix(in srgb, #ef4444 55%, transparent)',
        background: 'color-mix(in srgb, #ef4444 8%, #111827)',
        color: '#fca5a5',
        fontSize: 12,
        fontWeight: 600,
        letterSpacing: '0.04em',
        textAlign: 'center',
        textTransform: 'uppercase',
      }}
    >
      Preview unavailable
    </div>
  )
}

/**
 * Slide thumbnail: PNG/JPEG (and template covers) render as <img>;
 * legacy SVG responses still inline. Fetch failures show a visible error.
 */
export default function SvgThumb({
  apiUrl,
  url,
  alt,
  svgClassName = 'slide-thumb',
  contain = false,
}: {
  apiUrl: string
  url: string
  alt: string
  svgClassName?: string
  /** Scale media into the wrapper box (lightbox) instead of width-only growth. */
  contain?: boolean
}) {
  const [html, setHtml] = useState('')
  const [rasterSrc, setRasterSrc] = useState('')
  const [error, setError] = useState(false)
  const objectUrlRef = useRef<string | null>(null)

  useEffect(() => {
    let alive = true
    setHtml('')
    setRasterSrc('')
    setError(false)
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current)
      objectUrlRef.current = null
    }
    const load = async () => {
      try {
        // Do not cache-bust rasters — cover/slide endpoints set Cache-Control.
        const res = await apiFetch(url)
        if (!res.ok) throw new Error(String(res.status))
        const contentType = (res.headers.get('content-type') || '').toLowerCase()
        const asRaster =
          looksLikeRasterUrl(url) ||
          (contentType.startsWith('image/') && !contentType.includes('svg'))

        if (asRaster) {
          const blob = await res.blob()
          const objectUrl = URL.createObjectURL(blob)
          if (!alive) {
            URL.revokeObjectURL(objectUrl)
            return
          }
          objectUrlRef.current = objectUrl
          setRasterSrc(objectUrl)
          return
        }

        const raw = await res.text()
        if (!raw.trim()) throw new Error('empty')
        // Only a standalone <svg> may be inlined. A slide's HTML document
        // injected here painted at its native 1280x720 and, worse, published its
        // own stylesheet into the host page. Treat anything else as unavailable.
        if (!/^\s*(?:<\?xml[^>]*\?>\s*)?(?:<!--[\s\S]*?-->\s*)*<svg[\s>]/i.test(raw)) {
          throw new Error('not-svg')
        }
        const base = imagesBaseFromSlideUrl(url, apiUrl)
        const inlined = await inlineAuthenticatedSvgImages(raw, base || undefined)
        if (!alive) return
        setHtml(prepareSvgThumbMarkup(inlined, svgClassName, contain))
      } catch {
        if (alive) setError(true)
      }
    }
    void load()
    return () => {
      alive = false
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current)
        objectUrlRef.current = null
      }
    }
  }, [apiUrl, url, svgClassName, contain])

  if (error) {
    return <ThumbError alt={alt} contain={contain} />
  }

  if (rasterSrc) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={rasterSrc}
        alt={alt}
        className={contain ? 'slide-lightbox-host' : svgClassName}
        style={
          contain
            ? { width: '100%', height: '100%', objectFit: 'contain', display: 'block' }
            : {
                // Previews are rendered at 3.125x device scale (4000x2250), so an
                // image that paints before the route stylesheet is attached lays
                // out about three times too large and the card visibly jumps.
                // Fitting inline keeps the first painted frame the right size.
                width: '100%',
                height: 'auto',
                maxWidth: '100%',
                maxHeight: '100%',
                objectFit: 'contain',
                display: 'block',
              }
        }
        onError={() => setError(true)}
      />
    )
  }

  if (!html) {
    return (
      <div
        aria-hidden="true"
        className={contain ? 'slide-lightbox-host' : undefined}
        style={{
          width: '100%',
          // Reserve the slide's own aspect box rather than a 72px stub: growing
          // from stub height to full height on load is the second half of the
          // "thumbnail jumps" flicker.
          ...(contain ? { height: '100%' } : { aspectRatio: '16 / 9', height: 'auto' }),
          background: 'color-mix(in srgb, var(--card-border, #334155) 35%, transparent)',
          borderRadius: 8,
        }}
      />
    )
  }

  return (
    <div
      role="img"
      aria-label={alt}
      className={contain ? 'slide-lightbox-host' : undefined}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}
