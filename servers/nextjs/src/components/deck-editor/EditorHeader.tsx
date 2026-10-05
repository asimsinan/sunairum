'use client'

import { useEffect, useRef, useState } from 'react'
import Icon from '@/components/Icon'
import type { DeckStatus, EditorMode, SaveStatus } from './types'
import styles from './deckEditor.module.css'

type Props = {
  title: string
  saveStatus: SaveStatus
  deckStatus: DeckStatus
  editorMode: EditorMode
  canUndo: boolean
  canRedo: boolean
  exporting: false | 'pptx' | 'previous-pptx' | 'pdf' | 'notes-pdf' | 'html'
  aiBusy?: boolean
  layersOpen?: boolean
  notesOpen?: boolean
  onBack: () => void
  onUndo: () => void
  onRedo: () => void
  onExport: () => void
  onExportPdf: () => void
  onExportNotesPdf?: () => void
  onExportPrevious?: () => void
  onExportHtml?: () => void
  onDuplicate: () => void
  onDelete: () => void
  onRegenerate?: () => void
  onShortcuts: () => void
  onToggleLayers?: () => void
  onToggleNotes?: () => void
  onModeChange: (mode: EditorMode) => void
  onPresent?: () => void
  regenerateLabel?: string
  zoomLabel?: string
  onZoomOut?: () => void
  onZoomIn?: () => void
  onZoomCycle?: () => void
}

function statusLabel(saveStatus: SaveStatus, deckStatus: DeckStatus) {
  if (saveStatus === 'saving') return { text: 'Saving…', tone: 'saving' }
  if (saveStatus === 'dirty') return { text: 'Unsaved changes', tone: 'dirty' }
  if (saveStatus === 'error') return { text: 'Save failed', tone: 'error' }
  if (deckStatus === 'draft_invalid') return { text: 'Needs fixes before export', tone: 'invalid' }
  if (deckStatus === 'draft') return { text: 'Draft', tone: 'dirty' }
  if (saveStatus === 'saved') return { text: 'Saved', tone: 'saved' }
  if (deckStatus === 'done_with_issues') return { text: 'Ready with advisories', tone: 'dirty' }
  return { text: 'Ready', tone: 'saved' }
}

