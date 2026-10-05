'use client'

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type MutableRefObject,
} from 'react'
import { SLIDE_STAGE_H, SLIDE_STAGE_W } from './SlideStage'
import type { InsertKind } from './insertKinds'
import { collectLayersFromDocument } from './htmlLayers'
import { ensureSunId, parsePx } from './htmlSelection'
import type { HtmlLayerItem, HtmlSelection, HtmlStylePatch } from './types'

export type EditableHtmlSlideHandle = {
  getHtml: () => string | null
  setHtml: (html: string) => void
  insertKind: (kind: InsertKind, opts?: { imageUrl?: string }) => boolean
  focus: () => void
  getSelection: () => HtmlSelection | null
  listLayers: () => HtmlLayerItem[]
  selectById: (id: string | null) => boolean
  applyStyle: (patch: HtmlStylePatch) => boolean
  applyText: (text: string) => boolean
  reorderLayer: (id: string, direction: 'up' | 'down' | 'top' | 'bottom') => boolean
  deleteSelection: () => boolean
  startTextEdit: () => boolean
}

type Props = {
  html: string
  title?: string
  width?: number
  height?: number
  onDirty?: (html: string) => void
  onSelectionChange?: (sel: HtmlSelection | null) => void
  /** Fired after the iframe editor is installed / reinstalled (layers ready). */
  onReady?: () => void
  /** When false, drag/resize/insert-oriented gestures are limited (Refine mode). */
  editMode?: boolean
}

const EDITOR_STYLE = `
.__sun-sel {
  outline: 2px solid #3182CE !important;
  outline-offset: 2px;
  cursor: move;
}
.__sun-sel[data-sun-flow="1"] {
  cursor: move;
}
.__sun-edit {
  outline: 2px solid #DD6B20 !important;
  outline-offset: 2px;
  cursor: text !important;
}
.__sun-resize {
  position: absolute;
  width: 10px;
  height: 10px;
  margin: -5px 0 0 -5px;
  border-radius: 50%;
  background: #fff;
  border: 1.5px solid #3182CE;
  box-sizing: border-box;
  z-index: 10000;
  pointer-events: auto;
  touch-action: none;
}
.__sun-resize[data-h="nw"] { cursor: nwse-resize; }
.__sun-resize[data-h="n"] { cursor: ns-resize; }
.__sun-resize[data-h="ne"] { cursor: nesw-resize; }
.__sun-resize[data-h="e"] { cursor: ew-resize; }
.__sun-resize[data-h="se"] { cursor: nwse-resize; }
.__sun-resize[data-h="s"] { cursor: ns-resize; }
.__sun-resize[data-h="sw"] { cursor: nesw-resize; }
.__sun-resize[data-h="w"] { cursor: ew-resize; }
.__sun-rotate-stem {
  position: absolute;
  width: 1.5px;
  height: 22px;
  margin-left: -0.75px;
  background: #3182CE;
  z-index: 10001;
  pointer-events: none;
}
.__sun-rotate {
  position: absolute;
  width: 14px;
  height: 14px;
  margin: -7px 0 0 -7px;
  border-radius: 50%;
  background: #3182CE;
  border: 2px solid #fff;
  box-shadow: 0 1px 4px rgba(0,0,0,.35);
  /* Circular-arrow cursor (no standard CSS "rotate" keyword). */
  cursor: url("data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'%3E%3Cpath fill='none' stroke='%231A202C' stroke-width='2' stroke-linecap='round' d='M7.5 5.2A8 8 0 1 1 4.2 12'/%3E%3Cpath fill='%231A202C' d='M7.2 2.4l.4 4.6 3.8-2.6z'/%3E%3C/svg%3E") 12 12, crosshair;
  z-index: 10002;
  pointer-events: auto;
  touch-action: none;
  box-sizing: border-box;
}
.__sun-rotate:active {
  cursor: url("data:image/svg+xml;utf8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'%3E%3Cpath fill='none' stroke='%231A202C' stroke-width='2' stroke-linecap='round' d='M7.5 5.2A8 8 0 1 1 4.2 12'/%3E%3Cpath fill='%231A202C' d='M7.2 2.4l.4 4.6 3.8-2.6z'/%3E%3C/svg%3E") 12 12, crosshair;
}
html, body { cursor: default; }
body[data-sun-edit-chrome="1"] { user-select: none !important; -webkit-user-select: none !important; }
body[data-sun-edit-chrome="1"] * { user-select: none !important; -webkit-user-select: none !important; }
body[data-sun-edit-chrome="1"] .__sun-edit,
body[data-sun-edit-chrome="1"] .__sun-edit * { user-select: text !important; -webkit-user-select: text !important; }
`

const TEXT_TAGS = new Set([
  'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'P', 'LI', 'SPAN', 'LABEL',
  'TD', 'TH', 'FIGCAPTION', 'A', 'STRONG', 'EM', 'B', 'I', 'SMALL', 'BUTTON',
])

const RESIZE_HANDLES = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'] as const
type ResizeHandle = (typeof RESIZE_HANDLES)[number]

function findSlideRoot(doc: Document): HTMLElement {
  return (
    (doc.querySelector('.slide') as HTMLElement | null) ||
    (doc.querySelector('section') as HTMLElement | null) ||
    doc.body
  )
}

function isSlideChrome(el: HTMLElement): boolean {
  if (!el) return true
  if (el === el.ownerDocument?.body || el === el.ownerDocument?.documentElement) return true
  if (el.classList?.contains('slide')) return true
  if (el.classList?.contains('__sun-resize')) return true
  const tag = el.tagName
  return tag === 'HTML' || tag === 'BODY' || tag === 'SCRIPT' || tag === 'STYLE' || tag === 'HEAD'
}

function isPositioned(el: HTMLElement, doc: Document): boolean {
  if (el.dataset?.sunInsert || el.dataset?.sunFreeform) return true
  const style = doc.defaultView?.getComputedStyle(el)
  if (!style) return false
  return style.position === 'absolute' || style.position === 'fixed'
}

function isFullSlideWrapper(el: HTMLElement, doc: Document): boolean {
  const root = findSlideRoot(doc)
  if (el === root) return true
  // Before layout, offset*/client* can be 0 — never treat that as "full slide"
  // (0 >= 0 would mark every node and empty the layers list).
  const rw = root.clientWidth
  const rh = root.clientHeight
  const w = el.offsetWidth
  const h = el.offsetHeight
  if (rw < 32 || rh < 32 || w < 8 || h < 8) return false
  return w >= rw * 0.92 && h >= rh * 0.85
}

function isTableChrome(el: HTMLElement): boolean {
  return (
    el.hasAttribute('data-sunairum-table-chrome') ||
    el.hasAttribute('data-sunairum-table-preview') ||
    el.tagName === 'TABLE' ||
    el.tagName === 'THEAD' ||
    el.tagName === 'TBODY' ||
    el.tagName === 'TFOOT' ||
    el.tagName === 'TR' ||
    el.tagName === 'TD' ||
    el.tagName === 'TH' ||
    el.tagName === 'COLGROUP' ||
    el.tagName === 'COL'
  )
}

