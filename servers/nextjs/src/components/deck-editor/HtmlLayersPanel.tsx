'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import Icon from '@/components/Icon'
import styles from './deckEditor.module.css'
import type { HtmlLayerItem } from './types'

type Props = {
  layers: HtmlLayerItem[]
  selectedId: string | null
  onSelect: (id: string) => void
  onReorder: (id: string, direction: 'up' | 'down' | 'top' | 'bottom') => void
  onToggleHidden: (id: string, hidden: boolean) => void
}

function buildChildrenMap(layers: HtmlLayerItem[]): Map<string | null, HtmlLayerItem[]> {
  const byParent = new Map<string | null, HtmlLayerItem[]>()
  for (const layer of layers) {
    const key = layer.parentId
    const list = byParent.get(key)
    if (list) list.push(layer)
    else byParent.set(key, [layer])
  }
  // Within each parent, reverse so top-of-stack appears first (inspector convention).
  for (const list of byParent.values()) list.reverse()
  return byParent
}

/** Visible rows given collapse state (parents default collapsed). */
function visibleLayers(
  layers: HtmlLayerItem[],
  byParent: Map<string | null, HtmlLayerItem[]>,
  expanded: Set<string>,
): HtmlLayerItem[] {
  const out: HtmlLayerItem[] = []
  const seen = new Set<string>()
  const walk = (parentId: string | null) => {
    const kids = byParent.get(parentId) || []
    for (const kid of kids) {
      if (seen.has(kid.id)) continue
      seen.add(kid.id)
      out.push(kid)
      const childCount = byParent.get(kid.id)?.length || 0
      if (childCount > 0 && expanded.has(kid.id)) walk(kid.id)
    }
  }
  walk(null)
  // Orphans (parent missing) at root — still shown.
  for (const layer of layers) {
    if (seen.has(layer.id)) continue
    if (layer.parentId && seen.has(layer.parentId) && !expanded.has(layer.parentId)) continue
    seen.add(layer.id)
    out.push(layer)
  }
  return out
}

function kindFor(layer: HtmlLayerItem): string {
  if (layer.tag === 'img' || layer.tag === 'svg' || layer.tag === 'canvas') return 'image'
  if (layer.tag === 'table' || layer.label.toLowerCase().includes('table')) return 'table'
  if (layer.tag === 'td' || layer.tag === 'th') return 'cell'
  const label = layer.label.toLowerCase()
  if (label === 'circle' || label === 'line' || label === 'shape' || label.startsWith('icon')) {
    return 'shape'
  }
  if (layer.tag === 'hr') return 'shape'
  return 'text'
}

