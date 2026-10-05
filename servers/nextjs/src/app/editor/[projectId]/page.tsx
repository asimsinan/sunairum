"use client"
import { useEffect, useMemo, useRef, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Figtree, Sora } from 'next/font/google'
import { useUI } from '@/lib/i18n'
import { API_URL, apiFetch, downloadAuthenticatedFile, exportDeckTransaction, ExportTransactionError } from '@/lib/api'
import { useProjectStore } from '@/store/projectStore'
import { useWizardStore } from '@/store/wizardStore'
import {
  claimPendingSourceUpload,
  clearPendingSourceUpload,
  peekPendingSourceUpload,
  releasePendingSourceUploadClaim,
  startOrJoinSourceUpload,
} from '@/lib/pendingSourceUpload'
import Icon from '@/components/Icon'
import AutoTextarea from '@/components/AutoTextarea'
import GenerationProgress from '@/components/GenerationProgress'
import GroundingStatus from '@/components/GroundingStatus'
import SourceParsingPanel from '@/components/SourceParsingPanel'
import DesignDirectionPreview from '@/components/DesignDirectionPreview'
import SlideLightbox, { SvgThumb, lightboxStyles } from '@/components/SlideLightbox'
import styles from './editor.module.css'
import { notify } from '@/components/feedback/notify'
import { isReadyStatus } from '@/components/library/types'
import { touchProject } from '@/lib/touchProject'

const sora = Sora({ subsets: ['latin'], weight: ['600', '700'], variable: '--font-sora' })
const figtree = Figtree({
  subsets: ['latin'],
  weight: ['400', '600', '700', '800'],
  variable: '--font-figtree',
})

interface Stage1Data {
  audience: { value: string }
  communication_intent: { value: string }
  audience_outcome: { value: string }
  core_message: { value: string }
  delivery_context: { value: string }
  artifact_afterlife: { value: string }
  recommend: { canvas: string }
}

const EMPTY_STAGE1: Stage1Data = {
  audience: { value: '' },
  communication_intent: { value: '' },
  audience_outcome: { value: '' },
  core_message: { value: '' },
  delivery_context: { value: '' },
  artifact_afterlife: { value: '' },
  recommend: { canvas: 'ppt169' },
}

interface Candidate {
  name_tr: string
  note_tr: string
  visual_style: string
  icons: string
  color: {
    name_tr: string
    palette: {
      background: string
      secondary_bg: string
      primary: string
      accent: string
      secondary_accent: string
      body_text: string
    }
  }
  typography: {
    name_tr: string
    heading: { primary: string; english: string; css: string }
    body: { primary: string; english: string; css: string }
    body_size: number
  }
  image_strategy?: {
    name_tr: string
    rendering: string
    visual_tr: string
    mood_tr: string
  }
}

interface Stage2Data {
  recommend: {
    delivery_purpose: string
    mode: string
    visual_style: string
    image_usage: string[]
  }
  page_count: { value: string }
  template_application: { value: string }
  image_notes: { value: string }
  design_directions: {
    selected: number
    candidates: Candidate[]
  }
}

interface SlidePreview {
  filename: string
  url: string
}

interface SourceStatus {
  status: string
  progress: number
  message: string
  // The backend stays English-only; this names the phase so the UI can say it
  // in the reader's language. `message` is the fallback.
  message_key?: string
  error?: string | null
  ready: boolean
  pages?: number
  tables?: number
  figures?: number
  formulas?: number
}

const SOURCE_ACTIVE_STATUSES = new Set(['source_uploading', 'source_parsing', 'source_grounding'])