function closestPptxHost(el: HTMLElement | null): HTMLElement | null {
  if (!el || typeof el.closest !== 'function') return null
  return el.closest(
    '[data-pptx="table"], [data-pptx="chart"], [data-pptx="figure"], [data-pptx="formula"], [data-pptx]',
  ) as HTMLElement | null
}

function hasOpaqueBackground(style: CSSStyleDeclaration): boolean {
  const bg = (style.backgroundColor || '').replace(/\s+/g, '')
  return Boolean(bg && bg !== 'transparent' && bg !== 'rgba(0,0,0,0)')
}

/**
 * Decorative geometry: dots, pills, rules, bars, icon chips — often empty of text
 * so they were previously unselectable.
 */
function isShapeLike(el: HTMLElement, doc: Document): boolean {
  if (isSlideChrome(el) || isFullSlideWrapper(el, doc) || isTableChrome(el)) return false
  const tag = el.tagName
  if (tag === 'HR') return true
  if (tag !== 'DIV' && tag !== 'SPAN' && tag !== 'I' && tag !== 'EM') return false
  if (el.hasAttribute('data-sunairum-claim') || el.hasAttribute('data-pptx')) return false

  const text = (el.innerText || el.textContent || '').trim()
  // Allow empty shapes and tiny icon glyphs (e.g. ↗), not real copy.
  if (text.length > 8) return false
  if (el.querySelector('img, svg, table, canvas, video, p, h1, h2, h3, h4, h5, h6, ul, ol, li')) {
    return false
  }

  const style = doc.defaultView?.getComputedStyle(el)
  const styleAttr = el.getAttribute('style') || ''
  const w = el.offsetWidth || parsePx(/width\s*:\s*([\d.]+)px/i.exec(styleAttr)?.[1], 0)
  const h = el.offsetHeight || parsePx(/height\s*:\s*([\d.]+)px/i.exec(styleAttr)?.[1], 0)
  if (w < 2 && h < 2) return false

  const bg =
    (style && hasOpaqueBackground(style)) ||
    /background(?:-color)?\s*:\s*(?!transparent|none|rgba?\(\s*0\s*,\s*0\s*,\s*0\s*,\s*0)/i.test(
      styleAttr,
    )
  const radius =
    (style ? parseFloat(style.borderRadius) || 0 : 0) ||
    (/border-radius\s*:\s*50%/i.test(styleAttr) ? Math.min(w, h) : 0) ||
    parsePx(/border-radius\s*:\s*([\d.]+)px/i.exec(styleAttr)?.[1], 0)
  const leaf = el.children.length === 0

  // Circle / disk / pill endpoint
  if (bg && radius >= Math.min(w, h) * 0.35 && Math.min(w, h) > 0 && Math.min(w, h) <= 160) {
    return true
  }
  // Horizontal / vertical rule or bar
  if (bg && ((h <= 14 && w >= 6) || (w <= 14 && h >= 6))) return true
  // Small filled leaf chip
  if (bg && leaf && w <= 220 && h <= 220) return true
  // Border-only empty box
  if (leaf && !text) {
    const border =
      (style
        ? (parseFloat(style.borderTopWidth) || 0) +
          (parseFloat(style.borderRightWidth) || 0) +
          (parseFloat(style.borderBottomWidth) || 0) +
          (parseFloat(style.borderLeftWidth) || 0)
        : 0) || (/border(?:-width)?\s*:/i.test(styleAttr) ? 1 : 0)
    if (border > 0 && w >= 4 && h >= 4) return true
  }
  return false
}

/** Claim cards, host plates, padded callouts — free-form movable as units. */
function isPanelLike(el: HTMLElement, doc: Document): boolean {
  if (isSlideChrome(el) || isFullSlideWrapper(el, doc) || isTableChrome(el)) return false
  if (isShapeLike(el, doc)) return false
  if (el.dataset?.sunInsert || el.dataset?.sunFreeform) return true
  if (el.hasAttribute('data-sunairum-claim') || el.hasAttribute('data-pptx')) return true
  const tag = el.tagName
  if (
    tag !== 'DIV' &&
    tag !== 'SECTION' &&
    tag !== 'ARTICLE' &&
    tag !== 'ASIDE' &&
    tag !== 'HEADER' &&
    tag !== 'FOOTER'
  ) {
    return false
  }
  const style = doc.defaultView?.getComputedStyle(el)
  if (!style) return false
  const text = (el.innerText || '').trim()
  const hasMedia = Boolean(el.querySelector('img, svg, table, canvas, video'))
  if (!text && !hasMedia) return false
  const pad =
    (parseFloat(style.paddingTop) || 0) +
    (parseFloat(style.paddingRight) || 0) +
    (parseFloat(style.paddingBottom) || 0) +
    (parseFloat(style.paddingLeft) || 0)
  const border =
    (parseFloat(style.borderTopWidth) || 0) +
    (parseFloat(style.borderRightWidth) || 0) +
    (parseFloat(style.borderBottomWidth) || 0) +
    (parseFloat(style.borderLeftWidth) || 0)
  const hasBg = hasOpaqueBackground(style)
  return border > 0 || hasBg || pad >= 10
}

function isTextBlock(el: HTMLElement): boolean {
  if (isSlideChrome(el) || isTableChrome(el)) return false
  const text = (el.innerText || '').trim()
  if (!text) return false
  const tag = el.tagName
  if (TEXT_TAGS.has(tag)) return true
  if (tag === 'DIV' || tag === 'SECTION' || tag === 'HEADER' || tag === 'FOOTER' || tag === 'ARTICLE') {
    const kids = Array.from(el.children).filter((c): c is HTMLElement => c instanceof HTMLElement)
    const textKids = kids.filter((c) => (c.innerText || '').trim() && !c.classList.contains('__sun-resize'))
    if (textKids.length === 0) return true
    // Short labels and typical claim/body panels.
    if (text.length <= 120 && textKids.length <= 2) return true
    if (text.length <= 900 && textKids.length <= 8) return true
  }
  return false
}

function isSelectableObject(el: HTMLElement, doc: Document): boolean {
  if (isSlideChrome(el) || isFullSlideWrapper(el, doc) || isTableChrome(el)) return false
  const tag = el.tagName
  if (tag === 'IMG' || tag === 'SVG' || tag === 'CANVAS' || tag === 'VIDEO' || tag === 'HR') {
    return true
  }
  if (isShapeLike(el, doc)) return true
  if (isPositioned(el, doc)) return true
  if (isPanelLike(el, doc)) return true
  return isTextBlock(el)
}

/** Viewport→slide CSS px scale (1 when unscaled; corrects transformed hosts). */
function slideClientScale(doc: Document): { sx: number; sy: number } {
  const root = findSlideRoot(doc)
  const rect = root.getBoundingClientRect()
  const cw = root.clientWidth || SLIDE_STAGE_W
  const ch = root.clientHeight || SLIDE_STAGE_H
  return {
    sx: rect.width > 1 ? rect.width / cw : 1,
    sy: rect.height > 1 ? rect.height / ch : 1,
  }
}

function readRotationDeg(el: HTMLElement, doc: Document): number {
  const style = doc.defaultView?.getComputedStyle(el)
  const t = style?.transform || el.style.transform || ''
  if (!t || t === 'none') return 0
  const match = /matrix\(([^)]+)\)/.exec(t)
  if (match) {
    const parts = match[1].split(',').map((v) => parseFloat(v.trim()))
    if (parts.length >= 2 && parts.every((n) => Number.isFinite(n))) {
      return (Math.atan2(parts[1], parts[0]) * 180) / Math.PI
    }
  }
  const rot = /rotate\((-?[\d.]+)deg\)/.exec(el.style.transform || '')
  return rot ? parseFloat(rot[1]) || 0 : 0
}

