'use client'

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import { useRouter, useSearchParams } from 'next/navigation'
import Icon from '@/components/Icon'
import { API_URL, apiFetch, downloadAuthenticatedFile, exportDeckTransaction, ExportTransactionError } from '@/lib/api'
import { notify } from '@/components/feedback/notify'
import { useUI } from '@/lib/i18n'
import EditorHeader from './EditorHeader'
import HtmlAiRail from './HtmlAiRail'
import HtmlFormatToolbar from './HtmlFormatToolbar'
import HtmlInspector from './HtmlInspector'
import HtmlLayersPanel from './HtmlLayersPanel'
import InsertPopover from './InsertPopover'
import NotesPanel from './NotesPanel'
import PresentMode, { type PresentSlideVisual } from './PresentMode'
import {
  deleteSlide,
  duplicateSlide,
  fetchNotesTiming,
  fetchPreviewMeta,
  fetchRegenerateSlideResult,
  generateAiImage,
  regenerateSlide,
  reorderSlides,
  updateSlideHtml,
  uploadImage,
} from './api'
import EditableHtmlSlide, { type EditableHtmlSlideHandle } from './EditableHtmlSlide'
import { collectLayersFromHtml } from './htmlLayers'
import type { InsertKind } from './insertKinds'
import SlideStrip from './SlideStrip'
import SlideStage, { HtmlSlideFrame, SLIDE_STAGE_H, SLIDE_STAGE_W } from './SlideStage'
import type { DeckStatus, EditorMode, HtmlLayerItem, HtmlSelection, HtmlStylePatch, SaveStatus, SlideInfo } from './types'
import styles from './deckEditor.module.css'

type Props = {
  projectId: string
  title?: string
  initialSlides: SlideInfo[]
}

const ZOOM_MIN = 0.25
const ZOOM_MAX = 3
const ZOOM_STEP = 0.1

function slideStem(filename: string): string {
  return filename.replace(/\.(json|png|svg|html|md)$/i, '')
}

