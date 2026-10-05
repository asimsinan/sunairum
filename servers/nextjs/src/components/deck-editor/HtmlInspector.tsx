'use client'

import styles from './deckEditor.module.css'
import type { HtmlSelection, HtmlStylePatch } from './types'

type Props = {
  selection: HtmlSelection | null
  onApplyStyle: (patch: HtmlStylePatch) => void
  onApplyText: (text: string) => void
  onDelete: () => void
  onEditText: () => void
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

export default function HtmlInspector({
  selection,
  onApplyStyle,
  onApplyText,
  onDelete,
  onEditText,
}: Props) {
  return (
    <aside className={styles.inspector} aria-label="Inspector">
      <div className={styles.inspectorTitle}>Inspector</div>
      {!selection ? (
        <p className={styles.inspectorEmpty}>Select an element on the slide to edit its properties.</p>
      ) : (
        <>
          <div className={styles.field}>
            <label>Element</label>
            <input
              readOnly
              value={`${selection.tag}${selection.positioned ? ' · absolute' : ' · flow'}`}
            />
          </div>

          {(selection.text || selection.tag === 'p' || selection.tag.startsWith('h')) && (
            <div className={styles.field}>
              <label>Text</label>
              <textarea
                rows={3}
                value={selection.text}
                onChange={(e) => onApplyText(e.target.value)}
              />
              <button type="button" className={styles.btn} onClick={onEditText}>
                Edit on canvas
              </button>
            </div>
          )}

          <div className={styles.fieldRow}>
            <div className={styles.field}>
              <label>Size</label>
              <input
                type="number"
                min={8}
                max={120}
                value={Math.round(parseFloat(selection.fontSize) || 16)}
                onChange={(e) => onApplyStyle({ fontSize: `${e.target.value}px` })}
              />
            </div>
            <div className={styles.field}>
              <label>Weight</label>
              <select
                value={
                  selection.fontWeight === '700' || selection.fontWeight === 'bold' ? '700' : '400'
                }
                onChange={(e) => onApplyStyle({ fontWeight: e.target.value })}
              >
                <option value="400">Regular</option>
                <option value="700">Bold</option>
              </select>
            </div>
          </div>

          <div className={styles.fieldRow}>
            <div className={styles.field}>
              <label>Color</label>
              <input
                type="color"
                value={toHex(selection.color)}
                onChange={(e) => onApplyStyle({ color: e.target.value })}
              />
            </div>
            <div className={styles.field}>
              <label>Fill</label>
              <input
                type="color"
                value={toHex(selection.background === 'transparent' ? '#ffffff' : selection.background)}
                onChange={(e) => onApplyStyle({ background: e.target.value })}
              />
            </div>
          </div>

          <div className={styles.field}>
            <label>Opacity</label>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={selection.opacity}
              onChange={(e) => onApplyStyle({ opacity: Number(e.target.value) })}
            />
          </div>

          {selection.positioned && (
            <>
              <div className={styles.fieldRow}>
                <div className={styles.field}>
                  <label>X</label>
                  <input
                    type="number"
                    value={selection.x}
                    onChange={(e) => onApplyStyle({ left: Number(e.target.value) })}
                  />
                </div>
                <div className={styles.field}>
                  <label>Y</label>
                  <input
                    type="number"
                    value={selection.y}
                    onChange={(e) => onApplyStyle({ top: Number(e.target.value) })}
                  />
                </div>
                <div className={styles.field}>
                  <label>W</label>
                  <input
                    type="number"
                    value={selection.width}
                    onChange={(e) => onApplyStyle({ width: Number(e.target.value) })}
                  />
                </div>
                <div className={styles.field}>
                  <label>H</label>
                  <input
                    type="number"
                    value={selection.height}
                    onChange={(e) => onApplyStyle({ height: Number(e.target.value) })}
                  />
                </div>
              </div>
              <div className={styles.field}>
                <label>Rotate (°)</label>
                <input
                  type="number"
                  step={1}
                  value={selection.rotation}
                  onChange={(e) => onApplyStyle({ rotation: Number(e.target.value) })}
                />
              </div>
            </>
          )}

          <button type="button" className={styles.btn} data-danger="true" onClick={onDelete}>
            Delete
          </button>
        </>
      )}
    </aside>
  )
}
