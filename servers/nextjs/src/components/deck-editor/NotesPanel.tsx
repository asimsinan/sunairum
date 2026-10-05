'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Icon from '@/components/Icon'
import { useUI } from '@/lib/i18n'
import {
  fetchNotesTiming,
  fetchSlideNotes,
  fitNotesDuration,
  saveSlideNotes,
  undoNotesFit,
  type NotesTimingReport,
} from './api'
import styles from './deckEditor.module.css'

type Props = {
  projectId: string
  filename?: string
  slideIndex?: number
  slideCount?: number
  prefetchFilenames?: string[]
  open: boolean
  onToggle: () => void
  onRegisterFlush?: (flush: () => Promise<void>) => void
}

type SaveState = 'idle' | 'saving' | 'saved' | 'error'

function slideStem(filename: string): string {
  return filename.replace(/\.(svg|png|html|json|md)$/i, '')
}

function formatSeconds(sec: number): string {
  if (!Number.isFinite(sec) || sec <= 0) return '0:00'
  const m = Math.floor(sec / 60)
  const s = Math.round(sec % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

function countWords(value: string): number {
  const trimmed = value.trim()
  if (!trimmed) return 0
  return trimmed.split(/\s+/).length
}

function emitNoteLoadMetric(
  projectId: string,
  filename: string,
  source: 'cache' | 'network' | 'stale' | 'error',
  startedAt: number,
) {
  if (typeof window === 'undefined' || typeof performance === 'undefined') return
  window.dispatchEvent(
    new CustomEvent('sunairum:note-load', {
      detail: {
        projectId,
        filename,
        source,
        latencyMs: Math.max(0, Math.round(performance.now() - startedAt)),
      },
    }),
  )
}

export default function NotesPanel({
  projectId,
  filename,
  slideIndex = 0,
  slideCount = 0,
  prefetchFilenames = [],
  open,
  onToggle,
  onRegisterFlush,
}: Props) {
  const { t } = useUI()
  const [timing, setTiming] = useState<NotesTimingReport | null>(null)
  const [fitFeedback, setFitFeedback] = useState<string | null>(null)
  const [text, setText] = useState('')
  const [durationMin, setDurationMin] = useState(15)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dirty, setDirty] = useState(false)
  const [saveState, setSaveState] = useState<SaveState>('idle')
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const filenameRef = useRef(filename)
  const pendingRef = useRef<{ file: string; text: string } | null>(null)
  const noteCacheRef = useRef(new Map<string, string>())
  const noteRequestRef = useRef(0)
  const timingProjectRef = useRef<string | null>(null)
  filenameRef.current = filename

  const saveNote = useCallback(
    async (file: string, nextText: string) => {
      noteCacheRef.current.set(file, nextText)
      setBusy(true)
      setSaveState('saving')
      setError(null)
      try {
        const result = await saveSlideNotes(projectId, file, nextText)
        if (pendingRef.current?.file === file && pendingRef.current.text === nextText) {
          pendingRef.current = null
        }
        setTiming(result.timing)
        if (filenameRef.current === file) {
          setDirty(false)
          setSaveState('saved')
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err))
        setSaveState('error')
      } finally {
        setBusy(false)
      }
    },
    [projectId],
  )

  const flushPending = useCallback(async () => {
    if (saveTimer.current) {
      clearTimeout(saveTimer.current)
      saveTimer.current = null
    }
    const pending = pendingRef.current
    if (!pending) return
    await saveNote(pending.file, pending.text)
  }, [saveNote])

  useEffect(() => {
    onRegisterFlush?.(flushPending)
    return () => onRegisterFlush?.(async () => undefined)
  }, [flushPending, onRegisterFlush])

  const load = useCallback(async () => {
    const startedAt = typeof performance === 'undefined' ? 0 : performance.now()
    const requestId = ++noteRequestRef.current
    setError(null)
    // Persisting the previously selected note must never delay switching to
    // the next one. A save is still flushed before fit/export boundaries.
    if (pendingRef.current && pendingRef.current.file !== filename) {
      void flushPending()
    }

    if (!filename) {
      setText('')
      setDirty(false)
      setSaveState('idle')
      return
    }

    const cached = noteCacheRef.current.get(filename)
    if (cached !== undefined) {
      setText(cached)
      setDirty(Boolean(pendingRef.current?.file === filename))
      setSaveState('idle')
      emitNoteLoadMetric(projectId, filename, 'cache', startedAt)
    } else {
      // Clear stale content immediately while the requested note loads.
      setText('')
      setDirty(false)
      setSaveState('idle')
    }

    if (timingProjectRef.current !== projectId) {
      timingProjectRef.current = projectId
      void fetchNotesTiming(projectId)
        .then((report) => {
          if (timingProjectRef.current !== projectId) return
          setTiming(report)
          if (report.target_duration_minutes) {
            setDurationMin(Number(report.target_duration_minutes) || 15)
          }
        })
        .catch((err) => {
          if (noteRequestRef.current === requestId) {
            setError(err instanceof Error ? err.message : String(err))
          }
        })
    }

    if (cached !== undefined) return
    try {
      const note = await fetchSlideNotes(projectId, filename)
      if (noteRequestRef.current !== requestId || filenameRef.current !== filename) {
        emitNoteLoadMetric(projectId, filename, 'stale', startedAt)
        return
      }
      const nextText = note.text || ''
      noteCacheRef.current.set(filename, nextText)
      setText(nextText)
      setDirty(false)
      setSaveState('idle')
      emitNoteLoadMetric(projectId, filename, 'network', startedAt)
    } catch (err) {
      if (noteRequestRef.current !== requestId) {
        emitNoteLoadMetric(projectId, filename, 'stale', startedAt)
        return
      }
      setError(err instanceof Error ? err.message : String(err))
      setSaveState('error')
      emitNoteLoadMetric(projectId, filename, 'error', startedAt)
    }
  }, [filename, flushPending, projectId])

  useEffect(() => {
    noteCacheRef.current.clear()
    timingProjectRef.current = null
    noteRequestRef.current += 1
  }, [projectId])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    let cancelled = false
    for (const file of prefetchFilenames) {
      if (!file || file === filename || noteCacheRef.current.has(file)) continue
      void fetchSlideNotes(projectId, file)
        .then((note) => {
          if (!cancelled) noteCacheRef.current.set(file, note.text || '')
        })
        .catch(() => undefined)
    }
    return () => {
      cancelled = true
    }
  }, [filename, prefetchFilenames, projectId])

  useEffect(() => {
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current)
      const pending = pendingRef.current
      if (pending) {
        void saveSlideNotes(projectId, pending.file, pending.text).catch(() => undefined)
      }
    }
  }, [projectId])

  const slideTiming = useMemo(() => {
    if (!timing || !filename) return null
    const stem = slideStem(filename)
    return (
      timing.slides.find(
        (s) => s.slide_id === stem || slideStem(s.filename || '') === stem || s.filename === filename,
      ) || null
    )
  }, [filename, timing])

  const wordCount = useMemo(() => countWords(text), [text])
  const preview = useMemo(() => {
    const line = text.trim().replace(/\s+/g, ' ')
    if (!line) return t('notesEmpty')
    return line.length > 110 ? `${line.slice(0, 110)}…` : line
  }, [t, text])

  const scheduleSave = useCallback(
    (file: string, nextText: string) => {
      pendingRef.current = { file, text: nextText }
      noteCacheRef.current.set(file, nextText)
      if (saveTimer.current) clearTimeout(saveTimer.current)
      saveTimer.current = setTimeout(() => {
        void saveNote(file, nextText)
      }, 700)
    },
    [saveNote],
  )

  const onFit = useCallback(
    async (minutes: number = durationMin) => {
      await flushPending()
      setBusy(true)
      setError(null)
      setFitFeedback(null)
      try {
        const report = await fitNotesDuration(projectId, {
          target_duration_minutes: minutes,
          wpm: 125,
          mode: 'auto',
          preserve_facts: true,
          backup: true,
        })
        setTiming(report)
        // Fit can rewrite every note, so cached neighbours are no longer valid.
        noteCacheRef.current.clear()
        setDurationMin(Number(report.target_duration_minutes) || minutes)
        const changed = Number(report.changed_slides ?? 0)
        if (changed > 0) {
          setFitFeedback(
            `Rewrote ${changed} slides · target ${report.target_words} words · now ${report.actual_words} words`,
          )
        } else if (report.budget_ok) {
          setFitFeedback('Already on budget — no rewrite needed')
        } else {
          setFitFeedback(
            `Unchanged · target ${report.target_words} words · now ${report.actual_words} words`,
          )
        }
        if (filename) {
          const note = await fetchSlideNotes(projectId, filename)
          const nextText = note.text || ''
          noteCacheRef.current.set(filename, nextText)
          setText(nextText)
          setDirty(false)
          setSaveState('saved')
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err))
        setSaveState('error')
      } finally {
        setBusy(false)
      }
    },
    [durationMin, filename, flushPending, projectId],
  )

  const onUndo = async () => {
    setBusy(true)
    setError(null)
    try {
      const result = await undoNotesFit(projectId)
      setTiming(result.timing)
      noteCacheRef.current.clear()
      if (result.timing.target_duration_minutes) {
        setDurationMin(Number(result.timing.target_duration_minutes) || durationMin)
      }
      if (filename) {
        const note = await fetchSlideNotes(projectId, filename)
        const nextText = note.text || ''
        noteCacheRef.current.set(filename, nextText)
        setText(nextText)
        setDirty(false)
        setSaveState('saved')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setSaveState('error')
    } finally {
      setBusy(false)
    }
  }

  const statusText =
    busy && saveState !== 'saving'
      ? t('notesFitting')
      : saveState === 'saving'
        ? t('notesSaving')
        : saveState === 'saved' && !dirty
          ? t('notesSaved')
          : dirty
            ? t('notesUnsaved')
            : ''

  return (
    <aside
      className={styles.notesDock}
      data-open={open ? 'true' : 'false'}
      aria-label={t('notesPanel')}
      onPointerDown={(e) => e.stopPropagation()}
    >
      <div className={styles.notesBar}>
        <button
          type="button"
          className={styles.notesBarToggle}
          onClick={() => {
            void flushPending()
            onToggle()
          }}
          aria-expanded={open}
        >
          <Icon name="type" className="w-3.5 h-3.5" />
          <strong>{t('notesPanel')}</strong>
          {slideCount > 0 && (
            <span className={styles.notesBarMuted}>
              {slideIndex + 1}/{slideCount}
            </span>
          )}
          {!open && <span className={styles.notesBarPreview}>{preview}</span>}
          <span className={styles.notesBarChevron} data-open={open ? 'true' : 'false'}>
            ▾
          </span>
        </button>
      </div>

      {open && (
        <div className={styles.notesDockBody}>
          <div className={styles.notesToolbar}>
            <div className={styles.notesSeg}>
              {[5, 10, 15, 20].map((min) => (
                <button
                  key={min}
                  type="button"
                  className={styles.notesSegBtn}
                  data-active={durationMin === min ? '1' : '0'}
                  disabled={busy}
                  onClick={() => {
                    setDurationMin(min)
                    void onFit(min)
                  }}
                >
                  {min}m
                </button>
              ))}
            </div>

            <div className={styles.notesToolbarMeta}>
              <span>
                {t('notesTarget')} {durationMin}m
              </span>
              <span className={styles.notesDot}>·</span>
              <span>
                {t('notesEta')} {formatSeconds(timing?.estimated_seconds_total || 0)}
              </span>
              <span className={styles.notesDot}>·</span>
              <span>
                {wordCount}
                {slideTiming?.word_budget != null ? `/${slideTiming.word_budget}` : ''}{' '}
                {t('notesWords')}
              </span>
              {fitFeedback && (
                <>
                  <span className={styles.notesDot}>·</span>
                  <span>{fitFeedback}</span>
                </>
              )}
              {statusText && (
                <>
                  <span className={styles.notesDot}>·</span>
                  <span data-save={saveState}>{statusText}</span>
                </>
              )}
            </div>

            <div className={styles.notesToolbarActions}>
              <button
                type="button"
                className={styles.notesFitBtn}
                disabled={busy || !filename}
                onClick={() => void onFit()}
              >
                {busy && saveState !== 'saving' ? t('notesFitting') : t('notesFit')}
              </button>
              <button
                type="button"
                className={styles.notesGhostBtn}
                disabled={busy}
                onClick={() => void onUndo()}
              >
                {t('notesUndoFit')}
              </button>
            </div>
          </div>

          <textarea
            className={styles.notesDockTextarea}
            value={text}
            placeholder={t('notesPlaceholder')}
            disabled={!filename || (busy && saveState !== 'saving')}
            spellCheck
            onChange={(e) => {
              const next = e.target.value
              setText(next)
              setDirty(true)
              setSaveState('idle')
              if (filename) scheduleSave(filename, next)
            }}
            onBlur={() => {
              void flushPending()
            }}
          />

          {error && <div className={styles.notesError}>{error}</div>}
        </div>
      )}
    </aside>
  )
}