function writeRotationDeg(el: HTMLElement, deg: number) {
  const normalized = ((deg % 360) + 360) % 360
  const short = normalized > 180 ? normalized - 360 : normalized
  const rounded = Math.round(short * 10) / 10
  const existing = (el.style.transform || '').replace(/rotate\([^)]*\)/g, '').trim()
  const rotate = `rotate(${rounded}deg)`
  el.style.transform = existing ? `${existing} ${rotate}`.trim() : rotate
  el.style.transformOrigin = 'center center'
}

/** Nearest panel/card host that can contain freely positioned children. */
function findContainingPanel(el: HTMLElement, doc: Document): HTMLElement | null {
  let p = el.parentElement
  while (p && !isSlideChrome(p)) {
    if (p !== el && (isPanelLike(p, doc) || p.hasAttribute('data-sunairum-claim'))) {
      // Tables stay host-locked; don't treat table chrome as a text panel.
      if (!isTableChrome(p) && p.getAttribute('data-pptx') !== 'table') return p
    }
    p = p.parentElement
  }
  return null
}

/** True when this element renders its own text, rather than only boxing others. */
function ownsRenderedText(el: HTMLElement): boolean {
  for (const node of Array.from(el.childNodes)) {
    if (node.nodeType === Node.TEXT_NODE && String(node.textContent || '').trim()) {
      return true
    }
  }
  return false
}

/**
 * Bake absolute left/top/width relative to `container` (panel or slide), plus a
 * height that cannot crush the element's own copy.
 * Text stays inside panels when container is the panel — not ripped to slide root.
 */
function promoteToFreeform(el: HTMLElement, doc: Document, container?: HTMLElement | null): void {
  const root = container || findSlideRoot(doc)
  const win = doc.defaultView
  if (!win) return
  const rootStyle = win.getComputedStyle(root)
  if (rootStyle.position === 'static') root.style.position = 'relative'

  const rootRect = root.getBoundingClientRect()
  const rect = el.getBoundingClientRect()
  const { sx, sy } = slideClientScale(doc)
  const left = (rect.left - rootRect.left) / (sx || 1) + root.scrollLeft
  const top = (rect.top - rootRect.top) / (sy || 1) + root.scrollTop
  const width = Math.max(8, rect.width / (sx || 1))
  const height = Math.max(8, rect.height / (sy || 1))
  const rotation = readRotationDeg(el, doc)

  if (el.parentElement !== root) {
    root.appendChild(el)
  }

  el.style.position = 'absolute'
  el.style.left = `${Math.round(left)}px`
  el.style.top = `${Math.round(top)}px`
  el.style.width = `${Math.round(width)}px`
  // A box that owns copy gets its frozen size as a floor, not a cage. Baking a
  // hard height freezes whatever the element measured at this instant, and a
  // later typography change cannot fit inside it: a display number frozen at
  // height:16px while it was temporarily shrunk to 14px kept that box when it
  // returned to 104px, and its glyphs were drawn straight across the copy
  // beneath. min-height keeps a dragged size while letting the copy have room.
  if (ownsRenderedText(el)) {
    el.style.minHeight = `${Math.round(height)}px`
    el.style.height = 'auto'
  } else {
    el.style.height = `${Math.round(height)}px`
    el.style.minHeight = ''
  }
  el.style.margin = '0'
  el.style.boxSizing = 'border-box'
  el.style.maxWidth = 'none'
  el.dataset.sunFreeform = '1'
  delete el.dataset.sunFlow
  if (Math.abs(rotation) > 0.05) writeRotationDeg(el, rotation)
}

/** Target that should move: table host for cells; otherwise the element itself. */
function resolveMoveTarget(el: HTMLElement): HTMLElement {
  if (isTableChrome(el)) return closestPptxHost(el) || el
  return el
}

/** Containing block for freeform move: panel for nested text, else slide. */
function moveContainerFor(el: HTMLElement, doc: Document): HTMLElement {
  const slide = findSlideRoot(doc)
  if (isPanelLike(el, doc) || el.parentElement === slide) return slide
  const panel = findContainingPanel(el, doc)
  return panel || slide
}

/** Ensure element is absolutely positioned in its move container (panel or slide). */
function ensureMovable(el: HTMLElement, doc: Document): { el: HTMLElement; changed: boolean } {
  const target = resolveMoveTarget(el)
  const container = moveContainerFor(target, doc)
  let changed = false
  if (!(isPositioned(target, doc) && target.parentElement === container)) {
    promoteToFreeform(target, doc, container)
    changed = true
  } else if (!target.style.left && !target.style.top) {
    promoteToFreeform(target, doc, container)
    changed = true
  }
  return { el: target, changed }
}

/** Element box in slide-root CSS px (for chrome handles). */
function boxInSlideSpace(el: HTMLElement, doc: Document): {
  left: number
  top: number
  width: number
  height: number
} {
  const slide = findSlideRoot(doc)
  const slideRect = slide.getBoundingClientRect()
  const rect = el.getBoundingClientRect()
  const { sx, sy } = slideClientScale(doc)
  return {
    left: (rect.left - slideRect.left) / (sx || 1) + slide.scrollLeft,
    top: (rect.top - slideRect.top) / (sy || 1) + slide.scrollTop,
    width: Math.max(8, rect.width / (sx || 1)),
    height: Math.max(8, rect.height / (sy || 1)),
  }
}

/** Repair table chrome that was wrongly freeform-positioned inside a clipped host. */
function repairBrokenTableChrome(doc: Document): boolean {
  let fixed = false
  doc.querySelectorAll<HTMLElement>('[data-pptx="table"]').forEach((host) => {
    const chrome = host.querySelector<HTMLElement>('[data-sunairum-table-chrome]')
    if (!chrome) return
    const freeform = chrome.dataset.sunFreeform === '1' || chrome.style.position === 'absolute'
    if (!freeform) return
    // Slide-space coords on an in-host absolute child → clipped white plate.
    chrome.style.position = ''
    chrome.style.left = ''
    chrome.style.top = ''
    chrome.style.width = '100%'
    chrome.style.height = '100%'
    chrome.style.margin = ''
    chrome.style.maxWidth = ''
    delete chrome.dataset.sunFreeform
    delete chrome.dataset.sunFlow
    fixed = true
  })
  return fixed
}

