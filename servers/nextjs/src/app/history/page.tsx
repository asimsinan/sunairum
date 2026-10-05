'use client'

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import { Figtree, Sora } from 'next/font/google'
import { useUI } from '@/lib/i18n'
import { API_URL, apiFetch, downloadAuthenticatedFile, exportDeckTransaction, ExportTransactionError } from '@/lib/api'
import Icon from '@/components/Icon'
import { useWizardStore } from '@/store/wizardStore'
import { notify } from '@/components/feedback/notify'
import { touchProject } from '@/lib/touchProject'
import CoverThumb from '@/components/library/CoverThumb'
import LibraryCardMenu from '@/components/library/LibraryCardMenu'
import LibraryToolbar from '@/components/library/LibraryToolbar'
import { formatRelativeTime } from '@/components/library/relativeTime'

const sora = Sora({ subsets: ['latin'], weight: ['600', '700'] })
const figtree = Figtree({ subsets: ['latin'], weight: ['400', '600', '700', '800'] })
import {
  STATUS_BADGE,
  isActiveStatus,
  isDraftStatus,
  isFailedStatus,
  isReadyStatus,
  projectTitle,
  type LibraryFilter,
  type LibraryProject,
  type LibrarySort,
  type LibraryView,
} from '@/components/library/types'
import styles from './history.module.css'

const ACTIVE_POLL_MS = 2000
const IDLE_POLL_MS = 8000
const VIEW_STORAGE_KEY = 'sunairum.library.view'

