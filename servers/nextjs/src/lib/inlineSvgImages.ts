import { apiFetch } from '@/lib/api'

/**
 * Auth-gated /api/files/... image URLs do not load inside SVG <image> tags
 * (subresource fetch often omits session cookies / fails silently → "?" glyph).
 * Fetch with credentials and embed as data URLs for reliable preview/editor paint.
 * Kept for legacy SVG slide responses; PNG previews use <img> instead.
 */
export async function inlineAuthenticatedSvgImages(
  svg: string,
  imageBaseUrl?: string,
): Promise<string> {
  if (!svg) return svg
  let out = svg
  const base = (imageBaseUrl || '').replace(/\/$/, '')

  if (base) {
    out = out
      .replace(/href="\.\.\/images\//g, `href="${base}/`)
      .replace(/xlink:href="\.\.\/images\//g, `xlink:href="${base}/`)
      .replace(/href="images\//g, `href="${base}/`)
      .replace(/xlink:href="images\//g, `xlink:href="${base}/`)
  }

  const urls = new Set<string>()
  const re =
    /(?:href|xlink:href)="((?:\/api\/files\/[^"]+\/images\/|https?:\/\/[^"]+\/api\/files\/[^"]+\/images\/)[^"?#]+)"/gi
  for (const match of out.matchAll(re)) {
    if (match[1] && !match[1].startsWith('data:')) urls.add(match[1])
  }
  if (urls.size === 0) return out

  const embedded = new Map<string, string>()
  await Promise.all(
    [...urls].map(async (href) => {
      try {
        const path = href.startsWith('http') ? new URL(href).pathname : href
        const res = await apiFetch(path)
        if (!res.ok) return
        const blob = await res.blob()
        const dataUrl = await blobToDataUrl(blob)
        if (dataUrl) embedded.set(href, dataUrl)
      } catch {
        /* leave broken href; caller still shows the rest of the slide */
      }
    }),
  )

  for (const [href, dataUrl] of embedded) {
    const esc = href.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const file = decodeURIComponent(href.split('/images/').pop() || '')
    const original = file ? `../images/${file}` : ''
    if (original) {
      out = out.replace(
        new RegExp(`(<image\\b)(?![^>]*data-edit-original-href=)([^>]*?(?:href|xlink:href)="${esc}"[^>]*>)`, 'gi'),
        `$1 data-edit-original-href="${original}"$2`,
      )
    }
    out = out.replace(new RegExp(`(href|xlink:href)="${esc}"`, 'g'), `href="${dataUrl}"`)
  }
  return out
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(reader.error || new Error('read failed'))
    reader.readAsDataURL(blob)
  })
}

/**
 * Build …/images base from a slide preview URL.
 * Accepts legacy svg_output/ plus preview/ and html_output/ paths.
 */
export function imagesBaseFromSlideUrl(slideUrl: string, apiUrl = ''): string {
  const path = slideUrl.split('?')[0] || ''
  const files = path.match(
    /^\/api\/files\/([^/]+\/[^/]+)\/(?:svg_output|preview|html_output)\//,
  )
  if (files) return `${apiUrl}/api/files/${files[1]}/images`
  const storage = path.match(/^\/storage\/(.*?)\/(?:svg_output|preview|html_output)\//)
  if (storage) return `${apiUrl}/storage/${storage[1]}/images`
  return ''
}