function closestSelectable(start: HTMLElement | null, doc: Document): HTMLElement | null {
  if (!start) return null
  // Tables/charts/figures/formulas: always select the host, never a cell/chrome.
  const host = closestPptxHost(start)
  if (host && !isSlideChrome(host)) {
    const kind = host.getAttribute('data-pptx') || ''
    if (
      kind === 'table' ||
      kind === 'chart' ||
      kind === 'figure' ||
      kind === 'formula' ||
      isTableChrome(start)
    ) {
      return host
    }
  }

  // Prefer deepest hit: media → shape (circle/line) → text → freeform → panel.
  let el: HTMLElement | null = start
  while (el && !isSlideChrome(el)) {
    const tag = el.tagName
    if (tag === 'IMG' || tag === 'SVG' || tag === 'CANVAS' || tag === 'VIDEO' || tag === 'HR') {
      return el
    }
    if (isShapeLike(el, doc)) return el
    if (isTextBlock(el) && !isPanelLike(el, doc) && !isFullSlideWrapper(el, doc)) {
      return el
    }
    if (el.dataset?.sunFreeform === '1' && !isPanelLike(el, doc) && isSelectableObject(el, doc)) {
      return el
    }
    el = el.parentElement
  }

  // Click on card padding / empty area → select the panel unit.
  el = start
  while (el && !isSlideChrome(el)) {
    if (isPanelLike(el, doc) || isPositioned(el, doc) || isSelectableObject(el, doc)) {
      return el
    }
    el = el.parentElement
  }
  return null
}

function resolveEditableTarget(start: HTMLElement | null, doc: Document): HTMLElement | null {
  if (!start || start.tagName === 'IMG' || start.tagName === 'SVG' || start.tagName === 'CANVAS') {
    return null
  }
  let node: HTMLElement | null = start
  while (node && !isSlideChrome(node)) {
    if (isTextBlock(node) || (node.innerText || '').trim()) {
      const tag = node.tagName
      if (
        TEXT_TAGS.has(tag) ||
        tag === 'DIV' ||
        isPositioned(node, doc) ||
        node.dataset?.sunInsert
      ) {
        if ((node.innerText || '').trim()) return node
      }
    }
    node = node.parentElement
  }
  const block = closestSelectable(start, doc)
  if (block && (block.innerText || '').trim()) return block
  return null
}

function scrubEditorChrome(root: HTMLElement) {
  root.querySelector('#__sun-editor-style')?.remove()
  root.querySelectorAll('.__sun-resize, .__sun-rotate, .__sun-rotate-stem').forEach((n) => n.remove())
  root.querySelectorAll('.__sun-sel, .__sun-edit').forEach((n) => {
    n.classList.remove('__sun-sel', '__sun-edit')
    if (n instanceof HTMLElement) {
      delete n.dataset.sunFlow
    }
  })
  if (root.dataset) delete root.dataset.sunEditChrome
  root.querySelectorAll('[data-sun-edit-chrome]').forEach((n) => {
    if (n instanceof HTMLElement) delete n.dataset.sunEditChrome
  })
  root.querySelectorAll('[contenteditable]').forEach((n) => {
    n.removeAttribute('contenteditable')
  })
}

function serializeDocument(doc: Document): string {
  const html = doc.documentElement.cloneNode(true) as HTMLElement
  scrubEditorChrome(html)
  const doctype = doc.doctype ? `<!DOCTYPE ${doc.doctype.name}>` : '<!DOCTYPE html>'
  return `${doctype}\n${html.outerHTML}`
}

function prepareEditorHtml(html: string): string {
  try {
    const parsed = new DOMParser().parseFromString(html, 'text/html')
    parsed.querySelectorAll('script').forEach((node) => node.remove())
    parsed.querySelectorAll('*').forEach((el) => {
      for (const attr of Array.from(el.attributes)) {
        if (attr.name.toLowerCase().startsWith('on')) el.removeAttribute(attr.name)
      }
    })
    scrubEditorChrome(parsed.documentElement)
    // Seed stable object identities before the document enters the iframe.
    // Layers is populated immediately from this same source HTML while the
    // iframe loads; without persisting the ids here, the two DOMs allocate
    // independent `sun-*` sequences and a layer click can target no canvas
    // object at all. collectLayersFromDocument mutates candidates in-place.
    collectLayersFromDocument(parsed)
    const doctype = parsed.doctype ? `<!DOCTYPE ${parsed.doctype.name}>` : '<!DOCTYPE html>'
    return `${doctype}\n${parsed.documentElement.outerHTML}`
  } catch {
    return html
      .replace(/<script\b[\s\S]*?<\/script>/gi, '')
      .replace(/\son[a-z]+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, '')
  }
}

function assignSunIds(doc: Document) {
  const root = findSlideRoot(doc)
  const counter = { n: 0 }
  root.querySelectorAll<HTMLElement>('[data-sun-id]').forEach((el) => {
    const n = Number(String(el.dataset.sunId || '').replace(/^sun-/, ''))
    if (Number.isFinite(n) && n > counter.n) counter.n = n
  })
  const walk = (el: HTMLElement) => {
    if (!isSlideChrome(el) && isSelectableObject(el, doc)) ensureSunId(el, counter)
    Array.from(el.children).forEach((child) => {
      if (child instanceof HTMLElement) walk(child)
    })
  }
  Array.from(root.children).forEach((child) => {
    if (child instanceof HTMLElement) walk(child)
  })
}

function readSelection(el: HTMLElement, doc: Document): HtmlSelection {
  const win = doc.defaultView
  const style = win?.getComputedStyle(el)
  const rect = el.getBoundingClientRect()
  const positioned = isPositioned(el, doc)
  const left = positioned
    ? parsePx(el.style.left, el.offsetLeft)
    : rect.left
  const top = positioned
    ? parsePx(el.style.top, el.offsetTop)
    : rect.top
  const width = parsePx(el.style.width, el.offsetWidth || rect.width)
  const height = parsePx(el.style.height, el.offsetHeight || rect.height)
  const img = el.tagName === 'IMG' ? (el as HTMLImageElement) : el.querySelector('img')
  return {
    id: el.dataset.sunId || ensureSunId(el, { n: Date.now() % 100000 }),
    tag: el.tagName.toLowerCase(),
    text: (el.innerText || '').trim(),
    positioned,
    hidden: el.hidden || style?.visibility === 'hidden' || style?.display === 'none' || parseFloat(style?.opacity || '1') < 0.05,
    zIndex: parseInt(style?.zIndex || '0', 10) || 0,
    x: Math.round(left),
    y: Math.round(top),
    width: Math.round(width),
    height: Math.round(height),
    color: style?.color || '#000000',
    background: style?.backgroundColor || 'transparent',
    fontSize: style?.fontSize || '16px',
    fontFamily: style?.fontFamily || 'sans-serif',
    fontWeight: style?.fontWeight || '400',
    opacity: parseFloat(style?.opacity || '1') || 1,
    rotation: Math.round(readRotationDeg(el, doc) * 10) / 10,
    imageHref: img?.getAttribute('src') || undefined,
  }
}

const DRAG_THRESHOLD_PX = 4