export default function EditorPage({ params }: { params: { projectId: string } }) {
  useEffect(() => {
    touchProject(params.projectId)
  }, [params.projectId])
  const { t } = useUI()
  const router = useRouter()
  const searchParams = useSearchParams()
  const wizardConfig = useWizardStore((s) => s.config)
  // SPA flow: wizard config travels via the sessionStorage-backed store.
  // Legacy deep links (?topic=...&template_id=...) still work as a fallback.
  const cfg = wizardConfig && wizardConfig.projectId === params.projectId ? wizardConfig : null
  const setWizardConfig = useWizardStore((s) => s.setConfig)
  // Capture navigation intent before consuming it. A newly-created project can
  // paint stage-1 copy on its first frame; reopened projects retain neutral boot
  // copy until status proves which editor surface belongs here.
  const entryIntentRef = useRef<'create' | 'open' | null>(cfg?.entry || null)
  const isFreshCreate = entryIntentRef.current === 'create'
  useEffect(() => {
    if (!cfg?.entry) return
    setWizardConfig({ ...cfg, entry: undefined })
  }, [cfg, setWizardConfig])
  const [resolvedTopic, setResolvedTopic] = useState<string | null>(null)
  const sourceExpected = Boolean(cfg?.hasSource)
  const topic = cfg?.topic || searchParams.get('topic') || resolvedTopic || t('untitledPresentation')
  const instructions = cfg?.instructions || ''
  const mode = cfg?.mode || searchParams.get('mode')
  const template_id = cfg?.templateId || searchParams.get('template_id')
  const lang = cfg?.lang || searchParams.get('lang') || 'auto'
  const slidesParam = cfg?.slides || searchParams.get('slides') || 'auto'
  const isTemplateMode = !!template_id
  const slidesOverride = slidesParam !== 'auto' && parseInt(slidesParam, 10) > 0 ? slidesParam : null
  const stepLabel = (key: string, vars?: Record<string, string | number>) =>
    t(key, vars).replace(/^\d+\.\s*/, '')
  
  const { progress, statusKey, statusVars, setProgress, isGenerating, setGenerating } = useProjectStore()
  
  const pendingHandoff = peekPendingSourceUpload(params.projectId)
  const [wizardStage, setWizardStage] = useState<'stage1' | 'stage2' | 'stage3' | 'generating' | 'done'>('stage1')
  // PDF handoff from Get Started: skip boot gate and show Uploading immediately.
  const [loading, setLoading] = useState<boolean>(!pendingHandoff)
  // True once the initial project-status check has resolved, so the wizard
  // chrome never paints while we determine whether a completed project exists.
  const [statusResolved, setStatusResolved] = useState<boolean>(Boolean(pendingHandoff))
  // Skip entrance motion when boot lands directly on done/generating (avoids
  // loading-card → ready-pop flicker).
  const [suppressStageMotion, setSuppressStageMotion] = useState(false)
  const [sourceProcessing, setSourceProcessing] = useState<boolean>(
    sourceExpected || Boolean(pendingHandoff),
  )
  // True while home→editor File handoff HTTP upload is in flight.
  const [clientUploading, setClientUploading] = useState<boolean>(Boolean(pendingHandoff))
  const [sourceStatus, setSourceStatus] = useState<SourceStatus | null>(() =>
    pendingHandoff
      ? {
          status: 'source_uploading',
          progress: 4,
          message: '',
          message_key: 'source_status_uploading',
          ready: false,
        }
      : null,
  )
  
  // Stage 1 fields
  const [stage1Data, setStage1Data] = useState<Stage1Data | null>(null)
  // idle/loading keep the shell up; ready/error may paint the strategy form.
  // Prevents empty "Presentation Strategy" flashing before "Shaping recommendations".
  const [stage1LoadState, setStage1LoadState] = useState<'idle' | 'loading' | 'ready' | 'error'>(
    'idle',
  )
  const stage1FetchKeyRef = useRef<string | null>(null)
  const stage1LoadStateRef = useRef<'idle' | 'loading' | 'ready' | 'error'>('idle')
  stage1LoadStateRef.current = stage1LoadState
  const [canvas, setCanvas] = useState<string>('ppt169')
  const [audience, setAudience] = useState<string>('')
  const [communicationIntent, setCommunicationIntent] = useState<string>('')
  const [audienceOutcome, setAudienceOutcome] = useState<string>('')
  const [coreMessage, setCoreMessage] = useState<string>('')
  const [deliveryContext, setDeliveryContext] = useState<string>('')
  const [artifactAfterlife, setArtifactAfterlife] = useState<string>('')

  // Stage 2 fields
  const [stage2Data, setStage2Data] = useState<Stage2Data | null>(null)
  const [selectedDirection, setSelectedDirection] = useState<number>(0)
  const [pageCount, setPageCount] = useState<string>(slidesOverride || '8-12')
  const [imageNotes, setImageNotes] = useState<string>('')
  
  // Stage 3 fields
  const [speakerNotes, setSpeakerNotes] = useState<boolean>(true)
  const [notesDurationMin, setNotesDurationMin] = useState<number>(15)
  const [notesDurationCustom, setNotesDurationCustom] = useState<string>('')
  const [animations, setAnimations] = useState<boolean>(false)
  const [animationEffect, setAnimationEffect] = useState<string>('fade')
  const [transitionCatalog, setTransitionCatalog] = useState<{
    popular: string[]
    effects: string[]
  }>({
    popular: ['fade', 'push', 'wipe', 'cover', 'dissolve', 'cut', 'zoom'],
    effects: ['fade', 'push', 'wipe', 'cover', 'dissolve', 'cut', 'zoom'],
  })
  const [narration, setNarration] = useState<boolean>(false)
  /** Scratch-only: Image-engine illustrations into figure slots (budget 0–6). */
  const [aiIllustrations, setAiIllustrations] = useState(true)
  const [sourceFigures, setSourceFigures] = useState<Array<{ id: string; thumb_url?: string; page?: number; file?: string }>>([])
  const [selectedFigureIds, setSelectedFigureIds] = useState<string[]>([])
  const [sourceTables, setSourceTables] = useState<Array<{
    id: string
    page?: number
    caption?: string
    preview?: string[][]
    full?: string[][]
    rows?: number | null
    cols?: number | null
  }>>([])
  const [selectedTableIds, setSelectedTableIds] = useState<string[]>([])
  const [previewTableId, setPreviewTableId] = useState<string | null>(null)
  const [isCancelling, setIsCancelling] = useState(false)
  const [isResuming, setIsResuming] = useState(false)
  const [awaitingCompile, setAwaitingCompile] = useState(false)
  const [authoringAction, setAuthoringAction] = useState<string | null>(null)
  /** Project generation/export status for the completed-deck chrome. */
  const [projectStatus, setProjectStatus] = useState<string | null>(null)
  /** Failure/cancel detail shown on the interrupted done screen. */
  const [interruptDetail, setInterruptDetail] = useState<string | null>(null)

  // Previews
  const [previews, setPreviews] = useState<SlidePreview[]>([])
  // A slide's HTML is written before its preview raster, so mid-generation the
  // API's `url` falls back to html_output/slide_NN.html. Rendering that as a
  // thumbnail injected a whole 1280x720 slide document into this page: it
  // painted at native size (title and page number clipped by the card) until
  // the raster arrived and replaced it. A slide joins the strip once it has a
  // real thumbnail instead.
  const liveThumbs = useMemo(
    () => previews.filter((slide) => /\.png(\?|$)/i.test(slide.url || '')),
    [previews],
  )
  const [livePreviewIndex, setLivePreviewIndex] = useState<number | null>(null)
  const [downloadOpen, setDownloadOpen] = useState(false)
  const [exportingPptx, setExportingPptx] = useState(false)
  const [exportingPdf, setExportingPdf] = useState(false)
  const [exportingHtml, setExportingHtml] = useState(false)
  const downloadMenuRef = useRef<HTMLDivElement>(null)
  const downloadBusy = exportingPptx || exportingPdf || exportingHtml

  /** Keep failed/cancelled runs in the editor (resume UI) — never bounce to History. */
  const settleInterruptedRun = (
    status: string,
    slides?: SlidePreview[] | null,
    detail?: string | null,
  ) => {
    if (slides?.length) setPreviews(slides)
    setProjectStatus(status)
    setInterruptDetail(detail?.trim() || null)
    setGenerating(false)
    setAwaitingCompile(false)
    setWizardStage('done')
    setLoading(false)
  }

  // Returns a key for the store to resolve at render time, so the running
  // status follows a language switch instead of freezing.
  type StatusProgress = { key: string; vars?: Record<string, string | number> }

  const normalizeStatusKey = (key: string): string => {
    if (
      key === 'status_qa' ||
      key === 'status_qa_fixing' ||
      key === 'status_qa_fixing_generic' ||
      key === 'status_qa_failed'
    ) {
      return 'generatingStatus'
    }
    return key
  }

  const statusProgress = (project: any): StatusProgress => {
    const current = project.slide_current
    const total = project.slide_total
    const title = String(project.slide_title ?? '').trim()
      || (current ? `Slide ${current}` : '')
    const vars: Record<string, string | number> = {
      current: current ?? '',
      total: total ?? '',
      title,
    }
    // Per-slide progress is more specific than the phase the backend names.
    if (project.status === 'generating' && current && total) {
      return { key: 'status_slide_titled', vars }
    }
    // Legacy pipeline statuses still appear in old status.json files.
    if (project.status === 'qa' || project.status === 'qa_fixing') {
      return { key: 'generatingStatus' }
    }
    // The backend names its own phase, which is the only way to tell apart the
    // several phases that share one status.
    if (project.message_key) {
      const key = normalizeStatusKey(
        project.message_key === 'status_generating_slide' && current && total
          ? 'status_slide_titled'
          : project.message_key === 'status_speaker_notes_slide' && current && total
            ? 'status_speaker_notes_slide'
            : project.message_key,
      )
      return { key, vars }
    }

    // Everything below is for a status.json written before the backend started
    // naming phases. Never fall back to project.message for a status handled
    // here: that message is English and would bypass translation entirely.
    if (project.status === 'queued' || project.status === 'planning') {
      if (project.message_key === 'status_resuming') return { key: 'status_resuming' }
      return { key: 'status_planning' }
    }
    if (project.status === 'cancelled') return { key: 'status_cancelled' }
    if (SOURCE_ACTIVE_STATUSES.has(project.status)) return { key: 'sourceParsingDescription' }
    if (project.status === 'compiling') return { key: 'status_compiling' }
    if (project.status === 'rendering') return { key: 'status_rendering' }
    if (project.status === 'generating') return { key: 'generatingStatus' }
    return { key: statusKey || 'generatingStatus' }
  }

  const applyProjectStatus = (progressValue: number, project: any) => {
    const next = statusProgress(project)
    setProgress(progressValue, next.key, next.vars)
  }

  // The one place status text is turned into words.
  const statusLabel = statusKey ? t(statusKey, statusVars) : t('generatingStatus')

  // Prefer the phase key, but keep the backend's English if this build has no
  // translation for it, which beats showing the reader a bare key.
  const sourceStatusLabel = (() => {
    const key = sourceStatus?.message_key
    if (key) {
      const translated = t(key)
      if (translated !== key) return translated
    }
    return sourceStatus?.message || t('sourceParsingDescription')
  })()

  // Live slide previews: newly written PNG previews appear while generating.
  const previewTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  useEffect(() => {
    if (wizardStage !== 'generating') return
    const refreshPreview = async () => {
      try {
        const res = await apiFetch(`/api/projects/${params.projectId}/preview`)
        if (res.ok) {
          const data = await res.json()
          if (data && data.slides && data.slides.length > 0) setPreviews(data.slides)
        }
      } catch (err) {
        console.error("Live preview refresh failed:", err)
      }
    }
    refreshPreview()
    // PNG previews update as slides author; poll faster so stub→real swaps show up.
    previewTimerRef.current = setInterval(refreshPreview, 2000)
    return () => {
      if (previewTimerRef.current) clearInterval(previewTimerRef.current)
      previewTimerRef.current = null
    }
  }, [wizardStage, params.projectId])

  // Completion/error detection while generating (covers viewing mid-run,
  // where no WebSocket is attached to this page instance).
  const wsActiveRef = useRef(false)
  useEffect(() => {
    if (wizardStage !== 'generating') return
    const id = setInterval(async () => {
      try {
        const res = await apiFetch(`/api/projects`)
        const data = await res.json()
        const proj = (data.projects || []).find((p: any) => p.project_id === params.projectId)
        if (!proj) return
        if (isReadyStatus(proj.status)) {
          clearInterval(id)
          setProjectStatus(proj.status === 'completed' ? 'done' : proj.status)
          setGenerating(false)
          setAwaitingCompile(false)
          setSourceProcessing(false)
          setLoading(false)
          setWizardStage('done')
          apiFetch(`/api/projects/${params.projectId}/preview`)
            .then(r => r.json())
            .then(d => setPreviews(d.slides || []))
        } else if (proj.status === 'awaiting_user_compile') {
          setAwaitingCompile(true)
          setGenerating(true)
          applyProjectStatus(proj.progress || 84, proj)
          apiFetch(`/api/projects/${params.projectId}/preview`)
            .then(r => r.json())
            .then(d => setPreviews(d.slides || []))
            .catch(() => {})
        } else if (
          proj.status === 'error' ||
          proj.status === 'failed' ||
          proj.status === 'cancelled'
        ) {
          clearInterval(id)
          // Empty failures still open: History → Open must land on resume UI.
          apiFetch(`/api/projects/${params.projectId}/preview`)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => {
              settleInterruptedRun(
                proj.status,
                d?.slides || [],
                proj.error_message || proj.message,
              )
            })
            .catch(() =>
              settleInterruptedRun(
                proj.status,
                null,
                proj.error_message || proj.message,
              ),
            )
        } else if (proj.progress !== undefined) {
          applyProjectStatus(proj.progress, proj)
        }
      } catch (err) {
        console.error("Status poll failed:", err)
      }
    }, 3000)
    return () => clearInterval(id)
  }, [wizardStage, params.projectId])

  // Home navigates here before upload finishes — show Uploading on this page.
  useEffect(() => {
    const handoff = claimPendingSourceUpload(params.projectId)
    if (!handoff) return
    let alive = true
    setWizardStage('stage1')
    setSourceProcessing(true)
    setClientUploading(true)
    setGenerating(false)
    setLoading(false)
    setStatusResolved(true)
    setSourceStatus({
      status: 'source_uploading',
      progress: 4,
      message: t('source_status_uploading'),
      message_key: 'source_status_uploading',
      ready: false,
    })
    setProgress(4, 'source_status_uploading')

    ;(async () => {
      try {
        const formData = new FormData()
        formData.append('topic', handoff.topic)
        formData.append('file', handoff.file)
        // Coalesce: Strict Mode remount must not POST a second upload_source
        // (that would enqueue two Docling workers for the same PDF).
        const response = await startOrJoinSourceUpload(params.projectId, () =>
          apiFetch(`/api/projects/${params.projectId}/upload_source`, {
            method: 'POST',
            body: formData,
          }),
        )
        if (!alive) return
        if (!response.ok) {
          const error = await response.json().catch(() => ({}))
          throw new Error(
            (error as { detail?: string }).detail || t('sourceImportFailed'),
          )
        }
        clearPendingSourceUpload(params.projectId)
        // Poll may start now — parsing continues server-side.
        setClientUploading(false)
        setSourceStatus((prev) => ({
          status: 'source_uploading',
          progress: Math.max(prev?.progress || 0, 8),
          message: t('source_status_uploading'),
          message_key: 'source_status_uploading',
          ready: false,
          pages: prev?.pages,
          tables: prev?.tables,
          figures: prev?.figures,
          formulas: prev?.formulas,
        }))
      } catch (err) {
        if (!alive) return
        clearPendingSourceUpload(params.projectId)
        setClientUploading(false)
        console.error('Source upload failed:', err)
        const detail =
          err instanceof Error ? err.message : t('unknownError')
        setSourceStatus({
          status: 'source_error',
          progress: 0,
          message: t('sourceParsingFailed'),
          message_key: 'source_status_error',
          error: detail,
          ready: false,
        })
        setSourceProcessing(false)
        void notify.alert({
          message: `${t('sourceImportFailed')}: ${detail}`,
          tone: 'error',
        })
      }
    })()

    return () => {
      alive = false
      // Strict Mode remount: let the next effect claim the same File and join
      // the in-flight upload via startOrJoinSourceUpload.
      releasePendingSourceUploadClaim(params.projectId)
    }
  }, [params.projectId, t, setProgress, setGenerating])

  // Boot check: decide the correct initial screen for this project in ONE
  // pass, so refreshing a completed project resolves straight to the results
  // screen without ever painting the wizard steps.
  useEffect(() => {
    let cancelled = false
    const checkProjectStatus = async () => {
      // Client PDF handoff owns the parsing shell — skip boot gate / stage1 flash.
      if (peekPendingSourceUpload(params.projectId)) {
        setWizardStage('stage1')
        setSourceProcessing(true)
        setGenerating(false)
        setLoading(false)
        setStatusResolved(true)
        setSourceStatus((prev) => prev || {
          status: 'source_uploading',
          progress: 4,
          message: t('source_status_uploading'),
          message_key: 'source_status_uploading',
          ready: false,
        })
        return
      }
      setLoading(true)
      try {
        // Status and previews are checked together. Status is authoritative:
        // active tasks write partial PNG previews before the deck is ready.
        const [statusRes, prevRes] = await Promise.all([
          apiFetch(`/api/projects`).catch(() => null),
          apiFetch(`/api/projects/${params.projectId}/preview`).catch(() => null),
        ])
        if (cancelled) return

        // If a generation is currently running (including a rerun with stale
        // previews or an older PPTX), never show the completed screen.
        let status: string | undefined
        try {
           const statusData = await statusRes?.json()
           const proj = (statusData?.projects || []).find((p: any) => p.project_id === params.projectId)
           if (proj?.topic) {
             setResolvedTopic(proj.topic)
             // History / deep links often open without wizard session config.
             if (!cfg?.topic) {
               setWizardConfig({
                 projectId: params.projectId,
                 topic: proj.topic,
                 mode: (cfg?.mode as 'scratch' | 'template') || 'scratch',
                 templateId: cfg?.templateId,
                 lang: cfg?.lang || 'auto',
                 slides: cfg?.slides || 'auto',
                 hasSource: Boolean(cfg?.hasSource),
                 instructions: cfg?.instructions,
               })
             }
           }
           status = proj?.status
           if (typeof status === 'string') setProjectStatus(status)
           if (status && SOURCE_ACTIVE_STATUSES.has(status)) {
             setGenerating(false)
             setWizardStage('stage1')
             setSourceProcessing(true)
             setSourceStatus({
               status,
               progress: proj.progress || 0,
               message: proj.message || t('sourceParsingDescription'),
               ready: false,
             })
             applyProjectStatus(proj.progress || 0, proj)
             setLoading(false)
             return
           }
           // PDF already finished before/while the editor mounted. Do not leave
           // sourceProcessing=true (initial hasSource) or the parsing panel
           // flashes before "Shaping recommendations".
           if (status === 'source_ready') {
             setGenerating(false)
             setWizardStage('stage1')
             setSourceProcessing(false)
             setSourceStatus({
               status,
               progress: proj.progress || 100,
               message: proj.message || t('source_status_ready'),
               ready: true,
             })
             stage1FetchKeyRef.current = null
             setStage1Data(null)
             setStage1LoadState('loading')
             setLoading(true)
             return
           }
           if (status === 'source_error') {
             setGenerating(false)
             setWizardStage('stage1')
             setSourceProcessing(false)
             setSourceStatus({
               status,
               progress: proj.progress || 0,
               message: proj.message || t('sourceParsingFailed'),
               error: proj.error_message || proj.message,
               ready: false,
             })
             setLoading(false)
             return
           }
            if (status && ['queued', 'planning', 'generating', 'compiling', 'qa', 'qa_fixing', 'rendering', 'awaiting_user_compile'].includes(status)) {
            if (prevRes && prevRes.ok) {
              const prevData = await prevRes.json()
              if (prevData?.slides?.length) setPreviews(prevData.slides)
            }
            setSourceProcessing(false)
            setSuppressStageMotion(true)
            setGenerating(true)
            setWizardStage('generating')
            setAwaitingCompile(status === 'awaiting_user_compile')
            applyProjectStatus(proj.progress || 0, proj)
            setLoading(false)
            return
          }
          if (status === 'cancelled' || status === 'error' || status === 'failed') {
            // Failed/cancelled always open (resume UI); previews are optional.
            let slides: SlidePreview[] = []
            if (prevRes && prevRes.ok) {
              const prevData = await prevRes.json().catch(() => null)
              if (prevData?.slides?.length) slides = prevData.slides
            }
            setSourceProcessing(false)
            setSuppressStageMotion(true)
            settleInterruptedRun(
              status,
              slides,
              proj?.error_message || proj?.message,
            )
            return
          }
        } catch (err) {
          console.error("Error checking generation status:", err)
        }

        // Draft means "export stale / needed" — still show the authored slides.
        const viewable =
          isReadyStatus(status || '') ||
          status === 'draft' ||
          status === 'draft_invalid' ||
          status === 'awaiting_user_compile' ||
          status === 'error' ||
          status === 'failed' ||
          status === 'cancelled'

        let previewSlides: SlidePreview[] = []
        if (prevRes && prevRes.ok) {
          try {
            const prevData = await prevRes.json()
            if (prevData?.slides?.length) previewSlides = prevData.slides
          } catch (err) {
            console.error('Error reading project preview:', err)
          }
        }

        // Completed/draft project whose preview fetch failed: retry once.
        if (viewable && previewSlides.length === 0) {
          try {
            const retry = await apiFetch(`/api/projects/${params.projectId}/preview`)
            if (retry.ok) {
              const data = await retry.json()
              if (data?.slides?.length) previewSlides = data.slides
            }
          } catch (err) {
            console.error('Error checking project status:', err)
          }
        }

        // Ready runs must never stay on "Opening workspace" — even if preview
        // is empty (corrupt export). Slides alone also imply a completed run.
        if (viewable || previewSlides.length > 0) {
          if (previewSlides.length) setPreviews(previewSlides)
          const compiling = status === 'awaiting_user_compile'
          // hasSource boots with sourceProcessing=true; clear it or the source
          // poll later forces loading=true on top of the done screen forever.
          setSourceProcessing(false)
          setSuppressStageMotion(true)
          setWizardStage(compiling ? 'generating' : 'done')
          setAwaitingCompile(compiling)
          setGenerating(compiling)
          setLoading(false)
          return
        }

        // Fresh stage 1 / PDF setup: keep `loading` true through /stage1 fetch.
        // SOURCE_ACTIVE already cleared loading for the parsing panel; source_ready
        // kept it true. Do not clear here or the strategy form flashes.
      } catch (err) {
        console.error("Error checking project status:", err)
        if (!cancelled) setLoading(false)
      } finally {
        if (!cancelled) {
          setStatusResolved(true)
        }
      }
    }
    checkProjectStatus()
    return () => { cancelled = true }
  }, [params.projectId])

  // Stage 1 strategy data: fetched once the boot check has resolved (so the
  // wizard chrome never flashes on completed projects) and the topic is known.
  useEffect(() => {
    // Never call stage1 while the PDF handoff/upload is still in flight — that
    // used to race, hit FastAPI as scratch, and surface proxy ECONNRESET.
    if (
      !statusResolved ||
      wizardStage !== 'stage1' ||
      sourceProcessing ||
      clientUploading ||
      peekPendingSourceUpload(params.projectId) ||
      !topic
    ) {
      return
    }
    if (stage1LoadStateRef.current === 'ready' || stage1LoadStateRef.current === 'error') return

    const fetchKey = `${params.projectId}\0${topic}\0${lang}`
    if (stage1FetchKeyRef.current === fetchKey && stage1LoadState === 'loading') return
    stage1FetchKeyRef.current = fetchKey

    let cancelled = false
    setStage1LoadState('loading')
    setLoading(true)
    ;(async () => {
      try {
        const res = await apiFetch(`/api/projects/${params.projectId}/stage1?topic=${encodeURIComponent(topic)}&lang=${lang}`)
        if (cancelled) return
        if (res.ok) {
          const data = await res.json()
          if (cancelled) return
          setStage1Data(data)
          setCanvas(data.recommend?.canvas || 'ppt169')
          setAudience(data.audience?.value || '')
          setCommunicationIntent(data.communication_intent?.value || '')
          setAudienceOutcome(data.audience_outcome?.value || '')
          setCoreMessage(data.core_message?.value || '')
          setDeliveryContext(data.delivery_context?.value || '')
          setArtifactAfterlife(data.artifact_afterlife?.value || '')
          setStage1LoadState('ready')
          setLoading(false)
          return
        }
        // PDF evidence not ready yet — hold the loading shell / re-enter source poll.
        if (res.status === 409) {
          stage1FetchKeyRef.current = null
          setStage1LoadState('idle')
          setSourceProcessing(true)
          setLoading(false)
          return
        }
        // Definitive prep failure: allow an empty editable contract.
        setStage1Data(EMPTY_STAGE1)
        setStage1LoadState('error')
        setLoading(false)
      } catch (err) {
        console.error(err)
        if (cancelled) return
        setStage1Data(EMPTY_STAGE1)
        setStage1LoadState('error')
        setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [
    statusResolved,
    wizardStage,
    sourceProcessing,
    clientUploading,
    params.projectId,
    topic,
    lang,
  ])

  useEffect(() => {
    if (!previewTableId) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setPreviewTableId(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [previewTableId])

  useEffect(() => {
    if (!downloadOpen) return
    const onDown = (event: MouseEvent) => {
      if (!downloadMenuRef.current?.contains(event.target as Node)) setDownloadOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setDownloadOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [downloadOpen])

  const downloadPptx = async () => {
    if (downloadBusy) return
    setDownloadOpen(false)
    setExportingPptx(true)
    try {
      await exportDeckTransaction(
        params.projectId,
        'pptx',
        `${params.projectId}.pptx`,
      )
    } catch (error) {
      if (error instanceof ExportTransactionError && error.previousReleaseAvailable) {
        const accepted = await notify.confirm({
          title: 'Current export could not be rebuilt',
          message: `${error.message}\n\nDownload the explicitly labelled previous immutable release instead?`,
          confirmLabel: 'Download previous release',
          cancelLabel: 'Cancel',
        })
        if (accepted) {
          await downloadAuthenticatedFile(
            error.previousReleaseUrl || `/api/download/${params.projectId}.previous.pptx`,
            `${params.projectId}-previous.pptx`,
          )
          return
        }
      }
      void notify.alert({
        message: `${t('errorPrefix')}${error instanceof Error ? error.message : t('unknownError')}`,
        tone: 'error',
      })
    } finally {
      setExportingPptx(false)
    }
  }

  const downloadPdf = async () => {
    if (downloadBusy) return
    setDownloadOpen(false)
    setExportingPdf(true)
    try {
      await exportDeckTransaction(
        params.projectId,
        'pdf',
        `${params.projectId}.pdf`,
      )
    } catch (error) {
      void notify.alert({
        message: `${t('errorPrefix')}${error instanceof Error ? error.message : t('unknownError')}`,
        tone: 'error',
      })
    } finally {
      setExportingPdf(false)
    }
  }

  const downloadHtml = async () => {
    if (downloadBusy) return
    setDownloadOpen(false)
    setExportingHtml(true)
    try {
      await downloadAuthenticatedFile(
        `/api/download/${params.projectId}.html.zip`,
        `${params.projectId}-html.zip`,
      )
    } catch (error) {
      void notify.alert({
        message: `${t('errorPrefix')}${error instanceof Error ? error.message : t('unknownError')}`,
        tone: 'error',
      })
    } finally {
      setExportingHtml(false)
    }
  }

  useEffect(() => {
    if (livePreviewIndex === null) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setLivePreviewIndex(null)
        return
      }
      if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
        event.preventDefault()
        setLivePreviewIndex((idx) => {
          if (idx === null || previews.length === 0) return idx
          return Math.min(idx + 1, previews.length - 1)
        })
        return
      }
      if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
        event.preventDefault()
        setLivePreviewIndex((idx) => {
          if (idx === null || previews.length === 0) return idx
          return Math.max(idx - 1, 0)
        })
      }
    }
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    window.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = prevOverflow
      window.removeEventListener('keydown', onKey)
    }
  }, [livePreviewIndex, previews.length])

  // Drop the lightbox if the slide list shrinks, or we leave previewable stages.
  useEffect(() => {
    if (livePreviewIndex === null) return
    const previewable = wizardStage === 'generating' || wizardStage === 'done'
    if (!previewable || livePreviewIndex >= previews.length) {
      setLivePreviewIndex(null)
    }
  }, [livePreviewIndex, previews.length, wizardStage])

  // Load extracted PDF figures/tables for the Both-mode picker on stage 3.
  // Also hydrate duration/animations/prior selections from persisted result.json.
  useEffect(() => {
    if (wizardStage !== 'stage3') return
    let cancelled = false
    ;(async () => {
      let hydratedTableIds: string[] | null = null
      let hydratedFigureIds: string[] | null = null
      try {
        const prefsRes = await apiFetch(`/api/projects/${params.projectId}/production-settings`)
        if (prefsRes.ok) {
          const prefs = await prefsRes.json() as {
            proactive_speaker_notes?: boolean
            target_duration_minutes?: number
            proactive_custom_animations?: boolean
            custom_animation_effect?: string | null
            slide_transitions?: { popular?: string[]; effects?: string[] }
            proactive_narration_audio?: boolean
            image_source?: string
            selected_figure_ids?: string[]
            selected_table_ids?: string[]
            figure_render_mode?: 'exact' | 'ai_replica'
            table_render_mode?: 'exact' | 'ai_replica'
          }
          if (cancelled) return
          if (typeof prefs.proactive_speaker_notes === 'boolean') setSpeakerNotes(prefs.proactive_speaker_notes)
          if (typeof prefs.proactive_custom_animations === 'boolean') setAnimations(prefs.proactive_custom_animations)
          if (typeof prefs.custom_animation_effect === 'string' && prefs.custom_animation_effect.trim()) {
            setAnimationEffect(prefs.custom_animation_effect.trim().toLowerCase())
          }
          if (prefs.slide_transitions && Array.isArray(prefs.slide_transitions.effects) && prefs.slide_transitions.effects.length) {
            setTransitionCatalog({
              popular: Array.isArray(prefs.slide_transitions.popular) && prefs.slide_transitions.popular.length
                ? prefs.slide_transitions.popular
                : ['fade', 'push', 'wipe', 'cover', 'dissolve', 'cut', 'zoom'],
              effects: prefs.slide_transitions.effects,
            })
          }
          if (typeof prefs.proactive_narration_audio === 'boolean') setNarration(prefs.proactive_narration_audio)
          const minutes = Number(prefs.target_duration_minutes)
          if (Number.isFinite(minutes) && minutes > 0) {
            const rounded = Math.round(minutes)
            if ([5, 10, 15, 20].includes(rounded)) {
              setNotesDurationMin(rounded)
              setNotesDurationCustom('')
            } else {
              setNotesDurationCustom(String(rounded))
            }
          }
          if (Array.isArray(prefs.selected_figure_ids)) hydratedFigureIds = prefs.selected_figure_ids.map(String)
          if (Array.isArray(prefs.selected_table_ids)) hydratedTableIds = prefs.selected_table_ids.map(String)
        }
      } catch {
        /* keep Stage-3 defaults */
      }
      try {
        const res = await apiFetch(`/api/projects/${params.projectId}/source-figures`)
        if (!res.ok) return
        const data = await res.json() as { figures?: Array<{ id: string; thumb_url?: string; page?: number; file?: string }> }
        if (cancelled) return
        const figs = Array.isArray(data.figures) ? data.figures : []
        setSourceFigures(figs)
        if (hydratedFigureIds && hydratedFigureIds.length) {
          const allowed = new Set(figs.map(f => f.id))
          setSelectedFigureIds(hydratedFigureIds.filter(id => allowed.has(id)))
        } else {
          setSelectedFigureIds(figs.map(f => f.id))
        }
      } catch {
        /* no PDF figures — picker stays empty */
      }
      try {
        const res = await apiFetch(`/api/projects/${params.projectId}/source-tables`)
        if (!res.ok) return
        const data = await res.json() as {
          tables?: Array<{
            id: string
            page?: number
            caption?: string
            preview?: string[][]
            full?: string[][]
            rows?: number | null
            cols?: number | null
          }>
        }
        if (cancelled) return
        const tables = Array.isArray(data.tables) ? data.tables : []
        setSourceTables(tables)
        if (hydratedTableIds && hydratedTableIds.length) {
          const allowed = new Set(tables.map(t => t.id))
          setSelectedTableIds(hydratedTableIds.filter(id => allowed.has(id)))
        } else {
          setSelectedTableIds([])
        }
      } catch {
        /* no PDF tables — picker stays empty */
      }
    })()
    return () => { cancelled = true }
  }, [wizardStage, params.projectId, sourceExpected])

  // Source parsing continues after the home screen has navigated to the editor.
  // Stage 1 is intentionally held until the evidence bundle is ready.
  useEffect(() => {
    if (!sourceProcessing) return
    // Wait until the client HTTP upload finishes — polling before then can
    // false-error (no PDF yet) and release the stage-1 gate too early.
    if (clientUploading || peekPendingSourceUpload(params.projectId)) return
    // Completed / generating runs must not re-enter the stage-1 loading shell.
    if (wizardStage === 'done' || wizardStage === 'generating') {
      setSourceProcessing(false)
      return
    }
    let alive = true
    const refreshSourceStatus = async () => {
      try {
        const response = await apiFetch(`/api/projects/${params.projectId}/source-status`)
        if (!response.ok) {
          // 404 while project row is still committing — keep waiting.
          return
        }
        const data = await response.json() as SourceStatus
        if (!alive) return
        setSourceStatus(data)
        setProgress(data.progress || 0, data.message_key || data.message || 'sourceParsingDescription')
        if (data.ready || data.status === 'source_ready') {
          setSourceProcessing(false)
          // Only hold stage-1 shell while still in the strategy wizard.
          // Do not clobber a contract that already loaded successfully.
          const loadState = stage1LoadStateRef.current
          if (wizardStage === 'stage1' && loadState !== 'ready' && loadState !== 'error') {
            stage1FetchKeyRef.current = null
            setStage1Data(null)
            setStage1LoadState('loading')
            setLoading(true)
          }
        } else if (data.status === 'source_error') {
          setSourceProcessing(false)
          if (wizardStage === 'stage1') {
            setStage1LoadState('error')
            setLoading(false)
          }
        }
      } catch (error) {
        if (alive) console.error('Source status poll failed:', error)
      }
    }
    refreshSourceStatus()
    const timer = setInterval(refreshSourceStatus, 1500)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [sourceProcessing, clientUploading, wizardStage, params.projectId, t, setProgress])

  const handleConfirmStage1 = async () => {
    setLoading(true)
    try {
      const res = await apiFetch(`/api/projects/${params.projectId}/stage1/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          canvas,
          audience,
          communication_intent: communicationIntent,
          audience_outcome: audienceOutcome,
          core_message: coreMessage,
          delivery_context: deliveryContext,
          artifact_afterlife: artifactAfterlife,
          template_id: isTemplateMode ? template_id : null,
          language: lang === 'auto' ? null : lang
        })
      })
      if (res.ok) {
        if (isTemplateMode) {
          // Template mode: design comes from the selected template, skip Stage 2
          setWizardStage('stage3')
        } else {
          // Now fetch Stage 2
          const s2Res = await apiFetch(`/api/projects/${params.projectId}/stage2`)
          if (!s2Res.ok) {
            const errData = await s2Res.json()
            void notify.alert({ message: `${t('errorPrefix')}${errData.detail || t('designAlternativesFailed')}`, tone: 'error' })
            return
          }
          const s2Data = await s2Res.json()
          if (!s2Data || !s2Data.design_directions || !s2Data.design_directions.candidates) {
            void notify.alert({ message: `${t('errorPrefix')}${t('designAlternativesInvalid')}`, tone: 'error' })
            return
          }
          setStage2Data(s2Data)
          setSelectedDirection(s2Data.design_directions?.selected || 0)
          setPageCount(slidesOverride || s2Data.page_count?.value || '8-12')
          setImageNotes(s2Data.image_notes?.value || '')
          setWizardStage('stage2')
        }
      } else {
        const errData = await res.json()
        void notify.alert({ message: `${t('errorPrefix')}${errData.detail || t('contractConfirmFailed')}`, tone: 'error' })
      }
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleConfirmStage2 = async () => {
    if (!stage2Data) return
    setLoading(true)
    try {
      const direction = stage2Data.design_directions.candidates[selectedDirection]
      const res = await apiFetch(`/api/projects/${params.projectId}/stage2/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          delivery_purpose: stage2Data.recommend?.delivery_purpose || 'balanced',
          mode: stage2Data.recommend?.mode || 'pyramid',
          visual_style: direction.visual_style,
          image_usage: stage2Data.recommend?.image_usage || ['ai'],
          page_count: pageCount,
          template_application: stage2Data.template_application?.value || '',
          image_notes: imageNotes,
          color: {
            name_tr: direction.color.name_tr,
            palette: direction.color.palette
          },
          typography: {
            name_tr: direction.typography.name_tr,
            heading: direction.typography.heading,
            body: direction.typography.body,
            body_size: direction.typography.body_size
          },
          icons: direction.icons,
          image_strategy: direction.image_strategy
        })
      })
      if (res.ok) {
        setWizardStage('stage3')
      }
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleFinalGenerate = async () => {
    setPreviews([])
    // Source parse left the store at 100%; reset before the generating UI mounts
    // so the bar does not flash full then snap back to the run's real progress.
    setProgress(0, 'status_started')
    setGenerating(true)
    setWizardStage('generating')
    try {
      const res = await apiFetch(`/api/projects/${params.projectId}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image_ai_path: 'auto',
          formula_policy: 'mixed',
          proactive_speaker_notes: speakerNotes,
          target_duration_minutes: speakerNotes
            ? (notesDurationCustom.trim()
                ? Math.max(1, Number(notesDurationCustom) || 15)
                : notesDurationMin)
            : undefined,
          notes_wpm: speakerNotes ? 125 : undefined,
          proactive_custom_animations: animations,
          custom_animation_effect: animations ? animationEffect : null,
          proactive_narration_audio: narration,
          template_id: template_id || undefined,
          topic,
          n_slides: slidesParam === 'auto' ? null : slidesParam,
          language: lang === 'auto' ? null : lang,
          image_source: sourceExpected ? 'both' : 'ai',
          selected_figure_ids: sourceExpected ? selectedFigureIds : [],
          selected_table_ids: sourceExpected ? selectedTableIds : [],
          figure_render_mode: 'exact',
          table_render_mode: 'exact',
          ai_enrich_max_new: sourceExpected ? 0 : (aiIllustrations ? 3 : 0),
          additional_instructions: instructions || null,
          style_id: !template_id ? (cfg?.styleId || null) : null,
          presentation_style: !template_id ? (cfg?.styleId || null) : null,
        })
      })
      
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        setGenerating(false)
        setWizardStage('stage3')
        void notify.alert({ message: `${t('errorPrefix')}${errData.detail || t('generateStartError')}`, tone: 'error' })
        return
      }
      
      // Same-origin WS (Next rewrite locally, Caddy in cloud) — not API_URL host.
      const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws/${params.projectId}`)

      // If the WebSocket is unavailable, silently fall back to polling the
      // REST status endpoint so progress still updates without a page refresh.
      const startPolling = (reason: string) => {
        console.log(`WS unavailable (${reason}); falling back to status polling`)
        let polls = 0
        const pollId = setInterval(async () => {
          polls++
          if (polls > 400) {
            clearInterval(pollId)
            setGenerating(false)
            setWizardStage('stage3')
            notify.toast({ message: t('timeoutMsg'), tone: 'error' })
            return
          }
          try {
            const res = await apiFetch(`/api/projects`)
            const data = await res.json()
            const proj = (data.projects || []).find((p: any) => p.project_id === params.projectId)
            if (!proj) return
            if (isReadyStatus(proj.status)) {
              clearInterval(pollId)
              setProjectStatus(proj.status === 'completed' ? 'done' : proj.status)
              setGenerating(false)
              setWizardStage('done')
              apiFetch(`/api/projects/${params.projectId}/preview`)
                .then(r => r.json())
                .then(d => setPreviews(d.slides || []))
            } else if (
              proj.status === 'error' ||
              proj.status === 'failed' ||
              proj.status === 'cancelled'
            ) {
              clearInterval(pollId)
              apiFetch(`/api/projects/${params.projectId}/preview`)
                .then((r) => (r.ok ? r.json() : null))
                .then((d) =>
                  settleInterruptedRun(
                    proj.status,
                    d?.slides || [],
                    proj.error_message || proj.message,
                  ),
                )
                .catch(() =>
                  settleInterruptedRun(
                    proj.status,
                    null,
                    proj.error_message || proj.message,
                  ),
                )
            } else if (proj.progress !== undefined) {
              applyProjectStatus(proj.progress, proj)
            }
          } catch (err) {
            console.error('Status poll failed:', err)
          }
        }, 3000)
      }

      const wsTimeout = setTimeout(() => {
        ws.close()
        startPolling('timeout')
      }, 20000)

      let activityTimer: ReturnType<typeof setTimeout>
      const resetActivity = () => {
        clearTimeout(activityTimer)
        activityTimer = setTimeout(() => {
          ws.close()
          startPolling('inactivity')
        }, 60000)
      }

      ws.onopen = () => {
        wsActiveRef.current = true
        clearTimeout(wsTimeout)
        resetActivity()
      }

      ws.onerror = () => {
        startPolling('error')
      }

      ws.onclose = () => {
        wsActiveRef.current = false
        clearTimeout(wsTimeout)
        clearTimeout(activityTimer)
      }
      
      ws.onmessage = (event) => {
        resetActivity()
        const data = JSON.parse(event.data)
        // Ignore legacy websocket payloads; progress updates still flow.
        if (data.qa_event) return
        if (data.status_key === 'status_compile_error') {
          clearTimeout(wsTimeout)
          clearTimeout(activityTimer)
          setGenerating(false)
          setWizardStage('stage3')
          void notify.alert({ message: t('status_compile_error', { detail: data.detail || '' }), tone: 'error' })
          ws.close()
          return
        }
        if (data.status_key === 'status_quality_failed') {
          clearTimeout(wsTimeout)
          clearTimeout(activityTimer)
          setGenerating(false)
          setWizardStage('stage3')
          void notify.alert({ message: t('status_quality_failed', { detail: data.detail || '' }), tone: 'error' })
          ws.close()
          return
        }
        if (data.status_key === 'status_cancelled') {
          clearTimeout(wsTimeout)
          clearTimeout(activityTimer)
          setProgress(data.progress || 0, 'status_cancelled')
          ws.close()
          apiFetch(`/api/projects/${params.projectId}/preview`)
            .then((r) => (r.ok ? r.json() : null))
            .then((d) =>
              settleInterruptedRun('cancelled', d?.slides || [], data.detail || null),
            )
            .catch(() => settleInterruptedRun('cancelled', null, data.detail || null))
          return
        }
        if (data.status_key === 'status_awaiting_user_compile') {
          clearTimeout(wsTimeout)
          clearTimeout(activityTimer)
          setProgress(data.progress || 84, 'status_awaiting_user_compile')
          setAwaitingCompile(true)
          setGenerating(true)
          apiFetch(`/api/projects/${params.projectId}/preview`)
            .then(r => r.json())
            .then(d => setPreviews(d.slides || []))
            .catch(() => {})
          return
        }
        if (data.status_key === 'status_done_with_issues') {
          clearTimeout(wsTimeout)
          clearTimeout(activityTimer)
          setProgress(100, 'status_done_with_issues')
          setProjectStatus('done_with_issues')
          setGenerating(false)
          setAwaitingCompile(false)
          setWizardStage('done')
          ws.close()
          apiFetch(`/api/projects/${params.projectId}/preview`)
            .then(r => r.json())
            .then(d => setPreviews(d.slides || []))
          return
        }
        // Only forward placeholders the message actually carries; an undefined
        // one would render the word "undefined" into the sentence.
        const liveVars: Record<string, string | number> = {}
        for (const [name, value] of Object.entries({
          current: data.current ?? data.slide,
          total: data.total,
          title: data.title,
          detail: data.detail,
        })) {
          if (value !== undefined && value !== null && String(value).trim() !== '') {
            liveVars[name] = value as string | number
          }
        }
        let liveKey = normalizeStatusKey(data.status_key || data.status || '')
        if (
          (liveKey === 'status_generating_slide' || liveKey === 'status_slide' || liveKey === 'status_slide_titled')
          && liveVars.current !== undefined
          && liveVars.total !== undefined
        ) {
          if (!liveVars.title) liveVars.title = `Slide ${liveVars.current}`
          liveKey = 'status_slide_titled'
        }
        const terminalComplete =
          liveKey === 'status_completed' ||
          liveKey === 'completed' ||
          data.status === 'completed'
        const liveProgress =
          typeof data.progress === 'number'
            ? data.progress
            : terminalComplete
              ? 100
              : 0
        setProgress(liveProgress, liveKey || (terminalComplete ? 'status_completed' : liveKey), liveVars)
        if (liveProgress === 100 || terminalComplete) {
          clearTimeout(wsTimeout)
          clearTimeout(activityTimer)
          setProjectStatus('done')
          setGenerating(false)
          setAwaitingCompile(false)
          setWizardStage('done')
          ws.close()
          // Fetch previews
          apiFetch(`/api/projects/${params.projectId}/preview`)
            .then(r => r.json())
            .then(d => setPreviews(d.slides || []))
        }
      }
    } catch (err) {
      console.error(err)
      setGenerating(false)
      setWizardStage('stage3')
      void notify.alert({ message: t('generateStartError'), tone: 'error' })
    }
  }

  const handleAuthoringGenerate = async () => {
    if (authoringAction) return
    setAuthoringAction('generate')
    setAwaitingCompile(false)
    try {
      const response = await apiFetch(`/api/projects/${params.projectId}/generate/compile`, {
        method: 'POST',
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(payload.detail || t('authoringGenerateFailed'))
      setProgress(85, 'status_compiling')
    } catch (error) {
      setAwaitingCompile(true)
      void notify.alert({ message: `${t('errorPrefix')}${error instanceof Error ? error.message : t('unknownError')}`, tone: 'error' })
    } finally {
      setAuthoringAction(null)
    }
  }

  const handleCancelGeneration = async () => {
    if (isCancelling) return
    setIsCancelling(true)
    try {
      const res = await apiFetch(`/api/projects/${params.projectId}/cancel`, {
        method: 'POST',
      })
      if (!res.ok) {
        const error = await res.json().catch(() => ({}))
        throw new Error(error.detail || t('cancelGenerationFailed'))
      }
      const previewRes = await apiFetch(`/api/projects/${params.projectId}/preview`)
      const previewData = previewRes.ok ? await previewRes.json().catch(() => null) : null
      settleInterruptedRun('cancelled', previewData?.slides || [])
    } catch (err) {
      console.error('Generation cancellation failed:', err)
      void notify.alert({ message: `${t('errorPrefix')}${err instanceof Error ? err.message : t('unknownError')}`, tone: 'error' })
    } finally {
      setIsCancelling(false)
    }
  }

  const handleResumeGeneration = async () => {
    if (isResuming) return
    setIsResuming(true)
    try {
      const res = await apiFetch(`/api/projects/${params.projectId}/generate/resume`, {
        method: 'POST',
      })
      const payload = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(payload.detail || t('resumeGenerationFailed'))
      }
      setAwaitingCompile(false)
      setProjectStatus('queued')
      setInterruptDetail(null)
      setProgress(progress || 40, 'status_resuming')
      setGenerating(true)
      setWizardStage('generating')
    } catch (err) {
      console.error('Generation resume failed:', err)
      void notify.alert({
        message: `${t('errorPrefix')}${err instanceof Error ? err.message : t('unknownError')}`,
        tone: 'error',
      })
    } finally {
      setIsResuming(false)
    }
  }

  // Boot used to clear `loading` before the /stage1 effect set it again, which
  // flashed an empty strategy form. Keep the shell up until stage1 settles.
  const awaitingStage1 =
    statusResolved &&
    wizardStage === 'stage1' &&
    !sourceProcessing &&
    stage1LoadState !== 'ready' &&
    stage1LoadState !== 'error'
  // Never overlay the loading shell on done/generating — a stale `loading` flag
  // from the source poll used to stack "Opening workspace" on "Ready!".
  const showWizardLoading =
    (!statusResolved || loading || awaitingStage1) &&
    wizardStage !== 'done' &&
    wizardStage !== 'generating'
  // Boot check (!statusResolved) must not claim "restoring contract" — that copy
  // is only for a real stage-1 restore after we know the project is incomplete.
  const showStage1LoadingCopy =
    (statusResolved || isFreshCreate) &&
    wizardStage === 'stage1' &&
    !sourceProcessing &&
    (isFreshCreate || sourceExpected || awaitingStage1 || stage1LoadState === 'loading')
  const showBootLoadingCopy =
    !statusResolved && !isFreshCreate && wizardStage === 'stage1'
  const interrupted =
    projectStatus === 'cancelled' ||
    projectStatus === 'error' ||
    projectStatus === 'failed'

  return (
    <main
      className={`${styles.page} ${styles.pageReady} ${sora.variable} ${figtree.variable} ${figtree.className}`}
      aria-busy={showWizardLoading || undefined}
      aria-label={showBootLoadingCopy ? t('loadingBoot') : undefined}
    >
      <style>{`svg.slide-thumb, img.slide-thumb { width: 100%; max-width: 100%; height: auto; display: block; border-radius: 8px; border: var(--input-border); background: #fff; box-sizing: border-box; }`}</style>
      <div className={styles.wizardCard}>
        
        {/* Wizard Steps indicator */}
        {!showWizardLoading && wizardStage !== 'generating' && wizardStage !== 'done' && (
          <div className={styles.wizardSteps} aria-label={t('presentationSetupProgress')}>
            <div className={`${styles.wizardStep} ${wizardStage === 'stage1' ? styles.wizardStepActive : ''}`}>
              <span className={styles.wizardStepNumber}>1</span>
              <span className={styles.wizardStepLabel}>{stepLabel('step1')}</span>
            </div>
            <span className={styles.wizardStepLine} />
            {!isTemplateMode && <>
              <div className={`${styles.wizardStep} ${wizardStage === 'stage2' ? styles.wizardStepActive : ''}`}>
                <span className={styles.wizardStepNumber}>2</span>
                <span className={styles.wizardStepLabel}>{stepLabel('step2')}</span>
              </div>
              <span className={styles.wizardStepLine} />
            </>}
            <div className={`${styles.wizardStep} ${wizardStage === 'stage3' ? styles.wizardStepActive : ''}`}>
              <span className={styles.wizardStepNumber}>{isTemplateMode ? 2 : 3}</span>
              <span className={styles.wizardStepLabel}>{stepLabel('step3', { n: isTemplateMode ? 2 : 3 })}</span>
            </div>
          </div>
        )}

        {!showWizardLoading && wizardStage !== 'done' && wizardStage !== 'stage1' && (
          <header className={styles.stageHeader}>
            <h2 className={styles.stageTitle}>{t('strategyHeading')}</h2>
            {topic ? (
              <p className={styles.stageTopic} title={topic}>
                <span className={styles.stageTopicLabel}>{t('topicLabel')}</span>
                <span className={styles.stageTopicValue}>{topic}</span>
              </p>
            ) : null}
          </header>
        )}

        {showWizardLoading && (
          <section className={styles.loading} aria-live="polite" aria-busy="true">
            <div className={styles.loadingIcon} aria-hidden="true">
              <Icon name="sparkles" className="w-6 h-6" />
            </div>
            <div className={styles.loadingBody}>
              <div className={styles.loadingEyebrow}>
                {showBootLoadingCopy
                  ? t('loadingBootEyebrow')
                  : showStage1LoadingCopy
                    ? t('loadingStage1Eyebrow')
                    : t('loadingProjectEyebrow')}
              </div>
              <h2 className={styles.loadingTitle}>
                {showBootLoadingCopy
                  ? t('loadingBootTitle')
                  : showStage1LoadingCopy
                    ? t('loadingStage1Title')
                    : t('loadingProjectTitle')}
              </h2>
              <p className={styles.loadingCopy}>
                {showBootLoadingCopy
                  ? t('loadingBootCopy')
                  : showStage1LoadingCopy
                    ? t(sourceExpected ? 'loadingStage1Copy' : 'loadingStage1ScratchCopy')
                    : t('loadingProjectCopy')}
              </p>
              <div
                className={styles.loadingTrack}
                role="progressbar"
                aria-label={
                  showBootLoadingCopy
                    ? t('loadingBoot')
                    : showStage1LoadingCopy
                      ? t('loadingStage1')
                      : t('loadingProject')
                }
              >
                <div className={styles.loadingFill} />
              </div>
            </div>
          </section>
        )}

        {/* Mounted from stage 1 so section coverage is visible as soon as the PDF
            is parsed; the panel hides itself until it has something to report.
            On the done screen slide previews lead; grounding follows. */}
        {!showWizardLoading && wizardStage !== 'generating' && wizardStage !== 'done' && (
          <GroundingStatus
            apiUrl={API_URL}
            projectId={params.projectId}
            live={sourceProcessing}
          />
        )}

        {!showWizardLoading && wizardStage === 'stage1' && sourceProcessing && (
          <SourceParsingPanel
            progress={sourceStatus?.progress || progress}
            message={sourceStatusLabel}
            pages={sourceStatus?.pages || 0}
            tables={sourceStatus?.tables || 0}
            figures={sourceStatus?.figures || 0}
            formulas={sourceStatus?.formulas || 0}
            error={sourceStatus?.error}
          />
        )}

        {!showWizardLoading &&
          wizardStage === 'stage1' &&
          !sourceProcessing &&
          stage1Data &&
          (stage1LoadState === 'ready' || stage1LoadState === 'error') && (
          <div className={`${styles.strategyStage} ${styles.settingsStage}`}>
            <header className={styles.strategyHeader}>
              <span className={styles.eyebrow}><span className={styles.eyebrowMark} />{t('step1')}</span>
              <h1 className={styles.strategyTitle}>{t('strategyHeading')}</h1>
              <p className={styles.strategyLead}>{t('stage1Lead')}</p>
              <p className={styles.topicRow}>
                <span className={styles.topicLabel}>{t('topicLabel')}</span>
                <span className={styles.topicValue}>{topic}</span>
              </p>
            </header>

            <div className={styles.settingsStack}>
              <div className={styles.settingsPanel}>
                <div>
                  <h3 className={styles.settingsPanelTitle}>{t('contractBasics')}</h3>
                  <p className={styles.settingsPanelDesc}>{t('contractBasicsDesc')}</p>
                </div>
                <div className={styles.fieldGrid}>
                  {[
                    { key: 'audience', label: t('audience'), hint: t('audienceHint'), value: audience, set: setAudience },
                    { key: 'intent', label: t('intent'), hint: t('intentHint'), value: communicationIntent, set: setCommunicationIntent },
                    { key: 'outcome', label: t('outcome'), hint: t('outcomeHint'), value: audienceOutcome, set: setAudienceOutcome },
                    { key: 'delivery', label: t('delivery'), hint: t('deliveryHint'), value: deliveryContext, set: setDeliveryContext },
                  ].map(field => (
                    <div className={styles.field} key={field.key}>
                      <label className={styles.fieldLabel} htmlFor={`contract-${field.key}`}>{field.label}</label>
                      <AutoTextarea
                        id={`contract-${field.key}`}
                        className={styles.strategyInput}
                        value={field.value}
                        onChange={e => field.set(e.target.value)}
                        aria-describedby={`contract-${field.key}-hint`}
                      />
                      <p className={styles.fieldHint} id={`contract-${field.key}-hint`}>{field.hint}</p>
                    </div>
                  ))}
                </div>
              </div>

              <div className={`${styles.settingsPanel} ${styles.contractHighlight}`}>
                <div>
                  <h3 className={styles.settingsPanelTitle}>{t('coreMessage')}</h3>
                  <p className={styles.settingsPanelDesc}>{t('coreMessageHint')}</p>
                </div>
                <AutoTextarea
                  id="contract-core-message"
                  className={styles.strategyTextarea}
                  value={coreMessage}
                  onChange={e => setCoreMessage(e.target.value)}
                  aria-label={t('coreMessage')}
                />
              </div>

              <div className={styles.settingsPanel}>
                <div>
                  <h3 className={styles.settingsPanelTitle}>{t('afterlife')}</h3>
                  <p className={styles.settingsPanelDesc}>{t('afterlifeHint')}</p>
                </div>
                <AutoTextarea
                  id="contract-afterlife"
                  className={styles.strategyInput}
                  value={artifactAfterlife}
                  onChange={e => setArtifactAfterlife(e.target.value)}
                  aria-label={t('afterlife')}
                />
              </div>
            </div>

            <div className={styles.wizardActions}>
              <span className={styles.actionHint}>{isTemplateMode ? t('stage3Intro') : t('stage2Intro')}</span>
              <button type="button" className={styles.primaryButton} onClick={handleConfirmStage1}>
                {t('confirmContinue')}
                <Icon name="arrowRight" className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {!loading && wizardStage === 'stage2' && stage2Data && (
          <div className={styles.settingsStage}>
            <p className={styles.settingsIntro}>{t('stage2Intro')}</p>

            <div className={styles.settingsPanel}>
              <div className={styles.settingsFieldGrid}>
                <div className={styles.settingsField}>
                  <label className={styles.settingsFieldLabel} htmlFor="stage2-slide-count">{t('slideCount')}</label>
                  <input id="stage2-slide-count" type="text" value={pageCount} onChange={e => setPageCount(e.target.value)} className={styles.settingsInput} />
                </div>
                <div className={styles.settingsField}>
                  <label className={styles.settingsFieldLabel} htmlFor="stage2-image-notes">{t('imageNotes')}</label>
                  <input id="stage2-image-notes" type="text" value={imageNotes} onChange={e => setImageNotes(e.target.value)} className={styles.settingsInput} />
                </div>
              </div>
            </div>

            <h3 className={styles.settingsSectionTitle}>{t('designAlternatives')}</h3>
            <div className={styles.directionList}>
              {stage2Data.design_directions.candidates.map((candidate, idx) => (
                <div
                  key={idx}
                  role="button"
                  tabIndex={0}
                  onClick={() => setSelectedDirection(idx)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      setSelectedDirection(idx)
                    }
                  }}
                  className={styles.directionCard}
                  data-selected={selectedDirection === idx}
                >
                  <div className={styles.directionPreviewCol}>
                    <span className={styles.directionPreviewLabel}>{t('designPreviewLabel')}</span>
                    <DesignDirectionPreview
                      candidate={candidate}
                      topic={topic}
                      titleSlideLabel={t('designPreviewTitleSlide')}
                      contentSlideLabel={t('designPreviewContentSlide')}
                    />
                  </div>
                  <div className={styles.directionMetaCol}>
                    <div className={styles.directionMetaHeader}>
                      <span className={styles.directionName}>{candidate.name_tr}</span>
                      <span className={styles.directionStyle}>{t('styleLabel', { style: candidate.visual_style })}</span>
                    </div>
                    <p className={styles.directionNote}>{candidate.note_tr}</p>
                    <div className={styles.directionSwatches}>
                      {Object.entries(candidate.color.palette).map(([colorName, colorHex]) => (
                        <div
                          key={colorName}
                          className={styles.directionSwatch}
                          style={{ backgroundColor: colorHex }}
                          title={colorName}
                        />
                      ))}
                      <span className={styles.directionPaletteName}>{candidate.color.name_tr}</span>
                    </div>
                    <div className={styles.directionFonts}>
                      {t('fontIcons', { font: candidate.typography.name_tr, icons: candidate.icons })}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className={styles.wizardActions}>
              <button type="button" className={styles.ghostButton} onClick={() => setWizardStage('stage1')}>
                <Icon name="arrowLeft" className="w-4 h-4" />
                {t('back')}
              </button>
              <button type="button" className={styles.primaryButton} onClick={handleConfirmStage2}>
                {t('confirmContinue')}
                <Icon name="arrowRight" className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

        {wizardStage === 'stage3' && (
          <div className={styles.settingsStage}>
            <p className={styles.settingsIntro}>{t('stage3Intro')}</p>

            <div className={styles.settingsStack}>
              <div className={styles.assetPanel}>
                {sourceExpected ? (
                  <div>
                    <h3 className={styles.assetPanelTitle}>{t('imageSourcePdf')}</h3>
                    <p className={styles.assetPanelDesc}>{t('imageSourcePdfDesc')}</p>
                  </div>
                ) : (
                  <div>
                    <h3 className={styles.assetPanelTitle}>{t('imageSourceScratch')}</h3>
                    <p className={styles.assetPanelDesc}>{t('imageSourceScratchDesc')}</p>
                    <button
                      type="button"
                      className={`${styles.toggleCard} ${aiIllustrations ? styles.toggleCardActive : ''}`}
                      aria-pressed={aiIllustrations}
                      onClick={() => setAiIllustrations(v => !v)}
                    >
                      <span className={styles.toggleMark} aria-hidden="true">{aiIllustrations ? '✓' : ''}</span>
                      <span className={styles.toggleCopy}>
                        <span className={styles.toggleTitle}>{t('aiIllustrations')}</span>
                        <span className={styles.toggleDesc}>{t('aiIllustrationsDesc')}</span>
                      </span>
                    </button>
                  </div>
                )}
                {sourceExpected && sourceFigures.length > 0 && (
                  <div className={styles.assetBlock}>
                    <div className={styles.assetBlockHeader}>
                      <h4 className={styles.assetBlockTitle}>{t('selectPdfFigures')}</h4>
                      <span className={styles.assetBlockMeta}>
                        {selectedFigureIds.length}/{sourceFigures.length}
                      </span>
                    </div>
                    <p className={styles.assetBlockDesc}>{t('selectPdfFiguresDesc')}</p>
                    <div className={styles.assetToolbar}>
                      <button type="button" className={styles.assetToolbarBtn} onClick={() => setSelectedFigureIds(sourceFigures.map(f => f.id))}>{t('selectAllFigures')}</button>
                      <button type="button" className={styles.assetToolbarBtn} onClick={() => setSelectedFigureIds([])}>{t('clearFigures')}</button>
                    </div>
                    <div className={styles.figureGrid}>
                      {sourceFigures.map(fig => {
                        const selected = selectedFigureIds.includes(fig.id)
                        return (
                          <button
                            key={fig.id}
                            type="button"
                            aria-pressed={selected}
                            onClick={() => setSelectedFigureIds(prev => selected ? prev.filter(id => id !== fig.id) : [...prev, fig.id])}
                            className={`${styles.figureTile} ${selected ? styles.figureTileSelected : ''}`}
                          >
                            {selected && <span className={styles.assetCheck} aria-hidden="true">✓</span>}
                            {fig.thumb_url ? (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img className={styles.figureThumb} src={`${API_URL}${fig.thumb_url}`} alt={fig.file || fig.id} />
                            ) : (
                              <div className={styles.figureThumbFallback}>{fig.id}</div>
                            )}
                            <div className={styles.figureCaption}>p.{fig.page ?? '?'}</div>
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )}
                {sourceExpected && sourceTables.length > 0 && (
                  <div className={styles.assetBlock}>
                    <div className={styles.assetBlockHeader}>
                      <h4 className={styles.assetBlockTitle}>{t('selectPdfTables')}</h4>
                      <span className={styles.assetBlockMeta}>
                        {selectedTableIds.length}/{sourceTables.length}
                      </span>
                    </div>
                    <p className={styles.assetBlockDesc}>{t('selectPdfTablesDesc')}</p>
                    <div className={styles.assetToolbar}>
                      <button type="button" className={styles.assetToolbarBtn} onClick={() => setSelectedTableIds(sourceTables.map(f => f.id))}>{t('selectAllTables')}</button>
                      <button type="button" className={styles.assetToolbarBtn} onClick={() => setSelectedTableIds([])}>{t('clearTables')}</button>
                    </div>
                    <div className={styles.tableGrid}>
                      {sourceTables.map(table => {
                        const selected = selectedTableIds.includes(table.id)
                        const preview = Array.isArray(table.preview) && table.preview.length > 0
                          ? table.preview
                          : [['—', '—'], ['—', '—']]
                        return (
                          <div
                            key={table.id}
                            role="button"
                            tabIndex={0}
                            aria-pressed={selected}
                            onClick={() => setSelectedTableIds(prev => selected ? prev.filter(id => id !== table.id) : [...prev, table.id])}
                            onKeyDown={e => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault()
                                setSelectedTableIds(prev => selected ? prev.filter(id => id !== table.id) : [...prev, table.id])
                              }
                            }}
                            className={`${styles.tableCard} ${selected ? styles.tableCardSelected : ''}`}
                          >
                            {selected && <span className={styles.assetCheck} aria-hidden="true">✓</span>}
                            <div
                              className={styles.tableMini}
                              style={{ gridTemplateRows: `repeat(${Math.min(preview.length, 4)}, 1fr)` }}
                              aria-hidden="true"
                            >
                              {preview.slice(0, 4).map((row, rowIndex) => (
                                <div
                                  key={`${table.id}-r${rowIndex}`}
                                  style={{
                                    display: 'grid',
                                    gridTemplateColumns: `repeat(${Math.max(row.length, 1)}, 1fr)`,
                                    borderBottom: rowIndex < Math.min(preview.length, 4) - 1
                                      ? '1px solid color-mix(in srgb, var(--text-muted) 14%, transparent)'
                                      : 'none',
                                    background: rowIndex === 0 ? 'color-mix(in srgb, var(--text-muted) 8%, transparent)' : 'transparent',
                                  }}
                                >
                                  {row.map((cell, colIndex) => (
                                    <div
                                      key={`${table.id}-r${rowIndex}-c${colIndex}`}
                                      style={{
                                        padding: '2px 3px',
                                        fontSize: 8,
                                        lineHeight: 1.2,
                                        color: 'var(--text-primary)',
                                        fontWeight: rowIndex === 0 ? 700 : 500,
                                        overflow: 'hidden',
                                        whiteSpace: 'nowrap',
                                        textOverflow: 'ellipsis',
                                        borderRight: colIndex < row.length - 1
                                          ? '1px solid color-mix(in srgb, var(--text-muted) 12%, transparent)'
                                          : 'none',
                                        fontVariantNumeric: 'tabular-nums',
                                        textAlign: 'left',
                                      }}
                                    >
                                      {cell || ' '}
                                    </div>
                                  ))}
                                </div>
                              ))}
                            </div>
                            <div className={styles.tableTitle}>
                              {table.caption || `Table · p.${table.page ?? '?'}`}
                            </div>
                            <div className={styles.tableMetaRow}>
                              <span className={styles.tableBadge}>
                                p.{table.page ?? '?'}
                                {(table.rows != null || table.cols != null) ? ` · ${table.rows ?? '—'}×${table.cols ?? '—'}` : ''}
                              </span>
                              <button
                                type="button"
                                className={styles.tablePreviewLink}
                                onClick={e => {
                                  e.stopPropagation()
                                  setPreviewTableId(table.id)
                                }}
                              >
                                {t('previewTable')}
                              </button>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                    {previewTableId && (() => {
                      const table = sourceTables.find(item => item.id === previewTableId)
                      if (!table) return null
                      const selected = selectedTableIds.includes(table.id)
                      const matrix = (table.full && table.full.length > 0)
                        ? table.full
                        : (table.preview && table.preview.length > 0 ? table.preview : [['—']])
                      const colCount = Math.max(...matrix.map(row => row.length), 1)
                      return (
                        <div
                          role="dialog"
                          aria-modal="true"
                          aria-labelledby="table-preview-title"
                          className={styles.modalOverlay}
                          onClick={() => setPreviewTableId(null)}
                        >
                          <div
                            className={styles.modalPanel}
                            onClick={e => e.stopPropagation()}
                          >
                            <div className={styles.modalHeader}>
                              <h4 id="table-preview-title" className={styles.modalTitle}>
                                {table.caption || t('tablePreviewTitle')}
                              </h4>
                              <p className={styles.modalMeta}>
                                p.{table.page ?? '?'}
                                {(table.rows != null || table.cols != null) ? ` · ${table.rows ?? '—'}×${table.cols ?? '—'}` : ''}
                              </p>
                            </div>
                            <div className={styles.modalBody}>
                              <table style={{
                                borderCollapse: 'collapse',
                                width: '100%',
                                minWidth: colCount * 88,
                                fontSize: '0.82rem',
                              }}>
                                <tbody>
                                  {matrix.map((row, rowIndex) => (
                                    <tr key={`preview-r${rowIndex}`}>
                                      {Array.from({ length: colCount }, (_, colIndex) => (
                                        <td
                                          key={`preview-r${rowIndex}-c${colIndex}`}
                                          style={{
                                            border: '1px solid color-mix(in srgb, var(--text-muted) 22%, transparent)',
                                            padding: '0.4rem 0.55rem',
                                            background: rowIndex === 0 ? 'color-mix(in srgb, var(--text-muted) 10%, transparent)' : 'transparent',
                                            fontWeight: rowIndex === 0 ? 700 : 500,
                                            verticalAlign: 'top',
                                            whiteSpace: 'pre-wrap',
                                          }}
                                        >
                                          {row[colIndex] || ''}
                                        </td>
                                      ))}
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                            <div className={styles.modalActions}>
                              <button
                                type="button"
                                className={styles.ghostButton}
                                style={{ flex: '0 0 auto', minHeight: 44 }}
                                onClick={() => setPreviewTableId(null)}
                              >
                                {t('closeTablePreview')}
                              </button>
                              <button
                                type="button"
                                className={styles.primaryButton}
                                style={{ flex: '0 0 auto', minHeight: 44 }}
                                onClick={() => {
                                  setSelectedTableIds(prev => selected ? prev.filter(id => id !== table.id) : [...prev, table.id])
                                  setPreviewTableId(null)
                                }}
                              >
                                {selected ? t('removeThisTable') : t('useThisTable')}
                              </button>
                            </div>
                          </div>
                        </div>
                      )
                    })()}
                  </div>
                )}
              </div>

              <button
                type="button"
                className={`${styles.toggleCard} ${speakerNotes ? styles.toggleCardActive : ''}`}
                aria-pressed={speakerNotes}
                onClick={() => setSpeakerNotes(v => !v)}
              >
                <span className={styles.toggleMark} aria-hidden="true">✓</span>
                <span className={styles.toggleCopy}>
                  <span className={styles.toggleTitle}>{t('speakerNotes')}</span>
                  <span className={styles.toggleDesc}>{t('speakerNotesDesc')}</span>
                </span>
              </button>

              {speakerNotes && (
                <div className={styles.settingsPanel}>
                  <div>
                    <h4 className={styles.settingsPanelTitle}>{t('notesDuration')}</h4>
                    <p className={styles.settingsPanelDesc}>{t('notesDurationDesc')}</p>
                  </div>
                  <div className={styles.chipRow}>
                    {[5, 10, 15, 20].map((min) => {
                      const active = !notesDurationCustom.trim() && notesDurationMin === min
                      return (
                        <button
                          key={min}
                          type="button"
                          className={`${styles.chip} ${active ? styles.chipActive : ''}`}
                          onClick={() => {
                            setNotesDurationMin(min)
                            setNotesDurationCustom('')
                          }}
                        >
                          {min} min
                        </button>
                      )
                    })}
                    <label className={styles.chipCustom}>
                      {t('notesDurationCustom')}
                      <input
                        type="number"
                        min={1}
                        max={120}
                        value={notesDurationCustom}
                        onChange={(e) => setNotesDurationCustom(e.target.value)}
                        className={styles.chipCustomInput}
                      />
                    </label>
                  </div>
                  <p className={styles.estHint}>
                    {t('notesEstWords').replace(
                      '{words}',
                      String(
                        Math.round(
                          (notesDurationCustom.trim()
                            ? Math.max(1, Number(notesDurationCustom) || 15)
                            : notesDurationMin) *
                            125 *
                            0.88,
                        ),
                      ),
                    )}
                  </p>
                </div>
              )}

              <div className={styles.toggleStack}>
                <button
                  type="button"
                  className={`${styles.toggleCard} ${animations ? styles.toggleCardActive : ''}`}
                  aria-pressed={animations}
                  onClick={() => setAnimations(v => {
                    const next = !v
                    if (next && !animationEffect) setAnimationEffect('fade')
                    return next
                  })}
                >
                  <span className={styles.toggleMark} aria-hidden="true">✓</span>
                  <span className={styles.toggleCopy}>
                    <span className={styles.toggleTitle}>{t('animations')}</span>
                    <span className={styles.toggleDesc}>{t('animationsDesc')}</span>
                  </span>
                </button>
                {animations && (
                  <div className={styles.animationPicker} role="group" aria-label={t('animationsPick')}>
                    <p className={styles.animationPickerLabel}>{t('animationsPick')}</p>
                    <div className={styles.chipRow}>
                      <button
                        type="button"
                        className={`${styles.chip} ${animationEffect === 'random' ? styles.chipActive : ''}`}
                        onClick={() => setAnimationEffect('random')}
                      >
                        {t('animationsRandom')}
                      </button>
                      {transitionCatalog.popular.map((id) => (
                        <button
                          key={id}
                          type="button"
                          className={`${styles.chip} ${animationEffect === id ? styles.chipActive : ''}`}
                          onClick={() => setAnimationEffect(id)}
                        >
                          {id.replace(/-/g, ' ')}
                        </button>
                      ))}
                    </div>
                    <div className={styles.animationMoreRow}>
                      <span className={styles.animationMoreLabel}>{t('animationsMore')}</span>
                      <details className={styles.animationMenu}>
                        <summary className={styles.animationMenuTrigger}>
                          <span>
                            {transitionCatalog.popular.includes(animationEffect) || animationEffect === 'random'
                              ? t('animationsBrowse')
                              : animationEffect.replace(/-/g, ' ')}
                          </span>
                          <span className={styles.animationMenuChevron} aria-hidden="true">⌄</span>
                        </summary>
                        <div className={styles.animationMenuPopover} role="listbox" aria-label={t('animationsMore')}>
                          {transitionCatalog.effects
                            .filter((id) => !transitionCatalog.popular.includes(id))
                            .map((id) => (
                              <button
                                key={id}
                                type="button"
                                role="option"
                                aria-selected={animationEffect === id}
                                className={`${styles.animationMenuOption} ${animationEffect === id ? styles.animationMenuOptionActive : ''}`}
                                onClick={(event) => {
                                  setAnimationEffect(id)
                                  event.currentTarget.closest('details')?.removeAttribute('open')
                                }}
                              >
                                <span>{id.replace(/-/g, ' ')}</span>
                                {animationEffect === id && <span aria-hidden="true">✓</span>}
                              </button>
                            ))}
                        </div>
                      </details>
                    </div>
                  </div>
                )}
              </div>

              <button
                type="button"
                className={`${styles.toggleCard} ${narration ? styles.toggleCardActive : ''}`}
                aria-pressed={narration}
                onClick={() => setNarration(v => !v)}
              >
                <span className={styles.toggleMark} aria-hidden="true">✓</span>
                <span className={styles.toggleCopy}>
                  <span className={styles.toggleTitle}>{t('narration')}</span>
                  <span className={styles.toggleDesc}>{t('narrationDesc')}</span>
                </span>
              </button>
            </div>

            <div className={styles.wizardActions}>
              <button
                type="button"
                className={styles.ghostButton}
                onClick={() => setWizardStage(isTemplateMode ? 'stage1' : 'stage2')}
              >
                <Icon name="arrowLeft" className="w-4 h-4" />
                {t('back')}
              </button>
              <button type="button" className={styles.successButton} onClick={handleFinalGenerate}>
                <Icon name="sparkles" className="w-4 h-4" />
                {t('generateBtn2')}
              </button>
            </div>
          </div>
        )}

        {wizardStage === 'generating' && (
          <div>
            <GenerationProgress
              statusKey={statusKey}
              statusVars={statusVars}
              progress={progress}
              onCancel={handleCancelGeneration}
              cancelling={isCancelling}
            />

            {awaitingCompile && (
              <div className={styles.gatePanel}>
                <p className={styles.gateEyebrow}>
                  <span className={styles.gateEyebrowMark} aria-hidden="true" />
                  {t('authoringGateEyebrow')}
                </p>
                <h3 className={styles.gateTitle}>{t('authoringGateTitle')}</h3>
                <p className={styles.gateBody}>{t('authoringGateBody')}</p>
                <div className={styles.gateActions}>
                  <button
                    type="button"
                    className={styles.gateGenerate}
                    disabled={!!authoringAction}
                    onClick={handleAuthoringGenerate}
                    aria-busy={authoringAction === 'generate'}
                  >
                    <Icon name="sparkles" className="w-4 h-4" />
                    {authoringAction === 'generate' ? t('authoringGenerateBusy') : t('authoringGenerate')}
                  </button>
                </div>
              </div>
            )}

            {liveThumbs.length > 0 && (
              <div className={styles.livePreviews}>
                <p className={styles.livePreviewsTitle}>{t('generatingLive')}</p>
                <div className={styles.livePreviewGrid}>
                  {liveThumbs.map((slide, idx) => (
                    <button
                      key={slide.filename || idx}
                      type="button"
                      className={styles.livePreviewCard}
                      // The strip is filtered, so the lightbox needs this
                      // slide's index in `previews` — that is what it and its
                      // prev/next navigation address.
                      onClick={() => setLivePreviewIndex(previews.indexOf(slide))}
                      aria-label={t('previewSlide', { n: idx + 1 })}
                    >
                      <div className={styles.livePreviewThumb}>
                        <SvgThumb apiUrl={API_URL} url={slide.url} alt={slide.filename} />
                      </div>
                      <span className={styles.livePreviewLabel}>{t('slideLabel', { n: idx + 1 })}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Provenance last and collapsed: reassurance, not the headline. */}
            <GroundingStatus
              apiUrl={API_URL}
              projectId={params.projectId}
              live
              variant="compact"
            />
          </div>
        )}

        {wizardStage === 'done' && (
          <div
            className={styles.doneStage}
            data-interrupted={interrupted || undefined}
            data-instant={suppressStageMotion || undefined}
          >
            <header className={styles.doneHero} data-tone={interrupted ? 'alert' : 'ready'}>
              <div className={styles.doneHeroMain}>
                <div
                  className={styles.doneBadge}
                  data-tone={
                    projectStatus === 'cancelled'
                      ? 'cancelled'
                      : interrupted
                        ? 'error'
                        : undefined
                  }
                  aria-hidden="true"
                >
                  <Icon
                    name={
                      projectStatus === 'cancelled'
                        ? 'x'
                        : interrupted
                          ? 'alert'
                          : 'check'
                    }
                    className="w-5 h-5"
                  />
                </div>
                <div className={styles.doneHeroCopy}>
                  <p className={styles.doneKicker}>
                    {projectStatus === 'cancelled'
                      ? t('status_cancelled')
                      : statusKey === 'status_llm_unavailable'
                        ? t('status_llm_unavailable')
                        : interrupted
                          ? t('statusFailed')
                          : t('readyTitle')}
                    {!interrupted && previews.length > 0 ? (
                      <span className={styles.doneKickerMeta}>
                        · {t('slidesCount', { n: previews.length })}
                      </span>
                    ) : null}
                  </p>
                  <h3 className={styles.doneTitle}>
                    {topic?.trim() || t('untitledPresentation')}
                  </h3>
                  {interrupted ? (
                    <p className={styles.doneLead}>{t('resumeGenerationHint')}</p>
                  ) : null}
                </div>
              </div>

              {!interrupted ? (
                <div className={styles.doneHeroActions}>
                  <button
                    type="button"
                    className={styles.donePrimary}
                    onClick={() => router.push(`/editor/${params.projectId}/deck`)}
                  >
                    <Icon name="pencil" className="w-4 h-4" />
                    <span>{t('openDeckEditor')}</span>
                  </button>
                  <div className={styles.downloadSplit} ref={downloadMenuRef}>
                    <button
                      type="button"
                      className={styles.doneSuccess}
                      aria-haspopup="menu"
                      aria-expanded={downloadOpen}
                      aria-label={t('downloadMenu')}
                      disabled={downloadBusy}
                      onClick={() => setDownloadOpen((open) => !open)}
                    >
                      <Icon name="download" className="w-4 h-4" />
                      <span>
                        {exportingPptx
                          ? 'Rebuilding…'
                          : exportingPdf
                          ? t('exportingPdf')
                          : exportingHtml
                            ? t('exportingHtml')
                            : t('download')}
                      </span>
                      <span className={styles.downloadCaret} aria-hidden="true" />
                    </button>
                    {downloadOpen && (
                      <div className={styles.downloadMenu} role="menu" aria-label={t('downloadMenu')}>
                        <button
                          type="button"
                          role="menuitem"
                          className={styles.downloadMenuItem}
                          disabled={downloadBusy}
                          onClick={() => void downloadPptx()}
                        >
                          <span className={styles.downloadFormat}>{t('downloadPptxShort')}</span>
                          <span className={styles.downloadFormatDesc}>{exportingPptx ? 'Rebuilding…' : t('downloadPptx')}</span>
                        </button>
                        <button
                          type="button"
                          role="menuitem"
                          className={styles.downloadMenuItem}
                          disabled={downloadBusy}
                          onClick={() => void downloadPdf()}
                        >
                          <span className={styles.downloadFormat}>{t('downloadPdfShort')}</span>
                          <span className={styles.downloadFormatDesc}>
                            {exportingPdf ? t('exportingPdf') : t('downloadPdf')}
                          </span>
                        </button>
                        <button
                          type="button"
                          role="menuitem"
                          className={styles.downloadMenuItem}
                          disabled={downloadBusy}
                          onClick={() => void downloadHtml()}
                        >
                          <span className={styles.downloadFormat}>{t('downloadHtmlShort')}</span>
                          <span className={styles.downloadFormatDesc}>
                            {exportingHtml ? t('exportingHtml') : t('downloadHtml')}
                          </span>
                        </button>
                      </div>
                    )}
                  </div>
                  <button
                    type="button"
                    className={styles.doneGhost}
                    onClick={() => router.push('/')}
                  >
                    {t('newPresentation')}
                  </button>
                </div>
              ) : (
                <div className={styles.doneHeroActions}>
                  <button
                    type="button"
                    className={styles.doneResume}
                    disabled={isResuming}
                    onClick={() => void handleResumeGeneration()}
                  >
                    <Icon name="play" className="w-4 h-4" />
                    <span>{isResuming ? t('resumingGeneration') : t('resumeGeneration')}</span>
                  </button>
                  {previews.length > 0 && (
                    <button
                      type="button"
                      className={styles.doneGhost}
                      onClick={() => router.push(`/editor/${params.projectId}/deck`)}
                    >
                      <Icon name="pencil" className="w-4 h-4" />
                      <span>{t('openDeckEditor')}</span>
                    </button>
                  )}
                  <button
                    type="button"
                    className={styles.doneGhost}
                    onClick={() => router.push('/history')}
                  >
                    {t('historyTitle')}
                  </button>
                </div>
              )}

              {interrupted && interruptDetail ? (
                <p className={styles.doneErrorDetail}>{interruptDetail}</p>
              ) : null}
            </header>

            {previews.length > 0 && (
              <section className={styles.donePreviews} aria-label={t('slidesPreview')}>
                <div className={styles.donePreviewGrid}>
                  {previews.map((slide, idx) => (
                    <button
                      key={idx}
                      type="button"
                      className={styles.donePreviewCard}
                      onClick={() => setLivePreviewIndex(idx)}
                      aria-label={t('previewSlide', { n: idx + 1 })}
                    >
                      <div className={styles.donePreviewThumb}>
                        <SvgThumb apiUrl={API_URL} url={slide.url} alt={slide.filename} />
                      </div>
                      <span className={styles.donePreviewLabel}>
                        {t('slideLabel', { n: idx + 1 })}
                      </span>
                    </button>
                  ))}
                </div>
              </section>
            )}

            <GroundingStatus
              apiUrl={API_URL}
              projectId={params.projectId}
              live={false}
              className={styles.doneStackPanel}
            />
          </div>
        )}

        {livePreviewIndex !== null && previews[livePreviewIndex] && (
          <SlideLightbox
            apiUrl={API_URL}
            eyebrow={t('slidesPreview')}
            ariaLabel={t('previewSlide', { n: livePreviewIndex + 1 })}
            index={livePreviewIndex}
            total={previews.length}
            slideUrl={previews[livePreviewIndex].url}
            slideAlt={previews[livePreviewIndex].filename}
            hint={t('slidePreviewHint')}
            onClose={() => setLivePreviewIndex(null)}
            onPrev={() => setLivePreviewIndex((idx) => (idx === null ? idx : Math.max(0, idx - 1)))}
            onNext={() =>
              setLivePreviewIndex((idx) =>
                idx === null ? idx : Math.min(previews.length - 1, idx + 1),
              )
            }
            closeLabel={t('closePreview')}
            previousLabel={t('previousSlide')}
            nextLabel={t('nextSlide')}
            action={
              wizardStage === 'done' ? (
                <button
                  type="button"
                  className={lightboxStyles.slideLightboxAction}
                  onClick={() => {
                    const slide = livePreviewIndex
                    setLivePreviewIndex(null)
                    router.push(`/editor/${params.projectId}/deck?slide=${slide}`)
                  }}
                >
                  <Icon name="pencil" className="w-4 h-4" />
                  <span>{t('editThisSlide')}</span>
                </button>
              ) : undefined
            }
          />
        )}
      </div>

    </main>
  )
}