export default function HtmlLayersPanel({
  layers,
  selectedId,
  onSelect,
  onReorder,
  onToggleHidden,
}: Props) {
  // Default collapsed: empty set means no parent is expanded.
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set())
  const rowRefs = useRef<Map<string, HTMLButtonElement>>(new Map())

  const byParent = useMemo(() => buildChildrenMap(layers), [layers])
  const byId = useMemo(() => new Map(layers.map((l) => [l.id, l])), [layers])

  // Reveal ancestors when something nested is selected.
  useEffect(() => {
    if (!selectedId) return
    const chain: string[] = []
    let cur: string | null | undefined = selectedId
    const guard = new Set<string>()
    while (cur) {
      if (guard.has(cur)) break
      guard.add(cur)
      const node = byId.get(cur)
      if (!node?.parentId) break
      chain.push(node.parentId)
      cur = node.parentId
    }
    if (chain.length === 0) return
    setExpanded((prev) => {
      let changed = false
      const next = new Set(prev)
      for (const id of chain) {
        if (!next.has(id)) {
          next.add(id)
          changed = true
        }
      }
      return changed ? next : prev
    })
  }, [selectedId, byId])

  // Drop expand state for ids that no longer exist (slide change).
  useEffect(() => {
    setExpanded((prev) => {
      if (prev.size === 0) return prev
      const next = new Set<string>()
      for (const id of prev) {
        if (byId.has(id)) next.add(id)
      }
      return next.size === prev.size ? prev : next
    })
  }, [byId])

  const visible = useMemo(
    () => visibleLayers(layers, byParent, expanded),
    [layers, byParent, expanded],
  )

  // Canvas selection is allowed to originate anywhere on the slide. Once its
  // ancestor chain has been expanded above, keep the corresponding layer row
  // visible without stealing keyboard focus from the canvas.
  useEffect(() => {
    if (!selectedId || !visible.some((layer) => layer.id === selectedId)) return
    const frame = window.requestAnimationFrame(() => {
      rowRefs.current.get(selectedId)?.scrollIntoView({ block: 'nearest' })
    })
    return () => window.cancelAnimationFrame(frame)
  }, [selectedId, visible])

  const toggleExpand = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const expandAll = () => {
    const next = new Set<string>()
    for (const [id, kids] of byParent) {
      if (id && kids.length > 0) next.add(id)
    }
    setExpanded(next)
  }

  const collapseAll = () => setExpanded(new Set())

  return (
    <aside className={styles.layersPanel} aria-label="Layers">
      <div className={styles.layersHeader}>
        <div>
          <div className={styles.layersTitle}>Layers</div>
          <p className={styles.layersSubtitle}>{layers.length} objects</p>
        </div>
        <div className={styles.layersArrange}>
          <button
            type="button"
            className={styles.iconBtn}
            title="Expand all"
            onClick={expandAll}
          >
            ▾
          </button>
          <button
            type="button"
            className={styles.iconBtn}
            title="Collapse all"
            onClick={collapseAll}
          >
            ▸
          </button>
          {selectedId && (
            <>
              <button
                type="button"
                className={styles.iconBtn}
                title="Bring to front"
                onClick={() => onReorder(selectedId, 'top')}
              >
                ⇈
              </button>
              <button
                type="button"
                className={styles.iconBtn}
                title="Bring forward"
                onClick={() => onReorder(selectedId, 'up')}
              >
                ↑
              </button>
              <button
                type="button"
                className={styles.iconBtn}
                title="Send backward"
                onClick={() => onReorder(selectedId, 'down')}
              >
                ↓
              </button>
              <button
                type="button"
                className={styles.iconBtn}
                title="Send to back"
                onClick={() => onReorder(selectedId, 'bottom')}
              >
                ⇊
              </button>
            </>
          )}
        </div>
      </div>
      <ul className={styles.layersList}>
        {visible.length === 0 ? (
          <li>
            <p className={styles.inspectorEmpty}>No selectable layers yet.</p>
          </li>
        ) : (
          visible.map((layer) => {
            const childCount = byParent.get(layer.id)?.length || 0
            const isExpanded = expanded.has(layer.id)
            return (
              <li key={layer.id}>
                <button
                  type="button"
                  ref={(node) => {
                    if (node) rowRefs.current.set(layer.id, node)
                    else rowRefs.current.delete(layer.id)
                  }}
                  className={styles.layerItem}
                  data-active={layer.id === selectedId ? 'true' : undefined}
                  data-hidden={layer.hidden ? 'true' : undefined}
                  aria-selected={layer.id === selectedId}
                  style={{ paddingLeft: `${0.4 + layer.depth * 0.65}rem` }}
                  onClick={() => onSelect(layer.id)}
                >
                  {childCount > 0 ? (
                    <span
                      role="button"
                      tabIndex={0}
                      className={styles.layerDisclosure}
                      data-open={isExpanded ? 'true' : undefined}
                      title={isExpanded ? 'Collapse' : 'Expand'}
                      aria-expanded={isExpanded}
                      onClick={(e) => {
                        e.stopPropagation()
                        toggleExpand(layer.id)
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          e.stopPropagation()
                          toggleExpand(layer.id)
                        }
                      }}
                    >
                      {isExpanded ? '▾' : '▸'}
                    </span>
                  ) : (
                    <span className={styles.layerDisclosureSpacer} aria-hidden="true" />
                  )}
                  <span className={styles.layerIcon} data-kind={kindFor(layer)}>
                    {layer.tag.slice(0, 1).toUpperCase()}
                  </span>
                  <span className={styles.layerLabel} title={layer.label}>
                    {layer.label}
                  </span>
                  <span
                    role="button"
                    tabIndex={0}
                    className={styles.layerEye}
                    title={layer.hidden ? 'Show' : 'Hide'}
                    onClick={(e) => {
                      e.stopPropagation()
                      onToggleHidden(layer.id, !layer.hidden)
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        e.stopPropagation()
                        onToggleHidden(layer.id, !layer.hidden)
                      }
                    }}
                  >
                    <Icon name="eye" className="w-3.5 h-3.5" />
                  </span>
                </button>
              </li>
            )
          })
        )}
      </ul>
    </aside>
  )
}
