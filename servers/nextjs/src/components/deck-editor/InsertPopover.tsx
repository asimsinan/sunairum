'use client'

import { useEffect, useRef } from 'react'
import Icon from '@/components/Icon'
import type { InsertKind } from './insertKinds'
import styles from './deckEditor.module.css'

type Item = {
  kind: InsertKind
  label: string
  hint: string
  icon: 'type' | 'shape' | 'image' | 'plus'
}

const SECTIONS: { title: string; items: Item[] }[] = [
  {
    title: 'Text',
    items: [{ kind: 'text', label: 'Text box', hint: 'Body copy', icon: 'type' }],
  },
  {
    title: 'Shapes',
    items: [
      { kind: 'rect', label: 'Rectangle', hint: 'Card / panel', icon: 'shape' },
      { kind: 'ellipse', label: 'Ellipse', hint: 'Badge / node', icon: 'shape' },
      { kind: 'line', label: 'Line', hint: 'Divider', icon: 'shape' },
    ],
  },
  {
    title: 'Media',
    items: [
      { kind: 'image', label: 'Image', hint: 'Upload file', icon: 'image' },
      { kind: 'ai_image', label: 'AI image', hint: 'Generate from prompt', icon: 'image' },
    ],
  },
]

export default function InsertPopover({
  open,
  onClose,
  onInsert,
  anchor = 'canvas',
}: {
  open: boolean
  onClose: () => void
  onInsert: (kind: InsertKind) => void
  anchor?: 'canvas' | 'header'
}) {
  const rootRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    const onPointer = (event: MouseEvent | PointerEvent) => {
      const node = rootRef.current
      if (!node) return
      if (event.target instanceof Node && !node.contains(event.target)) {
        // Ignore the Insert toggle buttons themselves (they toggle open).
        const el = event.target as HTMLElement
        if (el.closest?.('[data-insert-toggle="true"]')) return
        onClose()
      }
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('pointerdown', onPointer, true)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('pointerdown', onPointer, true)
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      ref={rootRef}
      className={styles.insertPopover}
      data-anchor={anchor}
      role="menu"
      aria-label="Insert"
    >
      {SECTIONS.map((section) => (
        <div key={section.title} className={styles.insertSection}>
          <div className={styles.insertSectionTitle}>{section.title}</div>
          <div className={styles.insertGrid}>
            {section.items.map((item) => (
              <button
                key={item.kind}
                type="button"
                role="menuitem"
                className={styles.insertItem}
                onPointerDown={(event) => event.stopPropagation()}
                onClick={(event) => {
                  event.preventDefault()
                  event.stopPropagation()
                  onInsert(item.kind)
                }}
              >
                <span className={styles.insertItemIcon}>
                  <Icon name={item.icon} className="w-4 h-4" />
                </span>
                <span className={styles.insertItemCopy}>
                  <strong>{item.label}</strong>
                  <small>{item.hint}</small>
                </span>
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