type EditorApi = {
  getSelected: () => HTMLElement | null
  selectEl: (el: HTMLElement | null) => void
  emitSelection: () => void
  emitDirty: () => void
  startEdit: (el: HTMLElement) => void
  endEdit: () => void
  clearResizeHandles: () => void
  syncResizeHandles: () => void
  setEditMode: (on: boolean) => void
}

function installEditor(
  doc: Document,
  onDirty: ((html: string) => void) | undefined,
  onSelectionChange: ((sel: HtmlSelection | null) => void) | undefined,
  dirtyRef: MutableRefObject<boolean>,
  editModeRef: MutableRefObject<boolean>,
): { cleanup: () => void; api: EditorApi } {
  const win = doc.defaultView
  if (!win) {
    return {
      cleanup: () => undefined,
      api: {
        getSelected: () => null,
        selectEl: () => undefined,
        emitSelection: () => undefined,
        emitDirty: () => undefined,
        startEdit: () => undefined,
        endEdit: () => undefined,
        clearResizeHandles: () => undefined,
        syncResizeHandles: () => undefined,
        setEditMode: () => undefined,
      },
    }
  }

  let styleEl = doc.getElementById('__sun-editor-style') as HTMLStyleElement | null
  if (!styleEl) {
    styleEl = doc.createElement('style')
    styleEl.id = '__sun-editor-style'
    styleEl.textContent = EDITOR_STYLE
    ;(doc.head || doc.documentElement).appendChild(styleEl)
  }

  assignSunIds(doc)
  const repairedTables = repairBrokenTableChrome(doc)
  doc.documentElement.style.userSelect = 'text'
  doc.body.style.userSelect = 'text'

  let selected: HTMLElement | null = null
  let editing: HTMLElement | null = null
  let pending:
    | {
        el: HTMLElement
        startX: number
        startY: number
        origL: number
        origT: number
        dragging: boolean
        pointerId: number
        canDrag: boolean
        sx: number
        sy: number
      }
    | null = null
  let resize:
    | {
        el: HTMLElement
        handle: ResizeHandle
        startX: number
        startY: number
        origL: number
        origT: number
        origW: number
        origH: number
        sx: number
        sy: number
      }
    | null = null
  let rotating:
    | {
        el: HTMLElement
        startAngle: number
        origRot: number
        cx: number
        cy: number
      }
    | null = null
  /** Promote / transform changed DOM; flush on pointerup (not mid-gesture). */
  let pendingStructureDirty = false

  const emitDirty = () => {
    dirtyRef.current = true
    onDirty?.(serializeDocument(doc))
  }

  const emitSelection = () => {
    onSelectionChange?.(selected ? readSelection(selected, doc) : null)
  }

  const clearResizeHandles = () => {
    doc.querySelectorAll('.__sun-resize, .__sun-rotate, .__sun-rotate-stem').forEach((n) => n.remove())
  }

  const syncEditChrome = () => {
    if (editModeRef.current && !editing) doc.body.dataset.sunEditChrome = '1'
    else delete doc.body.dataset.sunEditChrome
  }

  const syncResizeHandles = () => {
    clearResizeHandles()
    syncEditChrome()
    if (!selected || !editModeRef.current) return
    if (editing) return
    const root = findSlideRoot(doc)
    const el = selected
    // Handles use live box — do NOT promote here (select/edit must not shift layout).
    const box = boxInSlideSpace(el, doc)
    const left = box.left
    const top = box.top
    const width = box.width
    const height = box.height
    for (const h of RESIZE_HANDLES) {
      const handle = doc.createElement('div')
      handle.className = '__sun-resize'
      handle.dataset.h = h
      handle.dataset.sunChrome = '1'
      let x = left
      let y = top
      if (h.includes('e')) x = left + width
      else if (h.includes('w')) x = left
      else x = left + width / 2
      if (h.includes('s')) y = top + height
      else if (h.includes('n')) y = top
      else y = top + height / 2
      if (h === 'n' || h === 's') x = left + width / 2
      if (h === 'e' || h === 'w') y = top + height / 2
      handle.style.left = `${Math.round(x)}px`
      handle.style.top = `${Math.round(y)}px`
      handle.addEventListener('pointerdown', (event) => {
        event.preventDefault()
        event.stopPropagation()
        const { el: movable, changed } = ensureMovable(el, doc)
        if (changed) pendingStructureDirty = true
        selected = movable
        const { sx, sy } = slideClientScale(doc)
        resize = {
          el: movable,
          handle: h,
          startX: event.clientX,
          startY: event.clientY,
          origL: parsePx(movable.style.left, movable.offsetLeft),
          origT: parsePx(movable.style.top, movable.offsetTop),
          origW: movable.offsetWidth,
          origH: movable.offsetHeight,
          sx: sx || 1,
          sy: sy || 1,
        }
        handle.setPointerCapture?.(event.pointerId)
      })
      root.appendChild(handle)
    }

    // Keep rotate clear of the top-left Insert/format chrome and slide edges.
    const ROTATE_STEM = 22
    const ROTATE_KNOB = 42
    const placeBelow =
      top < ROTATE_KNOB + 24 || (top < 160 && left + width / 2 < 420)
    const stemTop = placeBelow
      ? top + height + 6
      : top - ROTATE_STEM - 6
    const knobTop = placeBelow
      ? top + height + ROTATE_KNOB - 14
      : top - ROTATE_KNOB

    const stem = doc.createElement('div')
    stem.className = '__sun-rotate-stem'
    stem.dataset.sunChrome = '1'
    stem.dataset.side = placeBelow ? 'below' : 'above'
    stem.style.left = `${Math.round(left + width / 2)}px`
    stem.style.top = `${Math.round(stemTop)}px`
    if (placeBelow) stem.style.height = `${ROTATE_STEM}px`
    root.appendChild(stem)

    const rot = doc.createElement('div')
    rot.className = '__sun-rotate'
    rot.dataset.sunChrome = '1'
    rot.dataset.side = placeBelow ? 'below' : 'above'
    rot.title = 'Rotate'
    rot.style.left = `${Math.round(left + width / 2)}px`
    rot.style.top = `${Math.round(knobTop)}px`
    rot.addEventListener('pointerdown', (event) => {
      event.preventDefault()
      event.stopPropagation()
      const { el: movable, changed } = ensureMovable(el, doc)
      if (changed) pendingStructureDirty = true
      selected = movable
      const boxNow = boxInSlideSpace(movable, doc)
      const { sx, sy } = slideClientScale(doc)
      const rootRect = root.getBoundingClientRect()
      const cx = rootRect.left + (boxNow.left + boxNow.width / 2) * (sx || 1)
      const cy = rootRect.top + (boxNow.top + boxNow.height / 2) * (sy || 1)
      rotating = {
        el: movable,
        startAngle: (Math.atan2(event.clientY - cy, event.clientX - cx) * 180) / Math.PI,
        origRot: readRotationDeg(movable, doc),
        cx,
        cy,
      }
      rot.setPointerCapture?.(event.pointerId)
    })
    root.appendChild(rot)
  }

  const clearSel = () => {
    clearResizeHandles()
    doc.querySelectorAll('.__sun-sel').forEach((n) => {
      n.classList.remove('__sun-sel')
      if (n instanceof HTMLElement) delete n.dataset.sunFlow
    })
    selected = null
  }

  const selectEl = (el: HTMLElement | null) => {
    clearSel()
    if (!el) {
      emitSelection()
      return
    }
    // Tables → host; otherwise keep the clicked node. Never promote on select —
    // freeform lift was causing text to jump/overlay before any edit.
    const target = resolveMoveTarget(el)
    ensureSunId(target, { n: Date.now() % 100000 })
    selected = target
    target.classList.add('__sun-sel')
    if (!isPositioned(target, doc)) target.dataset.sunFlow = '1'
    else delete target.dataset.sunFlow
    syncResizeHandles()
    emitSelection()
  }

  const endEdit = () => {
    if (!editing) return
    editing.contentEditable = 'false'
    editing.classList.remove('__sun-edit')
    editing.removeAttribute('contenteditable')
    editing = null
    emitDirty()
    syncResizeHandles()
    emitSelection()
  }

  const startEdit = (el: HTMLElement) => {
    endEdit()
    // Edit in place — do not promote/reparent (layout must stay put).
    clearSel()
    ensureSunId(el, { n: Date.now() % 100000 })
    selected = el
    el.classList.add('__sun-sel')
    if (!isPositioned(el, doc)) el.dataset.sunFlow = '1'
    clearResizeHandles()
    editing = el
    el.contentEditable = 'true'
    el.classList.add('__sun-edit')
    delete doc.body.dataset.sunEditChrome
    el.focus()
    try {
      const range = doc.createRange()
      range.selectNodeContents(el)
      const sel = win.getSelection()
      sel?.removeAllRanges()
      sel?.addRange(range)
    } catch {
      /* ignore */
    }
    emitSelection()
  }

  const onPointerDown = (event: PointerEvent) => {
    if (event.button != null && event.button !== 0) return
    const target = event.target as HTMLElement | null
    if (!target) return
    if (
      target.classList?.contains('__sun-resize') ||
      target.classList?.contains('__sun-rotate') ||
      target.classList?.contains('__sun-rotate-stem') ||
      target.closest?.('.__sun-resize, .__sun-rotate')
    ) {
      return
    }

    if (editing && editing.contains(target)) {
      pending = null
      return
    }
    if (editing) endEdit()

    const el = closestSelectable(target, doc)
    if (!el) {
      selectEl(null)
      pending = null
      return
    }

    selectEl(el)
    if (!editModeRef.current || !selected) {
      pending = null
      return
    }

    const { sx, sy } = slideClientScale(doc)
    pending = {
      el: selected,
      startX: event.clientX,
      startY: event.clientY,
      origL: 0,
      origT: 0,
      dragging: false,
      pointerId: event.pointerId,
      canDrag: true,
      sx: sx || 1,
      sy: sy || 1,
    }
    event.preventDefault()
  }

  const onPointerMove = (event: PointerEvent) => {
    if (rotating) {
      const angle = (Math.atan2(event.clientY - rotating.cy, event.clientX - rotating.cx) * 180) / Math.PI
      writeRotationDeg(rotating.el, rotating.origRot + (angle - rotating.startAngle))
      clearResizeHandles()
      event.preventDefault()
      return
    }
    if (resize) {
      const dx = (event.clientX - resize.startX) / resize.sx
      const dy = (event.clientY - resize.startY) / resize.sy
      const { origL, origT, origW, origH } = resize
      let left = origL
      let top = origT
      let width = origW
      let height = origH
      const h = resize.handle
      if (h.includes('e')) width = Math.max(24, origW + dx)
      if (h.includes('s')) height = Math.max(16, origH + dy)
      if (h.includes('w')) {
        width = Math.max(24, origW - dx)
        left = origL + dx
      }
      if (h.includes('n')) {
        height = Math.max(16, origH - dy)
        top = origT + dy
      }
      resize.el.style.position = 'absolute'
      resize.el.style.left = `${Math.round(left)}px`
      resize.el.style.top = `${Math.round(top)}px`
      resize.el.style.width = `${Math.round(width)}px`
      resize.el.style.height = `${Math.round(height)}px`
      event.preventDefault()
      return
    }
    if (!pending || editing || !pending.canDrag) return
    const dxClient = event.clientX - pending.startX
    const dyClient = event.clientY - pending.startY
    if (!pending.dragging) {
      if (Math.hypot(dxClient, dyClient) < DRAG_THRESHOLD_PX) return
      // Promote only once the user actually starts moving.
      const { el: movable, changed } = ensureMovable(pending.el, doc)
      if (changed) pendingStructureDirty = true
      pending.el = movable
      selected = movable
      pending.origL = parsePx(movable.style.left, movable.offsetLeft)
      pending.origT = parsePx(movable.style.top, movable.offsetTop)
      pending.startX = event.clientX
      pending.startY = event.clientY
      pending.dragging = true
      try {
        pending.el.setPointerCapture?.(pending.pointerId)
      } catch {
        /* ignore */
      }
      clearResizeHandles()
      event.preventDefault()
      return
    }
    const dx = dxClient / pending.sx
    const dy = dyClient / pending.sy
    event.preventDefault()
    pending.el.style.position = 'absolute'
    pending.el.style.left = `${Math.round(pending.origL + dx)}px`
    pending.el.style.top = `${Math.round(pending.origT + dy)}px`
    clearResizeHandles()
  }

  const onPointerUp = () => {
    if (rotating) {
      rotating = null
      pendingStructureDirty = false
      emitDirty()
      syncResizeHandles()
      emitSelection()
      return
    }
    if (resize) {
      resize = null
      pendingStructureDirty = false
      emitDirty()
      syncResizeHandles()
      emitSelection()
      return
    }
    if (!pending) {
      if (pendingStructureDirty) {
        pendingStructureDirty = false
        emitDirty()
      }
      return
    }
    const didDrag = pending.dragging
    pending = null
    if (didDrag || pendingStructureDirty) {
      pendingStructureDirty = false
      emitDirty()
      syncResizeHandles()
      emitSelection()
    }
  }

  const onDblClick = (event: MouseEvent) => {
    const target = event.target as HTMLElement | null
    if (!target) return
    pending = null
    const el = resolveEditableTarget(target, doc)
    if (!el) return
    event.preventDefault()
    event.stopPropagation()
    startEdit(el)
  }

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === 'Escape') {
      if (editing) {
        endEdit()
        event.preventDefault()
        return
      }
      selectEl(null)
      return
    }
    if (editing) return
    if ((event.key === 'Enter' || event.key === 'F2') && selected) {
      const el = resolveEditableTarget(selected, doc)
      if (el) {
        event.preventDefault()
        startEdit(el)
      }
      return
    }
    if (
      editModeRef.current &&
      selected &&
      (event.key === 'ArrowLeft' ||
        event.key === 'ArrowRight' ||
        event.key === 'ArrowUp' ||
        event.key === 'ArrowDown')
    ) {
      event.preventDefault()
      const { el } = ensureMovable(selected, doc)
      selected = el
      const step = event.shiftKey ? 10 : 1
      const left = parsePx(el.style.left, el.offsetLeft)
      const top = parsePx(el.style.top, el.offsetTop)
      if (event.key === 'ArrowLeft') el.style.left = `${left - step}px`
      if (event.key === 'ArrowRight') el.style.left = `${left + step}px`
      if (event.key === 'ArrowUp') el.style.top = `${top - step}px`
      if (event.key === 'ArrowDown') el.style.top = `${top + step}px`
      syncResizeHandles()
      emitDirty()
      emitSelection()
      return
    }
    if ((event.key === 'Delete' || event.key === 'Backspace') && selected && editModeRef.current) {
      event.preventDefault()
      event.stopPropagation()
      selected.remove()
      selectEl(null)
      emitDirty()
      return
    }
  }

  const onInput = () => {
    if (editing) emitDirty()
  }

  doc.addEventListener('pointerdown', onPointerDown, true)
  doc.addEventListener('pointermove', onPointerMove, true)
  doc.addEventListener('pointerup', onPointerUp, true)
  doc.addEventListener('pointercancel', onPointerUp, true)
  doc.addEventListener('dblclick', onDblClick, true)
  doc.addEventListener('keydown', onKeyDown, true)
  doc.addEventListener('input', onInput, true)

  const api: EditorApi = {
    getSelected: () => selected,
    selectEl,
    emitSelection,
    emitDirty,
    startEdit,
    endEdit,
    clearResizeHandles,
    syncResizeHandles,
    setEditMode: (on) => {
      editModeRef.current = on
      syncResizeHandles()
    },
  }

  if (repairedTables) {
    // Persist the repair so the white clipped table does not return on reload.
    queueMicrotask(() => emitDirty())
  }

  return {
    cleanup: () => {
      endEdit()
      clearSel()
      pending = null
      resize = null
      rotating = null
      pendingStructureDirty = false
      doc.removeEventListener('pointerdown', onPointerDown, true)
      doc.removeEventListener('pointermove', onPointerMove, true)
      doc.removeEventListener('pointerup', onPointerUp, true)
      doc.removeEventListener('pointercancel', onPointerUp, true)
      doc.removeEventListener('dblclick', onDblClick, true)
      doc.removeEventListener('keydown', onKeyDown, true)
      doc.removeEventListener('input', onInput, true)
    },
    api,
  }
}