export default function HistoryPage() {
  const { t, lang } = useUI()
  const router = useRouter()
  const setWizardConfig = useWizardStore((s) => s.setConfig)
  const [pastProjects, setPastProjects] = useState<LibraryProject[]>([])
  const [loading, setLoading] = useState(true)
  const [cancellingProjectId, setCancellingProjectId] = useState<string | null>(null)
  const [resumingProjectId, setResumingProjectId] = useState<string | null>(null)
  const [downloadMenuId, setDownloadMenuId] = useState<string | null>(null)
  const [exportingPdfId, setExportingPdfId] = useState<string | null>(null)
  const [exportingPptxId, setExportingPptxId] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<LibraryFilter>('all')
  const [sort, setSort] = useState<LibrarySort>('last_opened')
  const [view, setView] = useState<LibraryView>('grid')
  const hasActiveRef = useRef(false)
  const listEpochRef = useRef(0)
  const locale = lang === 'en' ? 'en-US' : 'tr-TR'

  useEffect(() => {
    try {
      const stored = localStorage.getItem(VIEW_STORAGE_KEY)
      if (stored === 'grid' || stored === 'list') setView(stored)
    } catch {
      /* ignore */
    }
  }, [])

  const changeView = (next: LibraryView) => {
    setView(next)
    try {
      localStorage.setItem(VIEW_STORAGE_KEY, next)
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    let cancelled = false
    let timeout: ReturnType<typeof setTimeout> | null = null
    let inFlight = false

    const schedule = (delay: number) => {
      if (cancelled) return
      if (timeout) clearTimeout(timeout)
      timeout = setTimeout(tick, delay)
    }

    const tick = async () => {
      if (cancelled || inFlight) {
        schedule(hasActiveRef.current ? ACTIVE_POLL_MS : IDLE_POLL_MS)
        return
      }
      inFlight = true
      try {
        const epoch = listEpochRef.current
        const res = await apiFetch('/api/projects')
        const data = await res.json()
        if (cancelled || epoch !== listEpochRef.current) return
        if (data && data.projects) {
          setPastProjects(data.projects)
          hasActiveRef.current = data.projects.some((p: LibraryProject) =>
            isActiveStatus(p.status),
          )
        }
      } catch (err) {
        console.error('Error loading past projects', err)
      } finally {
        inFlight = false
        setLoading(false)
        if (!cancelled && !document.hidden) {
          schedule(hasActiveRef.current ? ACTIVE_POLL_MS : IDLE_POLL_MS)
        }
      }
    }

    const onVisibility = () => {
      if (document.hidden) {
        if (timeout) clearTimeout(timeout)
        timeout = null
        return
      }
      tick()
    }

    tick()
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      cancelled = true
      if (timeout) clearTimeout(timeout)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [])

  const hydrateWizard = (proj: LibraryProject) => {
    setWizardConfig({
      projectId: proj.project_id,
      entry: 'open',
      topic: proj.topic || projectTitle(proj, t('untitledPresentation')),
      mode: 'scratch',
      lang: lang === 'en' ? 'en' : 'auto',
      slides: 'auto',
      hasSource: Boolean(proj.has_pdf),
    })
  }

  const openEditor = (proj: LibraryProject) => {
    touchProject(proj.project_id)
    hydrateWizard(proj)
    router.push(`/editor/${proj.project_id}`)
  }

  const handleDeleteProject = async (projectId: string) => {
    const confirmed = await notify.confirm({
      title: t('delete'),
      message: t('confirmDelete'),
      tone: 'danger',
      confirmLabel: t('delete'),
      cancelLabel: t('cancel'),
    })
    if (!confirmed) return
    try {
      const res = await apiFetch(`/api/projects/${projectId}`, { method: 'DELETE' })
      if (res.ok) {
        setPastProjects((prev) => prev.filter((p) => p.project_id !== projectId))
      }
    } catch (err) {
      console.error('Error deleting project', err)
    }
  }

  const handleClearAll = async () => {
    const confirmed = await notify.confirm({
      title: t('clearAll'),
      message: t('confirmClearAll'),
      tone: 'danger',
      confirmLabel: t('delete'),
      cancelLabel: t('cancel'),
    })
    if (!confirmed) return
    try {
      const res = await apiFetch('/api/projects', { method: 'DELETE' })
      if (!res.ok) {
        const error = await res.json().catch(() => ({}))
        const detail =
          typeof error?.detail === 'string'
            ? error.detail
            : error?.detail?.message || t('unknownError')
        throw new Error(detail)
      }
      listEpochRef.current += 1
      setPastProjects([])
      hasActiveRef.current = false
    } catch (err) {
      console.error('Error clearing all projects', err)
      void notify.alert({
        message: `${t('errorPrefix')}${err instanceof Error ? err.message : t('unknownError')}`,
        tone: 'error',
      })
    }
  }

  const handleDownloadPdf = async (projectId: string) => {
    if (exportingPdfId) return
    setExportingPdfId(projectId)
    setDownloadMenuId(null)
    try {
      await exportDeckTransaction(projectId, 'pdf', `${projectId}.pdf`)
    } catch (err) {
      console.error('PDF export failed:', err)
      void notify.alert({
        message: `${t('errorPrefix')}${err instanceof Error ? err.message : t('unknownError')}`,
        tone: 'error',
      })
    } finally {
      setExportingPdfId(null)
    }
  }

  const handleDownloadPptx = async (projectId: string) => {
    if (exportingPptxId) return
    setExportingPptxId(projectId)
    setDownloadMenuId(null)
    try {
      await exportDeckTransaction(projectId, 'pptx', `${projectId}.pptx`)
    } catch (err) {
      if (err instanceof ExportTransactionError && err.previousReleaseAvailable) {
        const accepted = await notify.confirm({
          title: 'Current export could not be rebuilt',
          message: `${err.message}\n\nDownload the explicitly labelled previous immutable release instead?`,
          confirmLabel: 'Download previous release',
          cancelLabel: 'Cancel',
        })
        if (accepted) {
          await downloadAuthenticatedFile(
            err.previousReleaseUrl || `/api/download/${projectId}.previous.pptx`,
            `${projectId}-previous.pptx`,
          )
          return
        }
      }
      void notify.alert({
        message: `${t('errorPrefix')}${err instanceof Error ? err.message : t('unknownError')}`,
        tone: 'error',
      })
    } finally {
      setExportingPptxId(null)
    }
  }

  const handleCancelGeneration = async (projectId: string) => {
    if (cancellingProjectId) return
    setCancellingProjectId(projectId)
    try {
      const res = await apiFetch(`/api/projects/${projectId}/cancel`, { method: 'POST' })
      if (!res.ok) {
        const error = await res.json().catch(() => ({}))
        throw new Error(error.detail || t('cancelGenerationFailed'))
      }
      setPastProjects((prev) =>
        prev.map((project) =>
          project.project_id === projectId
            ? { ...project, status: 'cancelled', error_message: null }
            : project,
        ),
      )
    } catch (err) {
      console.error('Generation cancellation failed:', err)
      void notify.alert({
        message: `${t('errorPrefix')}${err instanceof Error ? err.message : t('unknownError')}`,
        tone: 'error',
      })
    } finally {
      setCancellingProjectId(null)
    }
  }

  const handleResumeGeneration = async (proj: LibraryProject) => {
    if (resumingProjectId) return
    setResumingProjectId(proj.project_id)
    setDownloadMenuId(null)
    try {
      const res = await apiFetch(`/api/projects/${proj.project_id}/generate/resume`, {
        method: 'POST',
      })
      const payload = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(payload.detail || t('resumeGenerationFailed'))
      }
      setPastProjects((prev) =>
        prev.map((project) =>
          project.project_id === proj.project_id
            ? {
                ...project,
                status: 'queued',
                message_key: 'status_resuming',
                error_message: null,
              }
            : project,
        ),
      )
      openEditor(proj)
    } catch (err) {
      console.error('Generation resume failed:', err)
      void notify.alert({
        message: `${t('errorPrefix')}${err instanceof Error ? err.message : t('unknownError')}`,
        tone: 'error',
      })
    } finally {
      setResumingProjectId(null)
    }
  }

  const renderBadge = (proj: LibraryProject) => {
    const badge = STATUS_BADGE[proj.status] || STATUS_BADGE.pending
    // Icon and colour answer the same question, so they read the same status:
    // `isReadyStatus` also covers the legacy `completed`, which used to draw a
    // grey chip with no icon for a deck that was in fact finished.
    const tone = isActiveStatus(proj.status)
      ? 'active'
      : proj.status === 'done_with_issues'
        ? 'warning'
        : isReadyStatus(proj.status)
          ? 'done'
          : isFailedStatus(proj.status)
            ? 'error'
            : isDraftStatus(proj.status)
              ? 'draft'
              : 'muted'
    // A ready deck reads ready. `done_with_issues` used an alert triangle, which
    // denied its own label — the deck is finished and usable; what is pending is
    // a review of export advisories, not the deck. That qualification belongs to
    // the amber tone and the tooltip detail, so both ready states draw the same
    // icon and differ only in colour.
    const icon = isActiveStatus(proj.status) ? (
      <span className={styles.badgeDot} />
    ) : isReadyStatus(proj.status) ? (
      <Icon name="check" />
    ) : isDraftStatus(proj.status) ? (
      <Icon name="pencil" />
    ) : isFailedStatus(proj.status) ? (
      <Icon name="x" />
    ) : (
      <span aria-hidden="true" />
    )
    const badgeTitle = proj.status === 'done_with_issues'
      ? t('statusDoneWithIssuesDetail')
      : t(badge.labelKey)
    return (
      <span className={styles.badge} data-status={tone} title={badgeTitle}>
        <span className={styles.badgeIcon}>{icon}</span>
        <span className={styles.badgeLabel}>{t(badge.labelKey)}</span>
      </span>
    )
  }

  const projectMessage = (proj: LibraryProject) => {
    if (proj.message_key) {
      const translated = t(proj.message_key)
      if (translated !== proj.message_key) return translated
    }
    return proj.error_message || proj.message || ''
  }

  const renderProgress = (proj: LibraryProject) => {
    if (!isActiveStatus(proj.status)) return null
    const pct = Math.round(Math.min(Math.max(proj.progress || 0, 0), 100))
    return (
      <div className={styles.progressBlock}>
        <div className={styles.progressMeta}>
          <span>
            {proj.slide_total && proj.slide_total > 0
              ? t('slideProgress', {
                  current: proj.slide_current || 0,
                  total: proj.slide_total,
                })
              : t('statusGenerating')}
          </span>
          <span>{pct}%</span>
        </div>
        <div className={styles.progressTrack}>
          <div className={styles.progressValue} style={{ width: `${pct}%` }} />
        </div>
      </div>
    )
  }

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    let items = pastProjects.filter((proj) => {
      if (filter === 'ready' && !isReadyStatus(proj.status)) return false
      if (filter === 'draft' && !isDraftStatus(proj.status)) return false
      if (filter === 'failed' && !isFailedStatus(proj.status)) return false
      if (filter === 'generating' && !isActiveStatus(proj.status)) return false
      if (!q) return true
      const hay = [
        projectTitle(proj, ''),
        proj.topic || '',
        proj.project_id,
      ]
        .join(' ')
        .toLowerCase()
      return hay.includes(q)
    })
    items = [...items].sort((a, b) => {
      if (sort === 'created') {
        return (b.created_at || 0) - (a.created_at || 0)
      }
      const ao = a.last_opened_at || 0
      const bo = b.last_opened_at || 0
      if (ao !== bo) return bo - ao
      return (b.created_at || 0) - (a.created_at || 0)
    })
    return items
  }, [pastProjects, search, filter, sort])

  // Continue = resume your work (last opened), not whatever job is running.
  const continueProject = useMemo(() => {
    const opened = [...pastProjects]
      .filter((p) => p.last_opened_at)
      .sort((a, b) => (b.last_opened_at || 0) - (a.last_opened_at || 0))
    if (opened[0]) return opened[0]
    const byCreated = [...pastProjects].sort(
      (a, b) => (b.created_at || 0) - (a.created_at || 0),
    )
    return byCreated[0] || null
  }, [pastProjects])

  const activeProjects = useMemo(
    () => pastProjects.filter((p) => isActiveStatus(p.status)),
    [pastProjects],
  )

  const countLabel =
    pastProjects.length === 1
      ? t('count_one')
      : t('count', { n: pastProjects.length })

  const cardMenu = (proj: LibraryProject) => (
    <LibraryCardMenu
      open={downloadMenuId === proj.project_id}
      onOpenChange={(next) => setDownloadMenuId(next ? proj.project_id : null)}
      label={t('libraryMore')}
    >
      {(isReadyStatus(proj.status) ||
        proj.status === 'draft' ||
        proj.status === 'draft_invalid') && (
        <button
          type="button"
          role="menuitem"
          className={styles.menuItem}
          onClick={(event) => {
            event.stopPropagation()
            setDownloadMenuId(null)
            touchProject(proj.project_id)
            hydrateWizard(proj)
            router.push(`/editor/${proj.project_id}/deck`)
          }}
        >
          {t('openDeckEditor')}
        </button>
      )}
      {proj.has_pptx && (
        <>
          <button
            type="button"
            role="menuitem"
            className={styles.menuItem}
            onClick={(event) => {
              event.stopPropagation()
              setDownloadMenuId(null)
              void handleDownloadPptx(proj.project_id)
            }}
            disabled={exportingPptxId === proj.project_id}
          >
            {exportingPptxId === proj.project_id ? 'Rebuilding…' : t('downloadPptxShort')}
          </button>
          <button
            type="button"
            role="menuitem"
            className={styles.menuItem}
            disabled={exportingPdfId === proj.project_id}
            onClick={(event) => {
              event.stopPropagation()
              void handleDownloadPdf(proj.project_id)
            }}
          >
            {exportingPdfId === proj.project_id ? t('exportingPdf') : t('downloadPdfShort')}
          </button>
        </>
      )}
      {isActiveStatus(proj.status) && (
        <button
          type="button"
          role="menuitem"
          className={styles.menuItem}
          disabled={cancellingProjectId === proj.project_id}
          onClick={(event) => {
            event.stopPropagation()
            setDownloadMenuId(null)
            void handleCancelGeneration(proj.project_id)
          }}
        >
          {cancellingProjectId === proj.project_id
            ? t('cancellingGeneration')
            : t('cancelGeneration')}
        </button>
      )}
      {(proj.status === 'cancelled' ||
        proj.status === 'error' ||
        proj.status === 'failed') && (
        <button
          type="button"
          role="menuitem"
          className={styles.menuItem}
          disabled={resumingProjectId === proj.project_id}
          onClick={(event) => {
            event.stopPropagation()
            void handleResumeGeneration(proj)
          }}
        >
          {resumingProjectId === proj.project_id
            ? t('resumingGeneration')
            : t('resumeGeneration')}
        </button>
      )}
      <button
        type="button"
        role="menuitem"
        className={styles.menuDanger}
        onClick={(event) => {
          event.stopPropagation()
          setDownloadMenuId(null)
          void handleDeleteProject(proj.project_id)
        }}
      >
        {t('delete')}
      </button>
    </LibraryCardMenu>
  )

  const metaLine = (proj: LibraryProject) => {
    const facts: { key: string; node: ReactNode }[] = []
    if ((proj.slide_count || 0) > 0) {
      facts.push({
        key: 'slides',
        node: t('librarySlides', { n: proj.slide_count || 0 }),
      })
    }
    if (proj.has_pdf) {
      facts.push({ key: 'pdf', node: t('libraryFromPdf') })
    }
    facts.push({
      key: 'time',
      node: (
        <time dateTime={new Date((proj.last_opened_at || proj.created_at) * 1000).toISOString()}>
          {formatRelativeTime(proj.last_opened_at || proj.created_at, t, locale)}
        </time>
      ),
    })
    return (
      <div className={styles.metaBlock}>
        {renderBadge(proj)}
        <div className={styles.metaFacts}>
          {facts.map((fact, index) => (
            <span key={fact.key} className={styles.metaFactWrap}>
              {index > 0 && (
                <span className={styles.metaDivider} aria-hidden="true">
                  ·
                </span>
              )}
              <span className={styles.metaFact}>{fact.node}</span>
            </span>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div
      className={`${styles.page} ${figtree.className}`}
      style={
        {
          '--lib-display': sora.style.fontFamily,
          '--lib-body': figtree.style.fontFamily,
        } as React.CSSProperties
      }
    >
      <header className={styles.hero}>
        <div>
          <div className={styles.eyebrow}>
            <span className={styles.eyebrowMark} />
            {t('libraryLabel')}
          </div>
          <h1 className={styles.title}>{t('historyTitle')}</h1>
          <p className={styles.subtitle}>{t('historySubtitle')}</p>
        </div>
        <button type="button" onClick={() => router.push('/')} className={styles.newButton}>
          <Icon name="sparkles" className="w-4 h-4" />
          {t('newPresentation')}
        </button>
      </header>

      {loading ? (
        <div className={styles.loading}>
          <div className={styles.loadingPulse} aria-hidden="true" />
          {t('loading')}
        </div>
      ) : pastProjects.length === 0 ? (
        <div className={styles.empty}>
          <Icon name="folder" className={styles.emptyIcon} />
          <h2>{t('emptyTitle')}</h2>
          <p>{t('emptyDesc')}</p>
          <button type="button" onClick={() => router.push('/')} className={styles.newButton}>
            <Icon name="sparkles" className="w-4 h-4" />
            {t('newPresentation')}
          </button>
        </div>
      ) : (
        <>
          {activeProjects.length > 0 && (
            <section className={styles.activeStrip} aria-label={t('libraryInProgress')}>
              {activeProjects.map((proj) => {
                const pct = Math.round(Math.min(Math.max(proj.progress || 0, 0), 100))
                return (
                  <button
                    key={proj.project_id}
                    type="button"
                    className={styles.activeBanner}
                    onClick={() => openEditor(proj)}
                  >
                    <span className={styles.activePulse} aria-hidden="true" />
                    <div className={styles.activeCopy}>
                      <strong>{t('libraryInProgress')}</strong>
                      <span className={styles.activeTitle}>
                        {projectTitle(proj, t('untitledPresentation'))}
                      </span>
                    </div>
                    <div className={styles.activeMeta}>
                      <span>
                        {proj.slide_total && proj.slide_total > 0
                          ? t('slideProgress', {
                              current: proj.slide_current || 0,
                              total: proj.slide_total,
                            })
                          : t(STATUS_BADGE[proj.status]?.labelKey || 'statusGenerating')}
                      </span>
                      <span>{pct}%</span>
                    </div>
                    <div className={styles.activeTrack}>
                      <div className={styles.activeValue} style={{ width: `${pct}%` }} />
                    </div>
                    <span className={styles.activeOpen}>{t('libraryOpen')}</span>
                  </button>
                )
              })}
            </section>
          )}

          {continueProject && (
            <section className={styles.continue} aria-label={t('libraryContinue')}>
              <button
                type="button"
                className={styles.continueCard}
                onClick={() => openEditor(continueProject)}
              >
                <div className={styles.continueMedia}>
                  <CoverThumb
                    project={continueProject}
                    apiUrl={API_URL}
                    className={styles.continueCover}
                  />
                </div>
                <div className={styles.continueBody}>
                  <span className={styles.continueKicker}>{t('libraryContinue')}</span>
                  <h2 className={styles.continueTitle}>
                    {projectTitle(continueProject, t('untitledPresentation'))}
                  </h2>
                  {metaLine(continueProject)}
                  {continueProject.status === 'error' && projectMessage(continueProject) && (
                    <p className={styles.errorText}>{projectMessage(continueProject)}</p>
                  )}
                  <span className={styles.continueCta}>
                    {t('libraryOpen')}
                    <Icon name="arrowRight" className="w-4 h-4" />
                  </span>
                </div>
              </button>
            </section>
          )}

          <LibraryToolbar
            countLabel={countLabel}
            search={search}
            onSearch={setSearch}
            filter={filter}
            onFilter={setFilter}
            sort={sort}
            onSort={setSort}
            view={view}
            onView={changeView}
            onClearAll={() => void handleClearAll()}
            t={t}
          />

          {filtered.length === 0 ? (
            <div className={styles.emptyCompact}>{t('libraryNoResults')}</div>
          ) : view === 'grid' ? (
            <ul className={styles.grid}>
              {filtered.map((proj) => (
                <li key={proj.project_id} className={styles.gridItem}>
                  <article
                    className={styles.card}
                    data-active={isActiveStatus(proj.status)}
                    data-menu-open={downloadMenuId === proj.project_id}
                    onClick={() => openEditor(proj)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        openEditor(proj)
                      }
                    }}
                    role="button"
                    tabIndex={0}
                  >
                    <div className={styles.cardCoverWrap}>
                      <CoverThumb project={proj} apiUrl={API_URL} />
                      <div className={styles.cardMenuAnchor}>{cardMenu(proj)}</div>
                    </div>
                    <div className={styles.cardBody}>
                      <h3 className={styles.cardTitle} title={projectTitle(proj, t('untitledPresentation'))}>
                        {projectTitle(proj, t('untitledPresentation'))}
                      </h3>
                      {metaLine(proj)}
                      {renderProgress(proj)}
                    </div>
                  </article>
                </li>
              ))}
            </ul>
          ) : (
            <ul className={styles.projectList}>
              {filtered.map((proj) => (
                <li
                  key={proj.project_id}
                  className={styles.projectRow}
                  data-active={isActiveStatus(proj.status)}
                  data-menu-open={downloadMenuId === proj.project_id}
                >
                  <button
                    type="button"
                    className={styles.rowMainButton}
                    onClick={() => openEditor(proj)}
                  >
                    <CoverThumb
                      project={proj}
                      apiUrl={API_URL}
                      className={styles.rowThumb}
                    />
                    <div className={styles.rowMain}>
                      <h3 className={styles.projectName}>
                        {projectTitle(proj, t('untitledPresentation'))}
                      </h3>
                      {metaLine(proj)}
                      {renderProgress(proj)}
                      {proj.status === 'error' && projectMessage(proj) && (
                        <p className={styles.errorText}>{projectMessage(proj)}</p>
                      )}
                    </div>
                  </button>
                  <div className={styles.rowActions}>{cardMenu(proj)}</div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}