export default function EditorHeader({
  title,
  saveStatus,
  deckStatus,
  editorMode,
  canUndo,
  canRedo,
  exporting,
  aiBusy,
  layersOpen,
  notesOpen,
  onBack,
  onUndo,
  onRedo,
  onExport,
  onExportPdf,
  onExportNotesPdf,
  onExportPrevious,
  onExportHtml,
  onDuplicate,
  onDelete,
  onRegenerate,
  onShortcuts,
  onToggleLayers,
  onToggleNotes,
  onModeChange,
  onPresent,
  regenerateLabel = 'Regenerate',
  zoomLabel,
  onZoomOut,
  onZoomIn,
  onZoomCycle,
}: Props) {
  const chip = statusLabel(saveStatus, deckStatus)
  const busy = Boolean(exporting) || Boolean(aiBusy)
  const [moreOpen, setMoreOpen] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const moreRef = useRef<HTMLDivElement>(null)
  const exportRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!moreOpen && !exportOpen) return
    const onPointerDown = (event: MouseEvent) => {
      const target = event.target as Node
      if (moreOpen && moreRef.current && !moreRef.current.contains(target)) setMoreOpen(false)
      if (exportOpen && exportRef.current && !exportRef.current.contains(target)) setExportOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setMoreOpen(false)
        setExportOpen(false)
      }
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [moreOpen, exportOpen])

  return (
    <header className={styles.header}>
      <div className={styles.headerLeft}>
        <button type="button" className={styles.iconBtn} onClick={onBack} aria-label="Back">
          <Icon name="arrowLeft" className="w-4 h-4" />
        </button>
        <div className={styles.title} title={title}>
          {title}
        </div>
        <span className={styles.statusChip} data-tone={chip.tone}>
          {chip.text}
        </span>
        {aiBusy && (
          <span className={styles.statusChip} data-tone="saving">
            AI…
          </span>
        )}
      </div>

      <div className={styles.headerCenter}>
        <div className={styles.modeSeg} role="tablist" aria-label="Editor mode">
          <button
            type="button"
            role="tab"
            className={styles.modeSegBtn}
            data-active={editorMode === 'refine' ? 'true' : undefined}
            aria-selected={editorMode === 'refine'}
            onClick={() => onModeChange('refine')}
          >
            Refine
          </button>
          <button
            type="button"
            role="tab"
            className={styles.modeSegBtn}
            data-active={editorMode === 'edit' ? 'true' : undefined}
            aria-selected={editorMode === 'edit'}
            onClick={() => onModeChange('edit')}
          >
            Edit
          </button>
        </div>
        <button type="button" className={styles.iconBtn} disabled={!canUndo} onClick={onUndo} aria-label="Undo">
          <Icon name="undo" className="w-4 h-4" />
        </button>
        <button type="button" className={styles.iconBtn} disabled={!canRedo} onClick={onRedo} aria-label="Redo">
          <Icon name="redo" className="w-4 h-4" />
        </button>
        {onZoomOut && onZoomIn && onZoomCycle && (
          <div className={styles.headerZoom} aria-label="Zoom">
            <button type="button" className={styles.iconBtn} onClick={onZoomOut} aria-label="Zoom out">
              <Icon name="zoomOut" className="w-4 h-4" />
            </button>
            <button
              type="button"
              className={styles.headerZoomFit}
              onClick={onZoomCycle}
              title={zoomLabel === 'Fit' ? 'Switch to 100%' : 'Fit to viewport'}
            >
              {zoomLabel || 'Fit'}
            </button>
            <button type="button" className={styles.iconBtn} onClick={onZoomIn} aria-label="Zoom in">
              <Icon name="zoomIn" className="w-4 h-4" />
            </button>
          </div>
        )}
        {editorMode === 'edit' && onToggleLayers && (
          <button
            type="button"
            className={styles.btn}
            data-active={layersOpen}
            onClick={onToggleLayers}
            aria-label="Layers"
          >
            <Icon name="layers" className="w-3.5 h-3.5" />
            <span className={styles.btnLabel}>Layers</span>
          </button>
        )}
        {onToggleNotes && (
          <button
            type="button"
            className={styles.btn}
            data-active={notesOpen}
            onClick={onToggleNotes}
            aria-label="Notes"
          >
            <Icon name="file" className="w-3.5 h-3.5" />
            <span className={styles.btnLabel}>Notes</span>
          </button>
        )}
      </div>

      <div className={styles.headerRight}>
        {onPresent && (
          <button type="button" className={`${styles.btn} ${styles.headerDesktopOnly}`} onClick={onPresent}>
            <Icon name="play" className="w-3.5 h-3.5" />
            <span className={styles.btnLabel}>Present</span>
          </button>
        )}
        <div
          className={`${styles.exportMenu} ${styles.headerDesktopOnly}`}
          ref={exportRef}
          data-open={exportOpen ? 'true' : 'false'}
        >
          <button
            type="button"
            className={`${styles.btn} ${styles.btnSuccess}`}
            disabled={busy}
            aria-haspopup="menu"
            aria-expanded={exportOpen}
            onClick={() => setExportOpen((v) => !v)}
          >
            <Icon name="download" className="w-4 h-4" />
            <span className={styles.btnLabel}>
              {exporting
                ? 'Exporting…'
                : 'Export'}
            </span>
            <span className={styles.exportCaret} aria-hidden="true" />
          </button>
          <div className={styles.exportMenuPanel} role="menu">
            <button
              type="button"
              role="menuitem"
              disabled={busy}
              onClick={() => {
                setExportOpen(false)
                onExport()
              }}
            >
              PowerPoint (.pptx)
            </button>
            <button
              type="button"
              role="menuitem"
              disabled={busy}
              onClick={() => {
                setExportOpen(false)
                onExportPdf()
              }}
            >
              PDF (.pdf)
            </button>
            {onExportNotesPdf && (
              <button
                type="button"
                role="menuitem"
                disabled={busy}
                onClick={() => {
                  setExportOpen(false)
                  onExportNotesPdf()
                }}
              >
                PDF with speaker notes (.pdf)
              </button>
            )}
            {onExportPrevious && (
              <button
                type="button"
                role="menuitem"
                disabled={busy}
                onClick={() => {
                  setExportOpen(false)
                  onExportPrevious()
                }}
              >
                Previous released PowerPoint
              </button>
            )}
            {onExportHtml && (
              <button
                type="button"
                role="menuitem"
                disabled={busy}
                onClick={() => {
                  setExportOpen(false)
                  onExportHtml()
                }}
              >
                HTML player (.zip)
              </button>
            )}
          </div>
        </div>

        <div className={styles.headerMore} ref={moreRef} data-open={moreOpen ? 'true' : 'false'}>
          <button
            type="button"
            className={styles.iconBtn}
            aria-label="More actions"
            aria-expanded={moreOpen}
            onClick={() => setMoreOpen((v) => !v)}
          >
            <Icon name="menu" className="w-4 h-4" />
          </button>
          <div className={styles.headerMoreMenu} role="menu">
            {onPresent && (
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setMoreOpen(false)
                  onPresent()
                }}
              >
                <Icon name="play" className="w-3.5 h-3.5" />
                Present
              </button>
            )}
            <button
              type="button"
              role="menuitem"
              disabled={busy}
              onClick={() => {
                setMoreOpen(false)
                onExport()
              }}
            >
              <Icon name="download" className="w-3.5 h-3.5" />
              {exporting === 'pptx' ? 'Exporting…' : 'Export PPTX'}
            </button>
            <button
              type="button"
              role="menuitem"
              disabled={busy}
              onClick={() => {
                setMoreOpen(false)
                onExportPdf()
              }}
            >
              <Icon name="download" className="w-3.5 h-3.5" />
              {exporting === 'pdf' ? 'Exporting…' : 'Export PDF'}
            </button>
            {onExportNotesPdf && (
              <button
                type="button"
                role="menuitem"
                disabled={busy}
                onClick={() => {
                  setMoreOpen(false)
                  onExportNotesPdf()
                }}
              >
                <Icon name="download" className="w-3.5 h-3.5" />
                {exporting === 'notes-pdf' ? 'Exporting…' : 'Export PDF with notes'}
              </button>
            )}
            {onExportPrevious && (
              <button
                type="button"
                role="menuitem"
                disabled={busy}
                onClick={() => {
                  setMoreOpen(false)
                  onExportPrevious()
                }}
              >
                <Icon name="download" className="w-3.5 h-3.5" />
                {exporting === 'previous-pptx' ? 'Exporting…' : 'Export previous PPTX'}
              </button>
            )}
            {onExportHtml && (
              <button
                type="button"
                role="menuitem"
                disabled={busy}
                onClick={() => {
                  setMoreOpen(false)
                  onExportHtml()
                }}
              >
                <Icon name="download" className="w-3.5 h-3.5" />
                {exporting === 'html' ? 'Exporting…' : 'Export HTML'}
              </button>
            )}
            {onRegenerate && (
              <button
                type="button"
                role="menuitem"
                disabled={busy}
                onClick={() => {
                  setMoreOpen(false)
                  onRegenerate()
                }}
              >
                <Icon name="sparkles" className="w-3.5 h-3.5" />
                {regenerateLabel}
              </button>
            )}
            <button
              type="button"
              role="menuitem"
              disabled={busy}
              onClick={() => {
                setMoreOpen(false)
                onDuplicate()
              }}
            >
              <Icon name="copy" className="w-3.5 h-3.5" />
              Duplicate slide
            </button>
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setMoreOpen(false)
                onDelete()
              }}
            >
              <Icon name="trash" className="w-3.5 h-3.5" />
              Delete slide
            </button>
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setMoreOpen(false)
                onShortcuts()
              }}
            >
              <Icon name="keyboard" className="w-3.5 h-3.5" />
              Shortcuts
            </button>
          </div>
        </div>
      </div>
    </header>
  )
}