function insertIntoDoc(
  doc: Document,
  kind: InsertKind,
  opts?: { imageUrl?: string },
): HTMLElement | null {
  const root = findSlideRoot(doc)
  const rootStyle = doc.defaultView?.getComputedStyle(root)
  if (rootStyle && rootStyle.position === 'static') root.style.position = 'relative'

  const el = doc.createElement('div')
  el.dataset.sunInsert = kind
  el.dataset.sunId = `sun-${Date.now() % 1000000}`
  el.style.position = 'absolute'
  el.style.left = '120px'
  el.style.top = '120px'
  el.style.boxSizing = 'border-box'
  el.style.zIndex = '999'

  if (kind === 'text') {
    el.style.width = '360px'
    el.style.minHeight = '48px'
    el.style.padding = '12px 14px'
    el.style.fontFamily = 'Georgia, serif'
    el.style.fontSize = '20px'
    el.style.lineHeight = '1.35'
    el.style.color = '#1A202C'
    el.style.background = 'rgba(255,255,255,0.92)'
    el.style.border = '1px solid #E2E8F0'
    el.style.borderRadius = '8px'
    el.textContent = 'New text'
  } else if (kind === 'rect') {
    el.style.width = '280px'
    el.style.height = '160px'
    el.style.background = '#EBF4FB'
    el.style.border = '1px solid #D0DCEA'
    el.style.borderRadius = '10px'
  } else if (kind === 'ellipse') {
    el.style.width = '120px'
    el.style.height = '120px'
    el.style.borderRadius = '999px'
    el.style.background = '#3182CE'
  } else if (kind === 'line') {
    el.style.width = '400px'
    el.style.height = '3px'
    el.style.background = '#3182CE'
    el.style.borderRadius = '2px'
  } else if (kind === 'image' || kind === 'ai_image') {
    const url = opts?.imageUrl
    if (!url) return null
    el.style.width = '360px'
    el.style.height = '220px'
    el.style.overflow = 'hidden'
    el.style.borderRadius = '10px'
    el.style.background = '#F5F7FA'
    const img = doc.createElement('img')
    img.src = url
    img.alt = ''
    img.style.width = '100%'
    img.style.height = '100%'
    img.style.objectFit = 'cover'
    img.style.display = 'block'
    el.appendChild(img)
  } else {
    return null
  }

  root.appendChild(el)
  return el
}

