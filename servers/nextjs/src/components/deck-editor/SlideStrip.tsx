'use client'

import { API_URL } from '@/lib/api'
import type { SlideInfo } from './types'
import styles from './deckEditor.module.css'

export type SlideStripBadges = {
  notes?: Set<string> | Record<string, boolean>
  regenerating?: string | null
  dirty?: Set<string> | Record<string, boolean>
}

type Props = {
  slides: SlideInfo[]
  activeIndex: number
  onSelect: (index: number) => void
  onMove?: (from: number, to: number) => void
  badges?: SlideStripBadges
}

function hasBadge(map: Set<string> | Record<string, boolean> | undefined, key: string): boolean {
  if (!map) return false
  if (map instanceof Set) return map.has(key)
  return Boolean(map[key])
}

export default function SlideStrip({ slides, activeIndex, onSelect, onMove, badges }: Props) {
  return (
    <aside className={styles.strip} aria-label="Slides">
      <div className={styles.stripHeader}>
        <span className={styles.stripTitle}>Slides</span>
        <span className={styles.stripCount}>{slides.length}</span>
      </div>
      <div className={styles.stripList}>
        {slides.map((slide, index) => {
          const src = slide.url
            ? slide.url.startsWith('http')
              ? slide.url
              : `${API_URL}${slide.url}`
            : ''
          const stem = slide.filename.replace(/\.(json|png|svg|html|md)$/i, '')
          const hasNotes = hasBadge(badges?.notes, slide.filename) || hasBadge(badges?.notes, stem)
          const isDirty = hasBadge(badges?.dirty, slide.filename)
          const isAi = badges?.regenerating === slide.filename
          return (
            <div
              key={slide.filename}
              className={styles.thumbRow}
              data-active={index === activeIndex ? 'true' : 'false'}
              data-ai={isAi ? 'true' : undefined}
              data-dirty={isDirty ? 'true' : undefined}
              onClick={() => onSelect(index)}
              onDragOver={(event) => {
                if (!onMove) return
                event.preventDefault()
              }}
              onDrop={(event) => {
                event.preventDefault()
                if (!onMove) return
                const from = Number(event.dataTransfer.getData('text/plain'))
                if (Number.isFinite(from) && from !== index) onMove(from, index)
              }}
            >
              <div className={styles.thumbMeta}>
                <span className={styles.thumbIndex}>{index + 1}</span>
                {onMove ? (
                  <button
                    type="button"
                    className={styles.thumbDrag}
                    title="Drag to reorder"
                    aria-label={`Drag to reorder slide ${index + 1}`}
                    draggable
                    onClick={(event) => event.stopPropagation()}
                    onDragStart={(event) => {
                      event.dataTransfer.setData('text/plain', String(index))
                      event.dataTransfer.effectAllowed = 'move'
                    }}
                  >
                    ⋮⋮
                  </button>
                ) : null}
              </div>
              <div className={styles.thumb}>
                {src ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={src} alt={`Slide ${index + 1}`} draggable={false} />
                ) : (
                  <span className={styles.thumbLabel}>{slide.filename}</span>
                )}
                {(hasNotes || isDirty || isAi) && (
                  <div className={styles.thumbBadges}>
                    {hasNotes && (
                      <span className={styles.thumbBadge} data-kind="notes" title="Has notes">
                        N
                      </span>
                    )}
                    {isDirty && (
                      <span className={styles.thumbBadge} data-kind="dirty" title="Unsaved">
                        •
                      </span>
                    )}
                    {isAi && (
                      <span className={styles.thumbBadge} data-kind="ai" title="AI regenerating">
                        AI
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </aside>
  )
}