function htmlUrlForSlide(slide: SlideInfo | undefined): string | null {
  if (!slide) return null
  if (slide.html_url) {
    return slide.html_url.startsWith('http')
      ? slide.html_url.replace(/^https?:\/\/[^/]+/, '')
      : slide.html_url.split('?')[0]
  }
  const url = slide.url || ''
  const path = url.startsWith('http') ? url.replace(/^https?:\/\/[^/]+/, '') : url
  const replaced = path.replace(/\/preview\/(slide_\d+)\.png/i, '/html_output/$1.html')
  if (replaced !== path) return replaced.split('?')[0]
  const m = path.match(/^(\/api\/files\/[^/]+\/[^/]+)\//)
  if (m) return `${m[1]}/html_output/${slideStem(slide.filename)}.html`
  return null
}

async function fetchTextAuth(path: string): Promise<string | null> {
  try {
    const res = await apiFetch(path)
    if (!res.ok) return null
    return await res.text()
  } catch {
    return null
  }
}

async function fetchBlobUrlAuth(path: string): Promise<string | null> {
  try {
    const res = await apiFetch(path)
    if (!res.ok) return null
    const blob = await res.blob()
    return URL.createObjectURL(blob)
  } catch {
    return null
  }
}

/** Parse `?slide=` as a 0-based index (main editor lightbox passes livePreviewIndex). */
function parseSlideQueryIndex(raw: string | null, slideCount: number): number {
  if (!slideCount) return 0
  if (raw == null || raw === '') return 0
  const n = Number(raw)
  if (!Number.isFinite(n)) return 0
  const idx = Math.trunc(n)
  if (idx < 0) return 0
  if (idx >= slideCount) return slideCount - 1
  return idx
}

export default function HtmlEditorShell({ projectId, title, initialSlides }: Props) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { t } = useUI()
  const [slides, setSlides] = useState(initialSlides)
  const [activeIndex, setActiveIndex] = useState(() =>
    parseSlideQueryIndex(searchParams.get('slide'), initialSlides.length),
  )
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const [exporting, setExporting] = useState<
    false | 'pptx' | 'previous-pptx' | 'pdf' | 'notes-pdf' | 'html'
  >(false)
  const [deckStatus, setDeckStatus] = useState<DeckStatus>('done')
  const [previousReleaseAvailable, setPreviousReleaseAvailable] = useState(false)
  const [shortcutsOpen, setShortcutsOpen] = useState(false)
  const [editorMode, setEditorMode] = useState<EditorMode>('edit')
  const [layersPinned, setLayersPinned] = useState(true)
  const [selection, setSelection] = useState<HtmlSelection | null>(null)
  const [layers, setLayers] = useState<HtmlLayerItem[]>([])
  const [notesPresence, setNotesPresence] = useState<Record<string, boolean>>({})
  const [dirtySlides, setDirtySlides] = useState<Record<string, boolean>>({})
  const [notesOpen, setNotesOpen] = useState(false)
  const [presenting, setPresenting] = useState(false)
  const [zoomMode, setZoomMode] = useState<'fit' | 'manual'>('fit')
  const [fitScale, setFitScale] = useState(1)
  const [manualZoom, setManualZoom] = useState(1)
  const [slideHtml, setSlideHtml] = useState<string | null>(null)
  /** Filename that `slideHtml` belongs to — prevents showing the previous slide after a switch. */
  const [slideHtmlFile, setSlideHtmlFile] = useState<string | null>(null)
  const [slidePngUrl, setSlidePngUrl] = useState<string | null>(null)
  const [slidePngFile, setSlidePngFile] = useState<string | null>(null)
  const [slideVisualLoading, setSlideVisualLoading] = useState(true)
  const [visualsByFile, setVisualsByFile] = useState<Record<string, PresentSlideVisual>>({})
  const visualsByFileRef = useRef<Record<string, PresentSlideVisual>>({})
  const [visualReloadKey, setVisualReloadKey] = useState(0)
  const loadGenRef = useRef(0)
  const [regenOpen, setRegenOpen] = useState(false)
  const [regenFeedback, setRegenFeedback] = useState('')
  const [regenBusy, setRegenBusy] = useState(false)
  const [regenError, setRegenError] = useState('')
  const [regenChips, setRegenChips] = useState<string[]>([])
  const [insertOpen, setInsertOpen] = useState(false)
  const [formatToolbarPos, setFormatToolbarPos] = useState<{ left: number; top: number } | null>(null)
  const [undoStack, setUndoStack] = useState<string[]>([])
  const [redoStack, setRedoStack] = useState<string[]>([])

  const canvasHostRef = useRef<HTMLDivElement | null>(null)
  const canvasStageRef = useRef<HTMLDivElement | null>(null)
  const slidePngRef = useRef<string | null>(null)
  const regenStartedAt = useRef(0)
  const editorRef = useRef<EditableHtmlSlideHandle | null>(null)
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const flushSaveRef = useRef<() => Promise<void>>(async () => undefined)
  const flushNotesRef = useRef<() => Promise<void>>(async () => undefined)
  const lastSavedHtmlRef = useRef<string | null>(null)
  const lastSavedByFileRef = useRef<Record<string, string>>({})
  const activeFileRef = useRef<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const applyingHistoryRef = useRef(false)

  const active = slides[activeIndex]
  const activeFile = active?.filename || null
  activeFileRef.current = activeFile
  const displayHtml =
    slideHtml && slideHtmlFile && activeFile && slideHtmlFile === activeFile ? slideHtml : null
  const displayPngUrl =
    slidePngUrl && slidePngFile && activeFile && slidePngFile === activeFile ? slidePngUrl : null
  const scale = zoomMode === 'fit' ? fitScale : manualZoom
  const layersOpen =
    editorMode === 'edit' && (layersPinned || Boolean(selection) || layers.length > 0)

  useEffect(() => {
    visualsByFileRef.current = visualsByFile
  }, [visualsByFile])

  const clearVisualCache = useCallback(() => {
    // Filename keys are identity; after reorder/delete/duplicate they are renumbered.
    setVisualsByFile({})
    visualsByFileRef.current = {}
    lastSavedByFileRef.current = {}
    lastSavedHtmlRef.current = null
  }, [])

  const registerNotesFlush = useCallback((flush: () => Promise<void>) => {
    flushNotesRef.current = flush
  }, [])

  const refreshLayers = useCallback(() => {
    // Prefer live iframe DOM (ids after assignSunIds); fall back to parsing slide HTML
    // so Layers never sticks at 0 while the iframe is still loading.
    const live = editorRef.current?.listLayers() || []
    if (live.length > 0) {
      setLayers(live)
      return live
    }
    const fromHtml = collectLayersFromHtml(displayHtml)
    setLayers(fromHtml)
    return fromHtml
  }, [displayHtml])

  /** Retry until the iframe has painted selectable nodes (slide switches race onLoad). */
  const refreshLayersUntilReady = useCallback(
    (attempts = 40) => {
      let cancelled = false
      let left = attempts
      const tick = () => {
        if (cancelled) return
        const next = refreshLayers()
        left -= 1
        // HTML fallback already fills the list; keep polling for live iframe ids.
        if (left <= 0) return
        if (next.length > 0 && (editorRef.current?.listLayers()?.length || 0) > 0) return
        window.setTimeout(tick, 50)
      }
      tick()
      return () => {
        cancelled = true
      }
    },
    [refreshLayers],
  )

  const onSelectionChange = useCallback(
    (sel: HtmlSelection | null) => {
      setSelection(sel)
      refreshLayers()
    },
    [refreshLayers],
  )

  // Populate layers from HTML immediately on slide change (no iframe wait).
  useEffect(() => {
    if (editorMode !== 'edit' || !displayHtml || !activeFile) {
      if (editorMode !== 'edit') setLayers([])
      return
    }
    setLayers(collectLayersFromHtml(displayHtml))
    return refreshLayersUntilReady()
  }, [activeFile, displayHtml, editorMode, refreshLayersUntilReady, visualReloadKey])

  const refreshSlides = useCallback(async () => {
    const meta = await fetchPreviewMeta(projectId)
    setSlides(meta.slides)
    if (meta.status) setDeckStatus(meta.status)
    setPreviousReleaseAvailable(Boolean(meta.previousReleaseAvailable))
    return meta.slides
  }, [projectId])

  useEffect(() => {
    void refreshSlides().catch(() => undefined)
  }, [refreshSlides])

  const loadSlideVisual = useCallback(async (slide: SlideInfo, opts?: { wantPng?: boolean }) => {
    const htmlPath = htmlUrlForSlide(slide)
    const html = htmlPath ? await fetchTextAuth(htmlPath) : null

    let pngBlob: string | null = null
    // Prefer HTML for the canvas; only fetch PNG when HTML is missing or explicitly requested.
    if ((!html || opts?.wantPng) && slide.url) {
      const pngPath = slide.url.startsWith('http')
        ? slide.url
        : `${slide.url.startsWith('/') ? '' : '/'}${slide.url}`
      const path = pngPath.startsWith('http')
        ? pngPath.replace(/^https?:\/\/[^/]+/, '')
        : pngPath
      // Skip re-fetching HTML as a "png" when url already points at html_output.
      if (path && !/\/html_output\/[^/]+\.html/i.test(path)) {
        pngBlob = await fetchBlobUrlAuth(path)
      }
    }

    return { html, pngUrl: pngBlob }
  }, [])

  const applySlideVisual = useCallback(
    (filename: string, html: string | null, pngUrl: string | null, opts?: { resetHistory?: boolean }) => {
      if (slidePngRef.current && slidePngRef.current !== pngUrl) {
        URL.revokeObjectURL(slidePngRef.current)
        slidePngRef.current = null
      }
      if (pngUrl) slidePngRef.current = pngUrl
      setSlideHtml(html)
      setSlideHtmlFile(html ? filename : null)
      setSlidePngUrl(pngUrl)
      setSlidePngFile(pngUrl ? filename : null)
      setSlideVisualLoading(false)
      if (opts?.resetHistory !== false) {
        setUndoStack(html ? [html] : [])
        setRedoStack([])
        if (html) lastSavedByFileRef.current[filename] = html
        lastSavedHtmlRef.current = html
        setSaveStatus('idle')
      }
      setSelection(null)
      setLayers(html ? collectLayersFromHtml(html) : [])
      setVisualsByFile((prev) => ({
        ...prev,
        [filename]: {
          html: html ?? prev[filename]?.html ?? null,
          pngUrl: pngUrl ?? prev[filename]?.pngUrl ?? null,
        },
      }))
    },
    [],
  )

  const reloadKeyRef = useRef(visualReloadKey)

  // Load HTML for active slide (canvas + regen preview).
  useEffect(() => {
    const slide = activeFile ? slides.find((s) => s.filename === activeFile) : undefined
    if (!slide || !activeFile) {
      setSlideHtml(null)
      setSlideHtmlFile(null)
      setSlidePngUrl(null)
      setSlidePngFile(null)
      setSlideVisualLoading(false)
      return
    }

    const forceReload = reloadKeyRef.current !== visualReloadKey
    reloadKeyRef.current = visualReloadKey

    const cached = visualsByFileRef.current[activeFile]
    if (!forceReload && cached?.html && slideHtmlFile === activeFile) {
      // Already showing the right slide (e.g. instant cache in selectSlide).
      setSlideVisualLoading(false)
      return
    }
    if (!forceReload && cached?.html) {
      applySlideVisual(activeFile, cached.html, cached.pngUrl || null)
      return
    }

    const gen = ++loadGenRef.current
    setSlideVisualLoading(true)
    ;(async () => {
      const { html, pngUrl } = await loadSlideVisual(slide)
      if (gen !== loadGenRef.current) {
        if (pngUrl) URL.revokeObjectURL(pngUrl)
        return
      }
      applySlideVisual(activeFile, html, pngUrl)
    })()
  }, [activeFile, applySlideVisual, loadSlideVisual, slideHtmlFile, slides, visualReloadKey])

  // Prefetch neighbors so strip clicks feel instant after the first visit.
  useEffect(() => {
    if (!activeFile) return
    const idx = slides.findIndex((s) => s.filename === activeFile)
    if (idx < 0) return
    const neighbors = [slides[idx - 1], slides[idx + 1]].filter(Boolean) as SlideInfo[]
    let cancelled = false
    ;(async () => {
      for (const slide of neighbors) {
        if (visualsByFileRef.current[slide.filename]?.html) continue
        const visual = await loadSlideVisual(slide)
        if (cancelled) {
          if (visual.pngUrl) URL.revokeObjectURL(visual.pngUrl)
          return
        }
        if (!visual.html) continue
        setVisualsByFile((prev) => {
          if (prev[slide.filename]?.html) return prev
          return { ...prev, [slide.filename]: visual }
        })
      }
    })()
    return () => {
      cancelled = true
    }
  }, [activeFile, loadSlideVisual, slides])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const timing = await fetchNotesTiming(projectId)
        if (cancelled) return
        const next: Record<string, boolean> = {}
        for (const row of timing.slides || []) {
          const has = Boolean((row.notes || '').trim()) || (row.word_count || 0) > 0
          if (row.filename) next[row.filename] = has
          if (row.slide_id) next[row.slide_id] = has
        }
        setNotesPresence(next)
      } catch {
        /* notes badges optional */
      }
    })()
    return () => {
      cancelled = true
    }
  }, [projectId, visualReloadKey])

  useEffect(() => {
    return () => {
      if (slidePngRef.current) URL.revokeObjectURL(slidePngRef.current)
    }
  }, [])

  // Prefetch visuals for Present mode when opened.
  useEffect(() => {
    if (!presenting) return
    let cancelled = false
    ;(async () => {
      const next: Record<string, PresentSlideVisual> = { ...visualsByFile }
      await Promise.all(
        slides.map(async (slide) => {
          if (next[slide.filename]?.html || next[slide.filename]?.pngUrl) return
          const visual = await loadSlideVisual(slide)
          if (!cancelled) next[slide.filename] = visual
        }),
      )
      if (!cancelled) setVisualsByFile(next)
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presenting])

  const bumpZoom = useCallback(
    (delta: number) => {
      setZoomMode('manual')
      setManualZoom((prev) => {
        const base = zoomMode === 'fit' ? fitScale : prev
        return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.round((base + delta) * 100) / 100))
      })
    },
    [fitScale, zoomMode],
  )

  // Fit scale from the visible stage (above zoom bar / AI rail), not a stale SlideStage host.
  useLayoutEffect(() => {
    const stage = canvasStageRef.current
    if (!stage) return
    const measure = () => {
      const style = getComputedStyle(stage)
      const padX =
        (parseFloat(style.paddingLeft) || 0) + (parseFloat(style.paddingRight) || 0)
      const padY =
        (parseFloat(style.paddingTop) || 0) + (parseFloat(style.paddingBottom) || 0)
      const hw = Math.max(0, stage.clientWidth - padX)
      const hh = Math.max(0, stage.clientHeight - padY)
      const next = Math.min(hw / SLIDE_STAGE_W, hh / SLIDE_STAGE_H)
      if (!Number.isFinite(next) || next <= 0) return
      const rounded = Math.round(next * 1000) / 1000
      setFitScale((prev) => (Math.abs(prev - rounded) < 0.002 ? prev : rounded))
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(stage)
    return () => ro.disconnect()
  }, [editorMode, notesOpen, layersOpen])

  const cycleZoomFit = useCallback(() => {
    if (zoomMode === 'fit') {
      setZoomMode('manual')
      setManualZoom(1)
    } else {
      setZoomMode('fit')
    }
  }, [zoomMode])

  const handleExportTransactionFailure = async (error: unknown) => {
    if (!(error instanceof ExportTransactionError)) return
    setPreviousReleaseAvailable(error.previousReleaseAvailable)
    if (!error.previousReleaseAvailable) return
    const accepted = await notify.confirm({
      title: 'Current export could not be rebuilt',
      message: `${error.message}\n\nDownload the explicitly labelled previous immutable release instead?`,
      confirmLabel: 'Download previous release',
      cancelLabel: 'Cancel',
    })
    if (accepted) {
      await downloadAuthenticatedFile(
        error.previousReleaseUrl || `${API_URL}/api/download/${projectId}.previous.pptx`,
        `${title || projectId}-previous.pptx`,
      )
    }
  }

  const exportPptx = async () => {
    setExporting('pptx')
    try {
      await Promise.all([flushSaveRef.current(), flushNotesRef.current()])
      await exportDeckTransaction(projectId, 'pptx', `${title || projectId}.pptx`)
      setDeckStatus('done')
      setPreviousReleaseAvailable(false)
      notify.toast({ message: 'PPTX exported', tone: 'success' })
    } catch (e) {
      setDeckStatus('draft_invalid')
      await handleExportTransactionFailure(e)
      notify.toast({ message: String(e), tone: 'error' })
    } finally {
      setExporting(false)
    }
  }

  const exportPdf = async () => {
    setExporting('pdf')
    try {
      await Promise.all([flushSaveRef.current(), flushNotesRef.current()])
      await exportDeckTransaction(projectId, 'pdf', `${title || projectId}.pdf`)
      setDeckStatus('done')
      setPreviousReleaseAvailable(false)
      notify.toast({ message: 'PDF exported', tone: 'success' })
    } catch (e) {
      setDeckStatus('draft_invalid')
      await handleExportTransactionFailure(e)
      notify.toast({ message: String(e), tone: 'error' })
    } finally {
      setExporting(false)
    }
  }

  const exportNotesPdf = async () => {
    setExporting('notes-pdf')
    try {
      await Promise.all([flushSaveRef.current(), flushNotesRef.current()])
      await exportDeckTransaction(projectId, 'notes-pdf', `${title || projectId}-notes.pdf`)
      setDeckStatus('done')
      setPreviousReleaseAvailable(false)
      notify.toast({ message: 'PDF with speaker notes exported', tone: 'success' })
    } catch (e) {
      setDeckStatus('draft_invalid')
      await handleExportTransactionFailure(e)
      notify.toast({ message: String(e), tone: 'error' })
    } finally {
      setExporting(false)
    }
  }

  const exportPreviousPptx = async () => {
    setExporting('previous-pptx')
    try {
      await downloadAuthenticatedFile(
        `${API_URL}/api/download/${projectId}.previous.pptx`,
        `${title || projectId}-previous.pptx`,
      )
      notify.toast({ message: 'Previous released PPTX exported', tone: 'success' })
    } catch (e) {
      notify.toast({ message: String(e), tone: 'error' })
    } finally {
      setExporting(false)
    }
  }

  const exportHtml = async () => {
    setExporting('html')
    try {
      await Promise.all([flushSaveRef.current(), flushNotesRef.current()])
      await downloadAuthenticatedFile(
        `${API_URL}/api/download/${projectId}.html.zip`,
        `${title || projectId}-html.zip`,
      )
      notify.toast({ message: 'HTML player exported', tone: 'success' })
    } catch (e) {
      notify.toast({ message: String(e), tone: 'error' })
    } finally {
      setExporting(false)
    }
  }

  const waitForRegenerateDone = useCallback(
    async (slideNumber: number, startedAt: number) => {
      const deadline = Date.now() + 180_000
      while (Date.now() < deadline) {
        try {
          const result = await fetchRegenerateSlideResult(projectId)
          if (
            result.ok &&
            Number(result.slide) === slideNumber &&
            Number(result.ts || 0) >= startedAt - 2
          ) {
            return result
          }
        } catch {
          /* keep polling */
        }
        await new Promise((r) => setTimeout(r, 1200))
      }
      throw new Error(t('regenerateSlideFailed'))
    },
    [projectId, t],
  )

  const appendRegenChip = useCallback((key: string, chipText: string) => {
    setRegenChips((prev) => (prev.includes(key) ? prev : [...prev, key]))
    setRegenFeedback((prev) => {
      const trimmed = prev.trim()
      if (!trimmed) return chipText
      if (trimmed.toLowerCase().includes(chipText.toLowerCase())) return prev
      return `${trimmed}${trimmed.endsWith('.') || trimmed.endsWith(';') ? ' ' : '; '}${chipText}`
    })
  }, [])

  const onConfirmRegenerate = useCallback(async () => {
    if (!active || regenBusy) return
    const feedback = regenFeedback.trim()
    if (!feedback) {
      setRegenError(t('regenerateSlideLabel'))
      return
    }
    const match = active.filename.match(/slide_(\d+)/i)
    const slideNumber = match ? Number(match[1]) : activeIndex + 1
    setRegenError('')
    setRegenBusy(true)
    regenStartedAt.current = Math.floor(Date.now() / 1000)
    try {
      await regenerateSlide(projectId, slideNumber, feedback)
      await waitForRegenerateDone(slideNumber, regenStartedAt.current)
      await refreshSlides()
      setVisualsByFile((prev) => {
        const next = { ...prev }
        delete next[active.filename]
        return next
      })
      setVisualReloadKey((k) => k + 1)
      setRegenOpen(false)
      setRegenFeedback('')
      setRegenChips([])
      notify.toast({ message: t('regenerateSlideSuccess'), tone: 'success' })
    } catch (err) {
      setRegenError(err instanceof Error ? err.message : t('regenerateSlideFailed'))
    } finally {
      setRegenBusy(false)
    }
  }, [
    active,
    activeIndex,
    projectId,
    refreshSlides,
    regenBusy,
    regenFeedback,
    t,
    waitForRegenerateDone,
  ])

  const enterPresent = useCallback(() => {
    flushSync(() => setPresenting(true))
  }, [])

  const exitPresent = useCallback(() => {
    setPresenting(false)
  }, [])

  const persistHtml = useCallback(
    async (html: string, filename: string) => {
      if (!html || !filename) return
      // Edits must never rename/reorder — only overwrite that exact stem.
      if (!/^slide_\d+\.html$/i.test(filename)) return
      if (html === lastSavedByFileRef.current[filename]) {
        if (activeFileRef.current === filename) setSaveStatus('saved')
        setDirtySlides((prev) => {
          if (!prev[filename]) return prev
          const next = { ...prev }
          delete next[filename]
          return next
        })
        return
      }
      if (activeFileRef.current === filename) setSaveStatus('saving')
      try {
        const saved = await updateSlideHtml(projectId, filename, html, true)
        lastSavedByFileRef.current[filename] = html
        if (activeFileRef.current === filename) {
          lastSavedHtmlRef.current = html
          setSaveStatus('saved')
        }
        setDirtySlides((prev) => {
          if (!prev[filename]) return prev
          const next = { ...prev }
          delete next[filename]
          return next
        })
        setVisualsByFile((prev) => ({
          ...prev,
          [filename]: { ...(prev[filename] || {}), html },
        }))
        // Free-form saves are never failures. Keep the draft editable and
        // defer layout remediation/validation to the export transaction.
        setDeckStatus('draft')
        setPreviousReleaseAvailable(Boolean(saved.previous_release_available))
      } catch (err) {
        if (activeFileRef.current === filename) setSaveStatus('error')
        notify.toast({
          message: err instanceof Error ? err.message : 'Failed to save slide',
          tone: 'error',
        })
      }
    },
    [projectId],
  )

  const flushSave = useCallback(async () => {
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current)
      saveTimerRef.current = null
    }
    const html = editorRef.current?.getHtml() || slideHtml
    const file = active?.filename
    if (!html || !file || slideHtmlFile !== file) return
    await persistHtml(html, file)
  }, [active?.filename, persistHtml, slideHtml, slideHtmlFile])
  flushSaveRef.current = flushSave

  const selectSlide = useCallback(
    (idx: number) => {
      if (idx === activeIndex) return
      const prev = slides[activeIndex]
      // Only save when the live editor still belongs to the previous filename.
      // Never write into another stem and never trigger reorder from navigation.
      if (prev?.filename && slideHtmlFile === prev.filename) {
        const prevHtml = editorRef.current?.getHtml() || slideHtml
        if (prevHtml) {
          if (saveTimerRef.current) {
            clearTimeout(saveTimerRef.current)
            saveTimerRef.current = null
          }
          setVisualsByFile((cache) => ({
            ...cache,
            [prev.filename]: { ...(cache[prev.filename] || {}), html: prevHtml },
          }))
          void persistHtml(prevHtml, prev.filename)
        }
      }

      const next = slides[idx]
      setActiveIndex(idx)
      setSelection(null)
      if (editorMode === 'edit') setLayersPinned(true)
      if (!next) {
        setSlideHtml(null)
        setSlideHtmlFile(null)
        setSlidePngUrl(null)
        setSlidePngFile(null)
        setSlideVisualLoading(false)
        setLayers([])
        return
      }

      const cached = visualsByFileRef.current[next.filename]
      if (cached?.html) {
        applySlideVisual(next.filename, cached.html, cached.pngUrl || null)
      } else {
        // Clear ownership so the previous slide cannot paint under the new key.
        setSlideHtml(null)
        setSlideHtmlFile(null)
        setSlidePngUrl(null)
        setSlidePngFile(null)
        setSlideVisualLoading(true)
        setLayers([])
        setUndoStack([])
        setRedoStack([])
      }
    },
    [activeIndex, applySlideVisual, editorMode, persistHtml, slideHtml, slideHtmlFile, slides],
  )

  const onDuplicateSlide = useCallback(async () => {
    if (!active) return
    try {
      await flushSave()
      await duplicateSlide(projectId, active.filename)
      clearVisualCache()
      setSlideHtml(null)
      setSlideHtmlFile(null)
      const next = await refreshSlides()
      const idx = next.findIndex((s) => s.filename === active.filename)
      setActiveIndex(Math.min(idx + 1, next.length - 1))
      notify.toast({ message: 'Slide duplicated', tone: 'success' })
    } catch (err) {
      notify.toast({
        message: err instanceof Error ? err.message : 'Duplicate failed',
        tone: 'error',
      })
      clearVisualCache()
      await refreshSlides()
    }
  }, [active, clearVisualCache, flushSave, projectId, refreshSlides])

  const onDeleteSlide = useCallback(async () => {
    if (!active || slides.length <= 1) return
    if (
      !(await notify.confirm({
        title: t('delete'),
        message: t('confirmDeleteSlide'),
        tone: 'danger',
        confirmLabel: t('delete'),
        cancelLabel: t('cancel'),
      }))
    ) {
      return
    }
    const deleting = active.filename
    const deleteAt = activeIndex
    try {
      await flushSave()
      await deleteSlide(projectId, deleting)
      clearVisualCache()
      setSlideHtml(null)
      setSlideHtmlFile(null)
      setActiveIndex(Math.min(deleteAt, Math.max(slides.length - 2, 0)))
      await refreshSlides()
    } catch (err) {
      notify.toast({
        message: err instanceof Error ? err.message : 'Delete failed',
        tone: 'error',
      })
      clearVisualCache()
      await refreshSlides()
    }
  }, [active, activeIndex, clearVisualCache, flushSave, projectId, refreshSlides, slides.length, t])

  const onMoveSlide = useCallback(
    async (from: number, to: number) => {
      if (from === to) return
      await flushSave()
      const next = [...slides]
      const [item] = next.splice(from, 1)
      next.splice(to, 0, item)
      // Disk renumbers stems (slide_01…) — drop filename-keyed caches before refresh.
      clearVisualCache()
      setSlideHtml(null)
      setSlideHtmlFile(null)
      setSlides(next)
      setActiveIndex(to)
      try {
        await reorderSlides(
          projectId,
          next.map((s) => s.filename),
        )
        await refreshSlides()
      } catch (err) {
        notify.toast({
          message: err instanceof Error ? err.message : 'Reorder failed',
          tone: 'error',
        })
        clearVisualCache()
        await refreshSlides()
      }
    },
    [clearVisualCache, flushSave, projectId, refreshSlides, slides],
  )

  const onEditorDirty = useCallback(
    (html: string) => {
      if (applyingHistoryRef.current) return
      setSlideHtml(html)
      if (active?.filename) setSlideHtmlFile(active.filename)
      setSaveStatus('dirty')
      setDeckStatus('draft')
      const file = active?.filename
      if (file) {
        setDirtySlides((prev) => (prev[file] ? prev : { ...prev, [file]: true }))
        setVisualsByFile((prev) => ({
          ...prev,
          [file]: { ...(prev[file] || {}), html },
        }))
      }
      setUndoStack((prev) => {
        const last = prev[prev.length - 1]
        if (last === html) return prev
        const next = [...prev, html]
        return next.length > 40 ? next.slice(next.length - 40) : next
      })
      setRedoStack([])
      refreshLayers()
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
      if (!file) return
      saveTimerRef.current = setTimeout(() => {
        void persistHtml(html, file)
      }, 900)
    },
    [active?.filename, persistHtml, refreshLayers],
  )

  const applyStyle = useCallback(
    (patch: HtmlStylePatch) => {
      editorRef.current?.applyStyle(patch)
      refreshLayers()
    },
    [refreshLayers],
  )

  const onModeChange = useCallback(
    (mode: EditorMode) => {
      setEditorMode(mode)
      if (mode === 'edit') {
        setLayersPinned(true)
        setInsertOpen(false)
        refreshLayersUntilReady()
      } else {
        setLayersPinned(false)
        setInsertOpen(false)
        setNotesOpen(false)
      }
    },
    [refreshLayersUntilReady],
  )

  const onUndo = useCallback(() => {
    setUndoStack((prev) => {
      if (prev.length < 2) return prev
      const current = prev[prev.length - 1]
      const prior = prev[prev.length - 2]
      setRedoStack((r) => [...r, current])
      applyingHistoryRef.current = true
      editorRef.current?.setHtml(prior)
      setSlideHtml(prior)
      setSaveStatus('dirty')
      const file = active?.filename
      if (file) {
        if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
        saveTimerRef.current = setTimeout(() => {
          applyingHistoryRef.current = false
          void persistHtml(prior, file)
        }, 400)
      } else {
        applyingHistoryRef.current = false
      }
      return prev.slice(0, -1)
    })
  }, [active?.filename, persistHtml])

  const onRedo = useCallback(() => {
    setRedoStack((prev) => {
      if (!prev.length) return prev
      const next = prev[prev.length - 1]
      setUndoStack((u) => [...u, next])
      applyingHistoryRef.current = true
      editorRef.current?.setHtml(next)
      setSlideHtml(next)
      setSaveStatus('dirty')
      const file = active?.filename
      if (file) {
        if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
        saveTimerRef.current = setTimeout(() => {
          applyingHistoryRef.current = false
          void persistHtml(next, file)
        }, 400)
      } else {
        applyingHistoryRef.current = false
      }
      return prev.slice(0, -1)
    })
  }, [active?.filename, persistHtml])

  const onInsertKind = useCallback(
    (kind: InsertKind) => {
      // Free-form DOM insert only — never open the regenerate modal from Insert.
      setInsertOpen(false)
      setRegenOpen(false)
      if (kind === 'image') {
        fileInputRef.current?.click()
        return
      }
      if (kind === 'ai_image') {
        void (async () => {
          try {
            setSaveStatus('saving')
            const match = active?.filename.match(/slide_(\d+)/i)
            const slideNumber = match ? Number(match[1]) : activeIndex + 1
            const generated = await generateAiImage(projectId, {
              prompt: 'Editorial illustration supporting this slide topic, clean and on-brand',
              aspect_ratio: '16:9',
              slide: slideNumber,
            })
            const url = generated.url?.startsWith('http')
              ? generated.url.replace(/^https?:\/\/[^/]+/, '')
              : generated.url
            const abs = url?.startsWith('/') ? url : `/${url || ''}`
            const ok = editorRef.current?.insertKind('ai_image', { imageUrl: abs })
            if (!ok) throw new Error('Could not insert image — wait for the slide HTML to load')
            setSaveStatus('saved')
            editorRef.current?.focus()
            notify.toast({ message: 'AI image inserted', tone: 'success' })
          } catch (err) {
            setSaveStatus('error')
            notify.toast({
              message: err instanceof Error ? err.message : 'AI image failed',
              tone: 'error',
            })
          }
        })()
        return
      }
      const ok = editorRef.current?.insertKind(kind)
      if (!ok) {
        notify.toast({
          message: 'Slide HTML is not ready yet — wait a moment, then try Insert again',
          tone: 'error',
        })
        return
      }
      editorRef.current?.focus()
      notify.toast({ message: `Inserted ${kind.replace('_', ' ')}`, tone: 'success' })
    },
    [active?.filename, activeIndex, projectId],
  )

  const onPickImage = useCallback(
    async (file: File | null) => {
      if (!file) return
      try {
        const uploaded = await uploadImage(projectId, file)
        const url = uploaded.url?.startsWith('http')
          ? uploaded.url.replace(/^https?:\/\/[^/]+/, '')
          : uploaded.url
        const abs = url?.startsWith('/') ? url : `/${url || ''}`
        const ok = editorRef.current?.insertKind('image', { imageUrl: abs })
        if (!ok) throw new Error('Could not insert image')
        editorRef.current?.focus()
      } catch (err) {
        notify.toast({
          message: err instanceof Error ? err.message : 'Image upload failed',
          tone: 'error',
        })
      }
    },
    [projectId],
  )

  // Flush pending edits before unmount.
  useEffect(() => {
    return () => {
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current)
        saveTimerRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    const stage = canvasHostRef.current
    const onWheel = (event: WheelEvent) => {
      if (!(event.metaKey || event.ctrlKey)) return
      event.preventDefault()
      bumpZoom(event.deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP)
    }
    stage?.addEventListener('wheel', onWheel, { passive: false })
    return () => stage?.removeEventListener('wheel', onWheel)
  }, [bumpZoom])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (presenting) return
      const target = event.target as HTMLElement | null
      if (
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.isContentEditable)
      ) {
        return
      }
      const meta = event.metaKey || event.ctrlKey
      if (meta && event.key.toLowerCase() === 'z' && !event.shiftKey) {
        event.preventDefault()
        onUndo()
        return
      }
      if (meta && (event.key.toLowerCase() === 'y' || (event.key.toLowerCase() === 'z' && event.shiftKey))) {
        event.preventDefault()
        onRedo()
        return
      }
      if (meta && (event.key === '=' || event.key === '+')) {
        event.preventDefault()
        bumpZoom(ZOOM_STEP)
        return
      }
      if (meta && event.key === '-') {
        event.preventDefault()
        bumpZoom(-ZOOM_STEP)
        return
      }
      if (meta && event.key === '0') {
        event.preventDefault()
        setZoomMode('fit')
        return
      }
      if (
        (event.key === 'Delete' || event.key === 'Backspace') &&
        selection &&
        editorMode === 'edit'
      ) {
        event.preventDefault()
        const removed = editorRef.current?.deleteSelection()
        if (removed) {
          setSelection(null)
          refreshLayers()
        }
        return
      }
      // Don't change slides while an object is selected (arrows nudge inside the iframe).
      if (selection && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')) {
        return
      }
      if (event.key === 'ArrowLeft') {
        selectSlide(Math.max(0, activeIndex - 1))
        return
      }
      if (event.key === 'ArrowRight') {
        selectSlide(Math.min(slides.length - 1, activeIndex + 1))
        return
      }
      if ((event.key === 'p' || event.key === 'P') && !meta) {
        event.preventDefault()
        void flushSave().finally(() => enterPresent())
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [
    activeIndex,
    bumpZoom,
    editorMode,
    enterPresent,
    flushSave,
    onRedo,
    onUndo,
    presenting,
    refreshLayers,
    selectSlide,
    selection,
    slides.length,
  ])

  const regenChipDefs = [
    { key: 'tighten', label: t('regenerateChipTighten') },
    { key: 'overlaps', label: t('regenerateChipOverlaps') },
    { key: 'keep', label: t('regenerateChipKeepAsset') },
    { key: 'hierarchy', label: t('regenerateChipHierarchy') },
  ]

  if (!slides.length) {
    return (
      <div className={styles.shell}>
        <div className={styles.empty}>No slides found for this project.</div>
      </div>
    )
  }

  return (
    <div
      className={styles.shell}
      data-html-editor="1"
      data-deck-editor="true"
      data-regen-busy={regenBusy ? 'true' : undefined}
    >
      <EditorHeader
        title={title || 'Deck'}
        saveStatus={saveStatus}
        deckStatus={deckStatus}
        editorMode={editorMode}
        canUndo={undoStack.length > 1}
        canRedo={redoStack.length > 0}
        exporting={exporting}
        aiBusy={regenBusy}
        layersOpen={layersOpen}
        notesOpen={notesOpen}
        onBack={() => {
          void flushSave().finally(() => router.push(`/editor/${projectId}`))
        }}
        onUndo={onUndo}
        onRedo={onRedo}
        onExport={() => void exportPptx()}
        onExportPdf={() => void exportPdf()}
        onExportNotesPdf={() => void exportNotesPdf()}
        onExportPrevious={previousReleaseAvailable ? () => void exportPreviousPptx() : undefined}
        onExportHtml={() => void exportHtml()}
        onDuplicate={() => void onDuplicateSlide()}
        onDelete={() => void onDeleteSlide()}
        onRegenerate={() => {
          setRegenError('')
          setRegenOpen(true)
        }}
        regenerateLabel={t('regenerateSlide')}
        onShortcuts={() => setShortcutsOpen(true)}
        onToggleNotes={() => setNotesOpen((v) => !v)}
        onToggleLayers={() => setLayersPinned((v) => !v)}
        onModeChange={onModeChange}
        onPresent={() => {
          void flushSave().finally(() => enterPresent())
        }}
        zoomLabel={zoomMode === 'fit' ? 'Fit' : `${Math.round(scale * 100)}%`}
        onZoomOut={() => bumpZoom(-ZOOM_STEP)}
        onZoomIn={() => bumpZoom(ZOOM_STEP)}
        onZoomCycle={cycleZoomFit}
      />

      <div
        className={styles.body}
        data-layers={layersOpen ? 'open' : 'closed'}
        data-html-editor="1"
        data-mode={editorMode}
      >
        <SlideStrip
          slides={slides}
          activeIndex={activeIndex}
          onSelect={selectSlide}
          onMove={(from, to) => void onMoveSlide(from, to)}
          badges={{
            notes: notesPresence,
            dirty: dirtySlides,
            regenerating: regenBusy ? active?.filename || null : null,
          }}
        />

        <div className={styles.canvasWrap} ref={canvasHostRef}>
          <div className={styles.canvasStage} ref={canvasStageRef}>
            <div className={styles.canvasFrame}>
              {displayHtml ? (
                <SlideStage
                  scale={scale}
                  aria-label={`Slide ${activeIndex + 1}`}
                >
                  <EditableHtmlSlide
                    key={`${activeFile || activeIndex}-${visualReloadKey}`}
                    ref={editorRef}
                    html={displayHtml}
                    title={`Slide ${activeIndex + 1}`}
                    onDirty={onEditorDirty}
                    onSelectionChange={onSelectionChange}
                    onReady={() => {
                      if (editorMode === 'edit') {
                        setLayersPinned(true)
                        refreshLayersUntilReady()
                      }
                    }}
                    editMode={editorMode === 'edit'}
                  />
                </SlideStage>
              ) : displayPngUrl ? (
                <SlideStage
                  scale={scale}
                  aria-label={`Slide ${activeIndex + 1}`}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={displayPngUrl}
                    alt={`Slide ${activeIndex + 1}`}
                    style={{ display: 'block', width: '100%', height: '100%', objectFit: 'contain' }}
                  />
                </SlideStage>
              ) : (
                <div className={styles.loading}>
                  {slideVisualLoading ? 'Loading slide…' : 'Preview unavailable'}
                </div>
              )}
            </div>
          </div>

          {editorMode === 'edit' && (
            <>
              <div className={styles.canvasFloatTools}>
                <div className={styles.canvasInsertGroup}>
                  <button
                    type="button"
                    className={styles.btn}
                    data-insert-toggle="true"
                    data-active={insertOpen ? 'true' : undefined}
                    onClick={() => setInsertOpen((v) => !v)}
                  >
                    <Icon name="plus" className="w-3.5 h-3.5" />
                    <span className={styles.btnLabel}>Insert</span>
                  </button>
                  <InsertPopover
                    open={insertOpen}
                    anchor="canvas"
                    onClose={() => setInsertOpen(false)}
                    onInsert={onInsertKind}
                  />
                </div>
              </div>
              {selection && (
                <HtmlFormatToolbar
                  selection={selection}
                  position={formatToolbarPos}
                  onPositionChange={setFormatToolbarPos}
                  onApplyStyle={applyStyle}
                  onEditText={() => editorRef.current?.startTextEdit()}
                  onAiEdit={() => {
                    setEditorMode('refine')
                    setLayersPinned(false)
                  }}
                  onDelete={() => {
                    editorRef.current?.deleteSelection()
                    setSelection(null)
                    refreshLayers()
                  }}
                  onBringToFront={() => {
                    if (!selection) return
                    editorRef.current?.reorderLayer(selection.id, 'top')
                    refreshLayers()
                  }}
                  onBringForward={() => {
                    if (!selection) return
                    editorRef.current?.reorderLayer(selection.id, 'up')
                    refreshLayers()
                  }}
                  onSendBackward={() => {
                    if (!selection) return
                    editorRef.current?.reorderLayer(selection.id, 'down')
                    refreshLayers()
                  }}
                  onSendToBack={() => {
                    if (!selection) return
                    editorRef.current?.reorderLayer(selection.id, 'bottom')
                    refreshLayers()
                  }}
                />
              )}
            </>
          )}

          {editorMode === 'refine' && (
            <HtmlAiRail
              slideLabel={`${activeIndex + 1} / ${slides.length}`}
              feedback={regenFeedback}
              busy={regenBusy}
              error={regenError}
              onFeedbackChange={setRegenFeedback}
              onSubmit={() => void onConfirmRegenerate()}
              onOpenAdvanced={() => {
                setRegenError('')
                setRegenOpen(true)
              }}
            />
          )}

          <NotesPanel
            projectId={projectId}
            filename={active?.filename}
            slideIndex={activeIndex}
            slideCount={slides.length}
            prefetchFilenames={slides
              .slice(Math.max(0, activeIndex - 1), Math.min(slides.length, activeIndex + 3))
              .map((slide) => slide.filename)}
            open={notesOpen}
            onToggle={() => setNotesOpen((v) => !v)}
            onRegisterFlush={registerNotesFlush}
          />
        </div>

        {layersOpen && (
          <div className={styles.rightRail}>
            <HtmlInspector
              selection={selection}
              onApplyStyle={applyStyle}
              onApplyText={(text) => {
                editorRef.current?.applyText(text)
                refreshLayers()
              }}
              onDelete={() => {
                editorRef.current?.deleteSelection()
                setSelection(null)
                refreshLayers()
              }}
              onEditText={() => editorRef.current?.startTextEdit()}
            />
            <HtmlLayersPanel
              layers={layers}
              selectedId={selection?.id || null}
              onSelect={(id) => {
                const editor = editorRef.current
                if (!editor) return
                if (editor.selectById(id)) return
                // A click can land during the brief fallback -> live-layer
                // handoff. Refresh from the iframe and retry once against the
                // authoritative DOM instead of silently doing nothing.
                refreshLayers()
                window.requestAnimationFrame(() => editorRef.current?.selectById(id))
              }}
              onReorder={(id, direction) => {
                editorRef.current?.reorderLayer(id, direction)
                refreshLayers()
              }}
              onToggleHidden={(id, hidden) => {
                const wasSelected = selection?.id === id
                if (!wasSelected) editorRef.current?.selectById(id)
                editorRef.current?.applyStyle({ hidden })
                if (!wasSelected && selection?.id) editorRef.current?.selectById(selection.id)
                refreshLayers()
              }}
            />
          </div>
        )}
      </div>

      {presenting && (
        <PresentMode
          slides={slides}
          startIndex={activeIndex}
          visualsByFile={visualsByFile}
          onClose={exitPresent}
        />
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        style={{ display: 'none' }}
        onChange={(e) => {
          const file = e.target.files?.[0] || null
          e.target.value = ''
          void onPickImage(file)
        }}
      />

      {shortcutsOpen && (
        <div className={styles.modalOverlay} onClick={() => setShortcutsOpen(false)}>
          <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
            <h3>Keyboard shortcuts</h3>
            <ul>
              <li>Drag — move elements</li>
              <li>Double-click — edit text</li>
              <li>Delete — remove selected element</li>
              <li>⌘/Ctrl + Z / Shift+Z — undo / redo</li>
              <li>P — present mode</li>
              <li>Arrow keys — change slide</li>
              <li>⌘/Ctrl + = / - / 0 — zoom in / out / fit</li>
            </ul>
            <button type="button" className={styles.btn} onClick={() => setShortcutsOpen(false)}>
              Close
            </button>
          </div>
        </div>
      )}

      {regenOpen && (
        <div
          className={styles.regenOverlay}
          role="dialog"
          aria-modal="true"
          aria-labelledby="regen-title"
          onClick={() => {
            if (!regenBusy) setRegenOpen(false)
          }}
        >
          <div className={styles.regenPanel} onClick={(e) => e.stopPropagation()}>
            <p className={styles.regenEyebrow}>
              {t('regenerateSlideEyebrow')} · {activeIndex + 1} / {slides.length}
            </p>
            <h2 id="regen-title" className={styles.regenTitle}>
              {t('regenerateSlideTitle')}
            </h2>
            <p className={styles.regenDesc}>{t('regenerateSlideDesc')}</p>
            <div
              className={styles.regenPreview}
              data-empty={!displayHtml && !displayPngUrl ? 'true' : undefined}
            >
              {displayHtml ? (
                <SlideStage className={styles.regenPreviewStage} aria-label="Slide preview">
                  <HtmlSlideFrame html={displayHtml} title="Slide preview" />
                </SlideStage>
              ) : displayPngUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={displayPngUrl} alt="" />
              ) : (
                <span className={styles.regenPreviewEmpty}>Preview unavailable</span>
              )}
            </div>
            <p className={styles.regenLabel}>{t('regenerateSlideLabel')}</p>
            <textarea
              className={styles.regenTextarea}
              value={regenFeedback}
              placeholder={t('regenerateSlidePlaceholder')}
              disabled={regenBusy}
              onChange={(e) => setRegenFeedback(e.target.value)}
            />
            <div className={styles.regenChips}>
              {regenChipDefs.map((chip) => (
                <button
                  key={chip.key}
                  type="button"
                  className={styles.regenChip}
                  data-active={regenChips.includes(chip.key) ? 'true' : undefined}
                  disabled={regenBusy}
                  onClick={() => appendRegenChip(chip.key, chip.label)}
                >
                  {chip.label}
                </button>
              ))}
            </div>
            {regenError ? <p className={styles.regenError}>{regenError}</p> : null}
            <div className={styles.regenActions}>
              <button
                type="button"
                className={styles.regenGhost}
                disabled={regenBusy}
                onClick={() => setRegenOpen(false)}
              >
                {t('cancel')}
              </button>
              <button
                type="button"
                className={styles.regenPrimary}
                disabled={regenBusy || !regenFeedback.trim()}
                onClick={() => void onConfirmRegenerate()}
              >
                <Icon name="sparkles" className="w-4 h-4" />
                {regenBusy ? t('regenerateSlideBusy') : t('regenerateSlideSubmit')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
