'use client'

import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import Icon from '@/components/Icon'
import styles from '@/app/history/history.module.css'
import type { LibraryFilter, LibrarySort, LibraryView } from './types'

const FILTERS: LibraryFilter[] = ['all', 'ready', 'draft', 'failed', 'generating']

export default function LibraryToolbar({
  countLabel,
  search,
  onSearch,
  filter,
  onFilter,
  sort,
  onSort,
  view,
  onView,
  onClearAll,
  t,
}: {
  countLabel: string
  search: string
  onSearch: (value: string) => void
  filter: LibraryFilter
  onFilter: (value: LibraryFilter) => void
  sort: LibrarySort
  onSort: (value: LibrarySort) => void
  view: LibraryView
  onView: (value: LibraryView) => void
  onClearAll: () => void
  t: (key: string, vars?: Record<string, string | number>) => string
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const [menuPos, setMenuPos] = useState<{ top: number; left: number } | null>(null)
  const [mounted, setMounted] = useState(false)
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setMounted(true)
  }, [])

  const placeMenu = () => {
    const rect = menuButtonRef.current?.getBoundingClientRect()
    if (!rect) return
    const menuWidth = 200
    const menuHeight = 72
    const pad = 8
    let left = rect.right - menuWidth
    let top = rect.bottom + pad
    left = Math.max(pad, Math.min(left, window.innerWidth - menuWidth - pad))
    if (top + menuHeight > window.innerHeight - pad) {
      top = Math.max(pad, rect.top - menuHeight - pad)
    }
    setMenuPos({ top, left })
  }

  const closeMenu = () => {
    setMenuOpen(false)
    setMenuPos(null)
  }

  const toggleMenu = () => {
    if (menuOpen) {
      closeMenu()
      return
    }
    placeMenu()
    setMenuOpen(true)
  }

  useEffect(() => {
    if (!menuOpen) return
    const onDown = (event: MouseEvent) => {
      const target = event.target as Node
      if (menuButtonRef.current?.contains(target)) return
      if (dropdownRef.current?.contains(target)) return
      closeMenu()
    }
    const onReposition = () => placeMenu()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeMenu()
    }
    // Defer so the opening click does not immediately close the menu.
    const timer = window.setTimeout(() => {
      document.addEventListener('mousedown', onDown)
    }, 0)
    window.addEventListener('resize', onReposition)
    window.addEventListener('scroll', onReposition, true)
    document.addEventListener('keydown', onKey)
    return () => {
      window.clearTimeout(timer)
      document.removeEventListener('mousedown', onDown)
      window.removeEventListener('resize', onReposition)
      window.removeEventListener('scroll', onReposition, true)
      document.removeEventListener('keydown', onKey)
    }
  }, [menuOpen])

  const filterLabel = (id: LibraryFilter) => {
    const map: Record<LibraryFilter, string> = {
      all: 'libraryFilterAll',
      ready: 'libraryFilterReady',
      draft: 'libraryFilterDraft',
      failed: 'libraryFilterFailed',
      generating: 'libraryFilterGenerating',
    }
    return t(map[id])
  }

  const menu =
    mounted &&
    menuOpen &&
    menuPos &&
    createPortal(
      <div
        ref={dropdownRef}
        className={styles.overflowDropdown}
        role="menu"
        style={{ top: menuPos.top, left: menuPos.left }}
      >
        <button
          type="button"
          role="menuitem"
          className={styles.overflowDanger}
          onClick={() => {
            closeMenu()
            onClearAll()
          }}
        >
          <Icon name="trash" className="w-4 h-4" />
          {t('clearAll')}
        </button>
      </div>,
      document.body,
    )

  return (
    <div className={styles.toolbar}>
      <div className={styles.toolbarShell}>
        <div className={styles.toolbarTop}>
          <div className={styles.count}>
            {countLabel}
            <span>{t('workspaceLabel')}</span>
          </div>
          <div className={styles.toolbarRight}>
            <div className={styles.viewToggle} role="group" aria-label={t('libraryViewGrid')}>
              <button
                type="button"
                className={styles.viewButton}
                data-active={view === 'grid'}
                aria-pressed={view === 'grid'}
                title={t('libraryViewGrid')}
                onClick={() => onView('grid')}
              >
                <Icon name="layers" className="w-4 h-4" />
              </button>
              <button
                type="button"
                className={styles.viewButton}
                data-active={view === 'list'}
                aria-pressed={view === 'list'}
                title={t('libraryViewList')}
                onClick={() => onView('list')}
              >
                <Icon name="menu" className="w-4 h-4" />
              </button>
            </div>
            <div className={styles.overflowMenu} data-open={menuOpen}>
              <button
                ref={menuButtonRef}
                type="button"
                className={styles.iconGhost}
                aria-haspopup="menu"
                aria-expanded={menuOpen}
                aria-label={t('libraryMore')}
                onClick={toggleMenu}
              >
                ···
              </button>
              {menu}
            </div>
          </div>
        </div>
        <div className={styles.toolbarControls}>
          <label className={styles.searchField}>
            <Icon name="search" className="w-4 h-4" />
            <input
              type="search"
              value={search}
              onChange={(event) => onSearch(event.target.value)}
              placeholder={t('librarySearchPlaceholder')}
              aria-label={t('librarySearchPlaceholder')}
            />
          </label>
          <div className={styles.filterChips} role="tablist" aria-label={t('libraryFilterAll')}>
            {FILTERS.map((id) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={filter === id}
                className={styles.chip}
                data-active={filter === id}
                onClick={() => onFilter(id)}
              >
                {filterLabel(id)}
              </button>
            ))}
          </div>
          <label className={styles.sortField}>
            <span className={styles.srOnly}>{t('librarySortLastOpened')}</span>
            <select
              value={sort}
              onChange={(event) => onSort(event.target.value as LibrarySort)}
            >
              <option value="last_opened">{t('librarySortLastOpened')}</option>
              <option value="created">{t('librarySortCreated')}</option>
            </select>
          </label>
        </div>
      </div>
    </div>
  )
}
