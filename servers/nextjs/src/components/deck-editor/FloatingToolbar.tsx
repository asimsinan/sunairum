'use client'

import { forwardRef } from 'react'
import styles from './deckEditor.module.css'
import type { InspectorState } from './types'

type Props = {
  selection: InspectorState | null
  left: number
  top: number
  onChange: (patch: Partial<InspectorState>) => void
  onEditText?: () => void
  onReplaceImage?: () => void
  onAiEdit?: () => void
  onDelete?: () => void
  onDuplicate?: () => void
  onBringForward?: () => void
  onSendBackward?: () => void
  onBringToFront?: () => void
  onSendToBack?: () => void
}

const FloatingToolbar = forwardRef<HTMLDivElement, Props>(function FloatingToolbar(
  {
    selection,
    left,
    top,
    onChange,
    onEditText,
    onReplaceImage,
    onAiEdit,
    onDelete,
    onDuplicate,
    onBringForward,
    onSendBackward,
    onBringToFront,
    onSendToBack,
  },
  ref,
) {
  if (!selection) return null
  const tag = selection.tag
  const isText = tag === 'text' || tag === 'tspan'
  const isImage = tag === 'image'
  const isShape = ['rect', 'circle', 'ellipse', 'path', 'polygon', 'line'].includes(tag)

  return (
    <div
      ref={ref}
      className={styles.floatingToolbar}
      style={{ left, top }}
      onMouseDown={(e) => e.stopPropagation()}
      onPointerDown={(e) => e.stopPropagation()}
    >
      {isText && (
        <>
          {onEditText && (
            <button type="button" className={styles.toolBtn} onClick={onEditText} title="Double-click text to edit">
              Edit text
            </button>
          )}
          <button
            type="button"
            className={styles.toolBtn}
            data-active={selection.fontWeight === '700' || selection.fontWeight === 'bold'}
            onClick={() =>
              onChange({
                fontWeight:
                  selection.fontWeight === '700' || selection.fontWeight === 'bold' ? '400' : '700',
              })
            }
          >
            B
          </button>
          <label className={styles.toolField}>
            <span>Size</span>
            <input
              type="number"
              min={10}
              max={96}
              value={Number.parseFloat(selection.fontSize || '18') || 18}
              onChange={(e) => onChange({ fontSize: `${e.target.value}px` })}
            />
          </label>
          <label className={styles.toolField}>
            <span>Color</span>
            <input
              type="color"
              value={normalizeHex(selection.fill || '#0F172A')}
              onChange={(e) => onChange({ fill: e.target.value })}
            />
          </label>
        </>
      )}
      {isShape && (
        <>
          <label className={styles.toolField}>
            <span>Fill</span>
            <input
              type="color"
              value={normalizeHex(selection.fill || '#3B82F6')}
              onChange={(e) => onChange({ fill: e.target.value })}
            />
          </label>
          <label className={styles.toolField}>
            <span>Stroke</span>
            <input
              type="color"
              value={normalizeHex(selection.stroke || '#0F172A')}
              onChange={(e) => onChange({ stroke: e.target.value })}
            />
          </label>
        </>
      )}
      {isImage && (
        <>
          <button type="button" className={styles.toolBtn} onClick={onReplaceImage}>
            Replace
          </button>
          <label className={styles.toolField}>
            <span>Opacity</span>
            <input
              type="range"
              min={0.1}
              max={1}
              step={0.05}
              value={selection.opacity ?? 1}
              onChange={(e) => onChange({ opacity: Number.parseFloat(e.target.value) })}
            />
          </label>
        </>
      )}
      <button type="button" className={styles.toolBtn} onClick={onBringToFront} title="Bring to front (⌘⇧])">
        ⇈
      </button>
      <button type="button" className={styles.toolBtn} onClick={onBringForward} title="Bring forward (⌘])">
        ↑
      </button>
      <button type="button" className={styles.toolBtn} onClick={onSendBackward} title="Send backward (⌘[)">
        ↓
      </button>
      <button type="button" className={styles.toolBtn} onClick={onSendToBack} title="Send to back (⌘⇧[)">
        ⇊
      </button>
      <button type="button" className={styles.toolBtn} onClick={onDuplicate}>
        Dup
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
})

export default FloatingToolbar

function normalizeHex(value: string): string {
  if (/^#[0-9a-fA-F]{6}$/.test(value)) return value
  if (/^#[0-9a-fA-F]{3}$/.test(value)) {
    const r = value[1]
    const g = value[2]
    const b = value[3]
    return `#${r}${r}${g}${g}${b}${b}`
  }
  return '#0F172A'
}
