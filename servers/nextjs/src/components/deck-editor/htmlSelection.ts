/** Shared helpers for HTML deck selection / layers. */

export function ensureSunId(el: HTMLElement, counter: { n: number }): string {
  const existing = el.dataset.sunId?.trim()
  if (existing) return existing
  counter.n += 1
  const id = `sun-${counter.n}`
  el.dataset.sunId = id
  return id
}

function labelText(el: HTMLElement): string {
  return (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim()
}

function shapeLabel(el: HTMLElement): string | null {
  const tag = el.tagName
  if (tag === 'HR') return 'Line'
  if (tag !== 'DIV' && tag !== 'SPAN') return null
  const text = labelText(el)
  if (text.length > 8) return null
  const styleAttr = el.getAttribute('style') || ''
  const w = parseFloat(/width\s*:\s*([\d.]+)px/i.exec(styleAttr)?.[1] || '') || el.offsetWidth || 0
  const h = parseFloat(/height\s*:\s*([\d.]+)px/i.exec(styleAttr)?.[1] || '') || el.offsetHeight || 0
  const radius50 = /border-radius\s*:\s*50%/i.test(styleAttr)
  const radiusPx = parseFloat(/border-radius\s*:\s*([\d.]+)px/i.exec(styleAttr)?.[1] || '') || 0
  const hasBg = /background(?:-color)?\s*:/i.test(styleAttr)
  if (!hasBg) return null
  if (radius50 || (Math.min(w, h) > 0 && radiusPx >= Math.min(w, h) * 0.35)) {
    return text ? `Icon · ${text}` : 'Circle'
  }
  if ((h > 0 && h <= 14 && w >= 6) || (w > 0 && w <= 14 && h >= 6)) return 'Line'
  if (el.children.length === 0 && hasBg) return 'Shape'
  return null
}

export function layerLabel(el: HTMLElement): string {
  const pptx = el.getAttribute('data-pptx')
  if (pptx) {
    const aria = el.getAttribute('aria-label')?.trim()
    if (aria) return `${pptx}: ${aria.slice(0, 36)}`
    return pptx.charAt(0).toUpperCase() + pptx.slice(1)
  }
  if (el.hasAttribute('data-sunairum-claim')) {
    const text = labelText(el)
    return text ? `Claim · ${text.slice(0, 32)}` : 'Claim'
  }
  if (el.hasAttribute('data-sunairum-table-chrome')) return 'Table chrome'
  const shape = shapeLabel(el)
  if (shape) return shape
  const tag = el.tagName.toLowerCase()
  if (tag === 'table') return 'Table'
  if (tag === 'td' || tag === 'th') {
    const text = labelText(el)
    return text ? `${tag.toUpperCase()} · ${text.slice(0, 28)}` : tag.toUpperCase()
  }
  const text = labelText(el)
  if (text) return text.slice(0, 42)
  if (el.dataset.sunInsert) return `Insert · ${el.dataset.sunInsert}`
  if (el.tagName === 'IMG') return 'Image'
  return tag
}

export function parsePx(value: string | null | undefined, fallback = 0): number {
  if (!value) return fallback
  const n = parseFloat(value)
  return Number.isFinite(n) ? n : fallback
}
