'use client'

import { useCallback, useRef, useState } from 'react'
import styles from './deckEditor.module.css'
import type { HtmlSelection, HtmlStylePatch } from './types'

type Pos = { left: number; top: number }

type Props = {
  selection: HtmlSelection | null
  onApplyStyle: (patch: HtmlStylePatch) => void
  onEditText?: () => void
  onAiEdit?: () => void
  onDelete?: () => void
  onBringForward?: () => void
  onSendBackward?: () => void
  onBringToFront?: () => void
  onSendToBack?: () => void
  position?: Pos | null
  onPositionChange?: (pos: Pos) => void
}

function toHex(color: string): string {
  if (/^#[0-9a-fA-F]{6}$/.test(color)) return color
  if (/^#[0-9a-fA-F]{3}$/.test(color)) {
    const r = color[1]
    const g = color[2]
    const b = color[3]
    return `#${r}${r}${g}${g}${b}${b}`
  }
  const m = color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/i)
  if (m) {
    const hex = (n: string) => Number(n).toString(16).padStart(2, '0')
    return `#${hex(m[1])}${hex(m[2])}${hex(m[3])}`
  }
  return '#1A202C'
}

function isInteractive(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false
  return Boolean(target.closest('button, input, select, textarea, label, a'))
}

export default function HtmlFormatToolbar({
  selection,
  onApplyStyle,
  onEditText,
  onAiEdit,
  onDelete,
  onBringForward,
  onSendBackward,
  onBringToFront,
  onSendToBack,
  position = null,
  onPositionChange,
}: Props) {
  const rootRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<{
    pointerId: number
    startX: number
    startY: number
    origLeft: number
    origTop: number
  } | null>(null)
  const [dragging, setDragging] = useState(false)

  const beginDrag = useCallback((event: React.PointerEvent) => {
    if (event.button !== 0) return
    const el = rootRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    const parent = el.offsetParent as HTMLElement | null
    const parentRect = parent?.getBoundingClientRect()
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      origLeft: rect.left - (parentRect?.left ?? 0),
      origTop: rect.top - (parentRect?.top ?? 0),
    }
    setDragging(true)
    el.setPointerCapture(event.pointerId)
  }, [])

  const onRootPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    event.stopPropagation()
    if (isInteractive(event.target)) return
    event.preventDefault()
    beginDrag(event)
  }

  const onHandlePointerDown = (event: React.PointerEvent<HTMLButtonElement>) => {
    event.stopPropagation()
    event.preventDefault()
    beginDrag(event)
  }

  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current
    if (!drag || event.pointerId !== drag.pointerId) return
    const el = rootRef.current
    const parent = el?.offsetParent as HTMLElement | null
    if (!el || !parent) return
    const maxLeft = Math.max(0, parent.clientWidth - el.offsetWidth)
    const maxTop = Math.max(0, parent.clientHeight - el.offsetHeight)
    const left = Math.min(maxLeft, Math.max(0, drag.origLeft + (event.clientX - drag.startX)))
    const top = Math.min(maxTop, Math.max(0, drag.origTop + (event.clientY - drag.startY)))
    onPositionChange?.({ left, top })
  }

  const endDrag = (event: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current
    if (!drag || event.pointerId !== drag.pointerId) return
    dragRef.current = null
    setDragging(false)
    try {
      rootRef.current?.releasePointerCapture(event.pointerId)
    } catch {
      /* already released */
    }
  }

  if (!selection) return null
  const isText =
    Boolean(selection.text) ||
    ['p', 'h1', 'h2', 'h3', 'h4', 'span', 'li', 'div'].includes(selection.tag)
  const isImage = selection.tag === 'img' || Boolean(selection.imageHref)
  const bold = selection.fontWeight === '700' || selection.fontWeight === 'bold'

  return (
    <div
      ref={rootRef}
      className={styles.floatingToolbar}
      data-html-format="1"
      data-dragging={dragging ? 'true' : undefined}
      style={position ? { left: position.left, top: position.top, right: 'auto' } : undefined}
      onMouseDown={(e) => e.stopPropagation()}
      onPointerDown={onRootPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
    >
      <button
        type="button"
        className={styles.toolbarDragHandle}
        aria-label="Move edit toolbar"
        title="Drag to move"
        onPointerDown={onHandlePointerDown}
      >
        <span aria-hidden="true" />
      </button>
      {isText && (
        <>
          {onEditText && (
            <button type="button" className={styles.toolBtn} onClick={onEditText}>
              Edit
            </button>
          )}
          <button
            type="button"
            className={styles.toolBtn}
            data-active={bold}
            onClick={() => onApplyStyle({ fontWeight: bold ? '400' : '700' })}
          >
            B
          </button>
          <label className={styles.toolField}>
            <span>Size</span>
            <input
              type="number"
              min={8}
              max={120}
              value={Math.round(parseFloat(selection.fontSize) || 16)}
              onChange={(e) => onApplyStyle({ fontSize: `${e.target.value}px` })}
            />
          </label>
          <label className={styles.toolField}>
            <span>Color</span>
            <input
              type="color"
              value={toHex(selection.color)}
              onChange={(e) => onApplyStyle({ color: e.target.value })}
            />
          </label>
        </>
      )}
      {isImage && (
        <label className={styles.toolField}>
          <span>Opacity</span>
          <input
            type="range"
            min={0.1}
            max={1}
            step={0.05}
            value={selection.opacity}
            onChange={(e) => onApplyStyle({ opacity: Number(e.target.value) })}
          />
        </label>
      )}
      {!isText && !isImage && (
        <label className={styles.toolField}>
          <span>Fill</span>
          <input
            type="color"
            value={toHex(selection.background === 'transparent' ? '#3182CE' : selection.background)}
            onChange={(e) => onApplyStyle({ background: e.target.value })}
          />
        </label>
      )}
      <button type="button" className={styles.toolBtn} onClick={onBringToFront} title="Bring to front">
        ⇈
      </button>
      <button type="button" className={styles.toolBtn} onClick={onBringForward} title="Bring forward">
        ↑
      </button>
      <button type="button" className={styles.toolBtn} onClick={onSendBackward} title="Send backward">
        ↓
      </button>
      <button type="button" className={styles.toolBtn} onClick={onSendToBack} title="Send to back">
        ⇊
      </button>
      {onAiEdit && (
        <button type="button" className={styles.toolBtn} onClick={onAiEdit}>
          AI
        </button>
      )}
      <button type="button" className={styles.toolBtn} data-danger onClick={onDelete}>
        Del
      </button>
    </div>
  )
}