const EditableHtmlSlide = forwardRef<EditableHtmlSlideHandle, Props>(function EditableHtmlSlide(
  {
    html,
    title,
    width = SLIDE_STAGE_W,
    height = SLIDE_STAGE_H,
    onDirty,
    onSelectionChange,
    onReady,
    editMode = true,
  },
  ref,
) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null)
  const cleanupRef = useRef<(() => void) | null>(null)
  const apiRef = useRef<EditorApi | null>(null)
  const dirtyRef = useRef(false)
  const onDirtyRef = useRef(onDirty)
  const onSelectionRef = useRef(onSelectionChange)
  const onReadyRef = useRef(onReady)
  const editModeRef = useRef(editMode)
  /** Last HTML we emitted via onDirty — ignore parent echo so edits don't remount the iframe. */
  const lastEmittedHtmlRef = useRef<string | null>(null)
  const [srcDoc, setSrcDoc] = useState(() => prepareEditorHtml(html))
  onDirtyRef.current = onDirty
  onSelectionRef.current = onSelectionChange
  onReadyRef.current = onReady
  editModeRef.current = editMode

  const emitDirtyToParent = useCallback(
    (nextHtml: string) => {
      lastEmittedHtmlRef.current = nextHtml
      onDirtyRef.current?.(nextHtml)
    },
    [],
  )

  useEffect(() => {
    editModeRef.current = editMode
    apiRef.current?.setEditMode(editMode)
  }, [editMode])

  // Parent-driven HTML swaps only (slide change / undo). Ignore our own dirty echoes.
  useEffect(() => {
    const next = prepareEditorHtml(html)
    if (lastEmittedHtmlRef.current != null) {
      const emitted = prepareEditorHtml(lastEmittedHtmlRef.current)
      if (next === emitted || html === lastEmittedHtmlRef.current) return
    }
    const live = iframeRef.current?.contentDocument?.documentElement
      ? serializeDocument(iframeRef.current.contentDocument)
      : null
    if (live && prepareEditorHtml(live) === next) {
      lastEmittedHtmlRef.current = html
      return
    }
    setSrcDoc((prev) => (prev === next ? prev : next))
    const iframe = iframeRef.current
    if (iframe && iframe.srcdoc !== next) {
      dirtyRef.current = false
      lastEmittedHtmlRef.current = null
      iframe.srcdoc = next
    }
  }, [html])

  useImperativeHandle(
    ref,
    () => ({
      getHtml: () => {
        const doc = iframeRef.current?.contentDocument
        if (!doc?.documentElement) return null
        return serializeDocument(doc)
      },
      setHtml: (next: string) => {
        const iframe = iframeRef.current
        if (!iframe) return
        dirtyRef.current = false
        const prepared = prepareEditorHtml(next)
        lastEmittedHtmlRef.current = next
        iframe.srcdoc = prepared
      },
      insertKind: (kind, opts) => {
        const doc = iframeRef.current?.contentDocument
        if (!doc) return false
        const el = insertIntoDoc(doc, kind, opts)
        if (!el) return false
        dirtyRef.current = true
        emitDirtyToParent(serializeDocument(doc))
        apiRef.current?.selectEl(el)
        return true
      },
      focus: () => {
        iframeRef.current?.contentWindow?.focus()
      },
      getSelection: () => {
        const doc = iframeRef.current?.contentDocument
        const el = apiRef.current?.getSelected()
        if (!doc || !el) return null
        return readSelection(el, doc)
      },
      listLayers: () => {
        const doc = iframeRef.current?.contentDocument
        if (!doc) return []
        return collectLayersFromDocument(doc)
      },
      selectById: (id) => {
        const doc = iframeRef.current?.contentDocument
        if (!doc) return false
        if (!id) {
          apiRef.current?.selectEl(null)
          return true
        }
        const el = doc.querySelector(`[data-sun-id="${CSS.escape(id)}"]`) as HTMLElement | null
        if (!el) return false
        apiRef.current?.selectEl(el)
        return true
      },
      applyStyle: (patch) => {
        const doc = iframeRef.current?.contentDocument
        const el = apiRef.current?.getSelected()
        if (!doc || !el) return false
        if (patch.color != null) el.style.color = patch.color
        if (patch.background != null) el.style.background = patch.background
        if (patch.fontSize != null) el.style.fontSize = patch.fontSize
        if (patch.fontFamily != null) el.style.fontFamily = patch.fontFamily
        if (patch.fontWeight != null) el.style.fontWeight = patch.fontWeight
        if (patch.opacity != null) el.style.opacity = String(patch.opacity)
        if (patch.left != null) {
          el.style.position = el.style.position || 'absolute'
          el.style.left = `${patch.left}px`
        }
        if (patch.top != null) {
          el.style.position = el.style.position || 'absolute'
          el.style.top = `${patch.top}px`
        }
        if (patch.width != null) el.style.width = `${patch.width}px`
        if (patch.height != null) el.style.height = `${patch.height}px`
        if (patch.rotation != null && Number.isFinite(patch.rotation)) {
          writeRotationDeg(el, patch.rotation)
        }
        if (patch.hidden != null) {
          el.style.visibility = patch.hidden ? 'hidden' : 'visible'
          if (!patch.hidden && el.style.opacity === '0') el.style.opacity = '1'
        }
        apiRef.current?.emitDirty()
        apiRef.current?.syncResizeHandles()
        apiRef.current?.emitSelection()
        return true
      },
      applyText: (text) => {
        const el = apiRef.current?.getSelected()
        if (!el) return false
        el.textContent = text
        apiRef.current?.emitDirty()
        apiRef.current?.emitSelection()
        return true
      },
      reorderLayer: (id, direction) => {
        const doc = iframeRef.current?.contentDocument
        if (!doc) return false
        const el = doc.querySelector(`[data-sun-id="${CSS.escape(id)}"]`) as HTMLElement | null
        if (!el?.parentElement) return false
        const parent = el.parentElement
        const siblings = Array.from(parent.children).filter(
          (n): n is HTMLElement =>
            n instanceof HTMLElement &&
            !n.classList.contains('__sun-resize') &&
            !n.classList.contains('__sun-rotate') &&
            !n.classList.contains('__sun-rotate-stem') &&
            n.dataset.sunChrome !== '1',
        )
        const idx = siblings.indexOf(el)
        if (idx < 0) return false
        if (direction === 'up' && idx < siblings.length - 1) {
          parent.insertBefore(siblings[idx + 1], el)
        } else if (direction === 'down' && idx > 0) {
          parent.insertBefore(el, siblings[idx - 1])
        } else if (direction === 'top') {
          parent.appendChild(el)
        } else if (direction === 'bottom') {
          parent.insertBefore(el, siblings[0] || null)
        } else {
          return false
        }
        apiRef.current?.emitDirty()
        apiRef.current?.emitSelection()
        return true
      },
      deleteSelection: () => {
        const el = apiRef.current?.getSelected()
        if (!el) return false
        el.remove()
        apiRef.current?.selectEl(null)
        apiRef.current?.emitDirty()
        return true
      },
      startTextEdit: () => {
        const doc = iframeRef.current?.contentDocument
        const el = apiRef.current?.getSelected()
        if (!doc || !el) return false
        const target = resolveEditableTarget(el, doc)
        if (!target) return false
        apiRef.current?.startEdit(target)
        return true
      },
    }),
    [emitDirtyToParent],
  )

  useEffect(() => {
    const iframe = iframeRef.current
    if (!iframe) return

    const docLooksReady = (doc: Document | null): boolean => {
      if (!doc?.body) return false
      // Skip about:blank / empty shells before srcDoc paints.
      const root =
        (doc.querySelector('.slide') as HTMLElement | null) ||
        (doc.querySelector('section') as HTMLElement | null) ||
        doc.body
      if (root.children.length > 0) return true
      return Boolean(
        (root.textContent || '').trim() || root.querySelector('img, svg, table, canvas'),
      )
    }

    let cancelled = false
    let retryTimer: ReturnType<typeof setTimeout> | null = null

    const install = () => {
      if (cancelled) return
      const doc = iframe.contentDocument
      if (!docLooksReady(doc)) {
        retryTimer = setTimeout(install, 40)
        return
      }
      cleanupRef.current?.()
      cleanupRef.current = null
      apiRef.current = null
      if (!doc) return
      doc.querySelectorAll('script').forEach((node) => node.remove())
      const { cleanup, api } = installEditor(
        doc,
        (next) => emitDirtyToParent(next),
        (sel) => onSelectionRef.current?.(sel),
        dirtyRef,
        editModeRef,
      )
      cleanupRef.current = cleanup
      apiRef.current = api
      api.setEditMode(editModeRef.current)
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          if (!cancelled) onReadyRef.current?.()
        })
      })
    }

    const onLoad = () => install()

    iframe.addEventListener('load', onLoad)
    if (iframe.contentDocument?.readyState === 'complete') onLoad()
    return () => {
      cancelled = true
      if (retryTimer) clearTimeout(retryTimer)
      iframe.removeEventListener('load', onLoad)
      cleanupRef.current?.()
      cleanupRef.current = null
      apiRef.current = null
    }
  }, [emitDirtyToParent])

  return (
    <iframe
      ref={iframeRef}
      title={title || 'Slide editor'}
      sandbox="allow-same-origin allow-scripts"
      srcDoc={srcDoc}
      tabIndex={0}
      style={{
        display: 'block',
        width,
        height,
        border: 0,
        background: '#fff',
      }}
    />
  )
})

export default EditableHtmlSlide
