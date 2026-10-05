/** Layout-independent layer collection (works on DOMParser docs + live iframes). */

import type { HtmlLayerItem } from './types'
import { ensureSunId, layerLabel } from './htmlSelection'

function visibleText(el: HTMLElement): string {
  return (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim()
}

function findSlideRoot(doc: Document): HTMLElement {
  return (
    (doc.querySelector('.slide') as HTMLElement | null) ||
    (doc.querySelector('section') as HTMLElement | null) ||
    doc.body
  )
}

function isEditorChrome(el: HTMLElement): boolean {
  return (
    el.classList.contains('__sun-resize') ||
    el.classList.contains('__sun-rotate') ||
    el.classList.contains('__sun-rotate-stem') ||
    el.dataset.sunChrome === '1' ||
    el.id === '__sun-editor-style'
  )
}

function isSlideShell(el: HTMLElement, root: HTMLElement): boolean {
  if (el === root) return true
  if (el === el.ownerDocument?.body || el === el.ownerDocument?.documentElement) return true
  if (el.classList.contains('slide')) return true
  const tag = el.tagName
  return tag === 'HTML' || tag === 'BODY' || tag === 'SCRIPT' || tag === 'STYLE' || tag === 'HEAD'
}

function isTableNoise(el: HTMLElement): boolean {
  const tag = el.tagName
  return (
    tag === 'THEAD' ||
    tag === 'TBODY' ||
    tag === 'TFOOT' ||
    tag === 'TR' ||
    tag === 'COLGROUP' ||
    tag === 'COL'
  )
}

/** Attribute / structure heuristics — no getComputedStyle required. */
function isLayerCandidate(el: HTMLElement, root: HTMLElement): boolean {
  if (isSlideShell(el, root) || isEditorChrome(el)) return false
  if (el.hasAttribute('data-sunairum-page-number')) return false
  const tag = el.tagName
  if (
    tag === 'SCRIPT' ||
    tag === 'STYLE' ||
    tag === 'BR' ||
    tag === 'WBR' ||
    tag === 'NOSCRIPT' ||
    tag === 'META' ||
    tag === 'LINK'
  ) {
    return false
  }
  if (isTableNoise(el)) return false
  if (tag === 'TABLE' || tag === 'TD' || tag === 'TH' || tag === 'CAPTION') return true
  if (el.hasAttribute('data-pptx') || el.hasAttribute('data-sunairum-claim')) return true
  if (el.hasAttribute('data-sunairum-table-chrome')) return true
  if (el.dataset.sunId || el.dataset.sunFreeform || el.dataset.sunInsert) return true
  if (tag === 'IMG' || tag === 'SVG' || tag === 'CANVAS' || tag === 'VIDEO') return true
  if (
    tag === 'H1' ||
    tag === 'H2' ||
    tag === 'H3' ||
    tag === 'H4' ||
    tag === 'H5' ||
    tag === 'H6' ||
    tag === 'P' ||
    tag === 'LI' ||
    tag === 'UL' ||
    tag === 'OL' ||
    tag === 'FIGCAPTION' ||
    tag === 'LABEL'
  ) {
    return visibleText(el).length > 0
  }
  if (tag === 'HR') return true
  const styleAttr = el.getAttribute('style') || ''
  const text = visibleText(el)
  // Decorative circles / lines / bars (often empty of copy).
  if (
    (tag === 'DIV' || tag === 'SPAN') &&
    text.length <= 8 &&
    /background(?:-color)?\s*:/i.test(styleAttr)
  ) {
    if (/border-radius\s*:\s*50%/i.test(styleAttr)) return true
    if (/height\s*:\s*([1-9]|1[0-4])px/i.test(styleAttr)) return true
    if (/width\s*:\s*([1-9]|1[0-4])px/i.test(styleAttr) && /height\s*:/i.test(styleAttr)) {
      return true
    }
    if (el.children.length === 0) return true
  }
  if (
    tag === 'DIV' ||
    tag === 'SECTION' ||
    tag === 'ARTICLE' ||
    tag === 'ASIDE' ||
    tag === 'HEADER' ||
    tag === 'FOOTER' ||
    tag === 'SPAN'
  ) {
    if (text.length >= 2) return true
    if (el.querySelector('img, svg, table, canvas, video, [data-pptx], [data-sunairum-claim]')) {
      return true
    }
  }
  if (/\bposition\s*:\s*(absolute|fixed)\b/i.test(styleAttr)) return true
  return false
}

function isPositionedAttr(el: HTMLElement): boolean {
  if (el.dataset.sunFreeform || el.dataset.sunInsert) return true
  const styleAttr = el.getAttribute('style') || ''
  return /\bposition\s*:\s*(absolute|fixed)\b/i.test(styleAttr)
}

export function collectLayersFromDocument(doc: Document): HtmlLayerItem[] {
  if (!doc?.body) return []
  const root = findSlideRoot(doc)
  const items: HtmlLayerItem[] = []
  const counter = { n: 0 }
  const usedIds = new Set<string>()

  // The live editor assigns ids to selectable canvas objects before Layers is
  // collected. Seed the allocator from those ids; otherwise a layer-only
  // container can be assigned an existing id (for example another `sun-1`),
  // breaking the one-to-one canvas <-> layer selection contract.
  root.querySelectorAll<HTMLElement>('[data-sun-id]').forEach((el) => {
    const match = /^sun-(\d+)$/.exec(el.dataset.sunId || '')
    if (!match) return
    const n = Number(match[1])
    if (Number.isFinite(n) && n > counter.n) counter.n = n
  })

  const uniqueLayerId = (el: HTMLElement): string => {
    const existing = el.dataset.sunId?.trim()
    if (existing && !usedIds.has(existing)) {
      usedIds.add(existing)
      return existing
    }
    if (existing) delete el.dataset.sunId
    const id = ensureSunId(el, counter)
    usedIds.add(id)
    return id
  }

  const visit = (el: HTMLElement, parentId: string | null, depth: number) => {
    if (isEditorChrome(el)) return

    let nextParent = parentId
    let nextDepth = depth
    if (isLayerCandidate(el, root)) {
      const id = uniqueLayerId(el)
      const styleAttr = el.getAttribute('style') || ''
      const hidden =
        el.hidden ||
        /\bvisibility\s*:\s*hidden\b/i.test(styleAttr) ||
        /\bdisplay\s*:\s*none\b/i.test(styleAttr)
      const zMatch = /(?:^|;)\s*z-index\s*:\s*(-?\d+)/i.exec(styleAttr)
      items.push({
        id,
        label: layerLabel(el) || visibleText(el).slice(0, 42) || el.tagName.toLowerCase(),
        tag: el.tagName.toLowerCase(),
        positioned: isPositionedAttr(el),
        hidden,
        zIndex: zMatch ? parseInt(zMatch[1], 10) || 0 : 0,
        parentId,
        depth,
      })
      nextParent = id
      nextDepth = depth + 1
    }

    Array.from(el.children).forEach((child) => {
      if (child instanceof HTMLElement) visit(child, nextParent, nextDepth)
    })
  }

  Array.from(root.children).forEach((child) => {
    if (child instanceof HTMLElement) visit(child, null, 0)
  })

  if (items.length === 0) {
    const slide = doc.querySelector('.slide') as HTMLElement | null
    if (slide && slide !== root) {
      Array.from(slide.children).forEach((child) => {
        if (child instanceof HTMLElement) visit(child, null, 0)
      })
    }
  }

  return items
}

/** Parse slide HTML and list layers without waiting on the editor iframe. */
export function collectLayersFromHtml(html: string | null | undefined): HtmlLayerItem[] {
  if (!html || typeof DOMParser === 'undefined') return []
  try {
    const doc = new DOMParser().parseFromString(html, 'text/html')
    return collectLayersFromDocument(doc)
  } catch {
    return []
  }
}
