"use client"

import { useEffect, useState, type ReactNode } from 'react'
import { useUI } from '@/lib/i18n'
import styles from './grounding-status.module.css'

interface GroundingStatusData {
  available: boolean
  grounding_mode: string
  source?: {
    parser_selected?: string
    parser_version?: string
    fallback_used?: boolean
    fallback_reason?: string | null
    page_count?: number
    source_pdf_sha256?: string | null
    tables_detected?: number
    structured_tables?: number
    figures_detected?: number
    figures_verified?: number
  }
  evidence?: {
    evidence_count?: number
    section_count?: number
    required_section_count?: number
    covered_section_count?: number
    table_count?: number
    formula_count?: number
    asset_count?: number
  }
  sections?: SourceSection[]
  plan?: {
    requested_slide_count?: number
    actual_slide_count?: number
    coverage_compressed?: boolean
    coverage?: CoverageGroup[]
    slides?: GroundedSlide[]
  } | null
  release?: {
    status?: string
    coverage_compressed?: boolean
  }
  settings_obedience?: {
    ok?: boolean
    missing_figure_ids?: string[]
    missing_table_ids?: string[]
    warnings?: string[]
    speaker_notes?: {
      enabled?: boolean
      budget_ok?: boolean
      target_words?: number
      actual_words?: number
      target_duration_minutes?: number
    }
    animations_requested?: boolean
    placed_figure_ids?: string[]
    placed_table_ids?: string[]
    selected_figure_ids?: string[]
    selected_table_ids?: string[]
    language?: {
      ok?: boolean
      language?: string
      off_language_slides?: {
        slide?: string
        expected?: string
        detected?: string
        sample?: string
      }[]
    }
  } | null
  stale_artifacts?: string[]
}

// Available as soon as the PDF is parsed; `slide_numbers` stays empty until the
// outline assigns the section, which is what this panel shows filling in.
interface SourceSection {
  section_id: string
  title: string
  level?: number
  page_start?: number
  page_end?: number
  evidence_count?: number
  slide_numbers?: number[]
  coverage_mode?: string | null
  is_backmatter?: boolean
  counts_toward_coverage?: boolean
}

interface CoverageGroup {
  slide_numbers?: number[]
  section_titles?: string[]
  coverage_mode?: string
  required_evidence_count?: number
}

interface GroundedSlide {
  slide_number: number
  slide_id: string
  title: string
  section_titles?: string[]
  coverage_mode?: string
  citation_pages?: number[]
  citation_ranges?: { page_start: number; page_end: number }[]
  evidence_count?: number
  table_count?: number
  figure_count?: number
  formula_count?: number
}

function formatPages(slide: GroundedSlide): string {
  if (slide.citation_ranges?.length) {
    return slide.citation_ranges
      .map(range => range.page_start === range.page_end ? `${range.page_start}` : `${range.page_start}-${range.page_end}`)
      .join(', ')
  }
  return slide.citation_pages?.join(', ') || ''
}

function formatSectionPages(section: SourceSection): string {
  const start = section.page_start || 0
  const end = section.page_end || start
  if (!start) return ''
  return start === end ? `${start}` : `${start}-${end}`
}

function modeLabel(mode: string | undefined, t: (key: string, vars?: Record<string, string | number>) => string): string {
  if (mode === 'compressed') return t('groundingCompressed')
  if (mode === 'grouped') return t('groundingGrouped')
  if (mode === 'summary') return t('groundingSummary')
  return t('groundingFull')
}

function CoverageDisclosure({
  label,
  count,
  progress,
  children,
}: {
  label: string
  count: string
  progress: number
  children: ReactNode
}) {
  // Always collapsed by default — section list is opt-in, never auto-expanded.
  const [open, setOpen] = useState(false)

  return (
    <details
      className={styles.disclosure}
      open={open}
      onToggle={(event) => {
        setOpen((event.currentTarget as HTMLDetailsElement).open)
      }}
    >
      <summary>
        <span className={styles.disclosureSummaryMain}>
          <span className={styles.disclosureSummaryRow}>
            {label}
            <span className={styles.disclosureCount}>{count}</span>
          </span>
          <span className={styles.coverageProgress} role="presentation">
            <span style={{ width: `${progress}%` }} />
          </span>
        </span>
      </summary>
      <div className={styles.disclosureBody}>{children}</div>
    </details>
  )
}

export default function GroundingStatus({
  apiUrl,
  projectId,
  live,
  // During a run this panel competed with the progress it sits next to: six stat
  // tiles, a row per source section and a row per slide buried the one thing the
  // reader wanted. "compact" keeps a single summary line and puts the audit
  // detail behind a disclosure.
  variant = 'full',
  className,
}: {
  apiUrl: string
  projectId: string
  live: boolean
  variant?: 'compact' | 'full'
  className?: string
}) {
  const panelClass = [styles.panel, className].filter(Boolean).join(' ')
  const compactClass = [styles.compact, className].filter(Boolean).join(' ')
  const { t } = useUI()
  const [data, setData] = useState<GroundingStatusData | null>(null)
  const [requestFailed, setRequestFailed] = useState(false)

  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const response = await fetch(`${apiUrl}/api/projects/${projectId}/grounding-status`)
        if (!response.ok) throw new Error('grounding status unavailable')
        const payload = await response.json() as GroundingStatusData
        if (!alive) return
        setData(payload)
        setRequestFailed(false)
      } catch {
        if (alive) setRequestFailed(true)
      }
    }

    load()
    if (!live) return () => { alive = false }
    const timer = setInterval(load, 2500)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [apiUrl, projectId, live])

  if (requestFailed && !data) {
    return (
      <section className={panelClass} aria-live="polite">
        <div className={styles.loadingRow}>
          <span className={styles.loadingDot} />
          <span>{t('groundingStatusUnavailable')}</span>
        </div>
      </section>
    )
  }
  if (!data || !data.available) return null

  const source = data.source || {}
  const evidence = data.evidence || {}
  const plan = data.plan
  const sections = data.sections || []
  // A panel of zeros mid-parse is noise; the parsing panel already covers that
  // stage. Wait until there is something real to report.
  if (!sections.length && !plan && !(evidence.evidence_count || 0)) return null
  const coveredSections = evidence.covered_section_count ?? 0
  // Prefer major L1 content sections (matches validate_section_coverage).
  const requiredSections =
    evidence.required_section_count ??
    sections.filter((section: { counts_toward_coverage?: boolean; is_backmatter?: boolean; level?: number }) => {
      if (typeof section.counts_toward_coverage === 'boolean') return section.counts_toward_coverage
      return !section.is_backmatter && (section.level || 1) === 1
    }).length
  const coverageDenominator = Math.max(requiredSections || 0, 1)
  const obedience =
    data.settings_obedience &&
    (data.settings_obedience.ok !== undefined ||
      (data.settings_obedience.selected_figure_ids?.length || 0) > 0 ||
      (data.settings_obedience.selected_table_ids?.length || 0) > 0 ||
      data.settings_obedience.speaker_notes)
      ? data.settings_obedience
      : null
  const obedienceIssues = Boolean(
    obedience &&
      (obedience.ok === false ||
        (obedience.missing_figure_ids && obedience.missing_figure_ids.length > 0) ||
        (obedience.missing_table_ids && obedience.missing_table_ids.length > 0) ||
        (obedience.warnings && obedience.warnings.length > 0) ||
        obedience.speaker_notes?.budget_ok === false)
  )
  // Inventory strip — not a KPI dashboard. Parser tooling was removed; what
  // remains is a quiet count of what the PDF contributed to the deck.
  const inventoryItems = [
    { value: source.page_count || 0, label: t('groundingPages') },
    { value: evidence.evidence_count || 0, label: t('groundingEvidence') },
    {
      value: evidence.table_count || source.structured_tables || 0,
      label: t('groundingTables'),
    },
    {
      value: evidence.asset_count || source.figures_detected || 0,
      label: t('groundingFigures'),
    },
  ]
  const formulaCount = evidence.formula_count || 0
  if (formulaCount > 0) {
    inventoryItems.push({ value: formulaCount, label: t('groundingFormulas') })
  }
  const inventory = (
    <ul className={styles.inventory} aria-label={t('groundingInventoryLabel')}>
      {inventoryItems.map((item) => (
        <li className={styles.inventoryItem} key={item.label}>
          <strong>{item.value}</strong>
          <span>{item.label}</span>
        </li>
      ))}
    </ul>
  )

  // Warnings stay visible in both variants: they are the only part of this panel
  // that asks the reader to do something.
  const advisories = (
    <>
      {source.fallback_used && (
        <div className={styles.advisory} data-tone="warning">
          <strong>{t('groundingFallbackWarning')}</strong>
          <span>{source.fallback_reason || t('groundingFallbackDescription')}</span>
        </div>
      )}
      {obedienceIssues && obedience && (
        <div className={styles.advisory} data-tone="warning">
          <strong>{t('groundingSettingsObedienceTitle')}</strong>
          <span>
            {[
              (obedience.missing_figure_ids?.length || 0) > 0
                ? t('groundingSettingsMissingFigures', { n: obedience.missing_figure_ids!.length })
                : null,
              (obedience.missing_table_ids?.length || 0) > 0
                ? t('groundingSettingsMissingTables', { n: obedience.missing_table_ids!.length })
                : null,
              obedience.speaker_notes?.budget_ok === false
                ? t('groundingSettingsNotesBudget', {
                    actual: obedience.speaker_notes.actual_words || 0,
                    target: obedience.speaker_notes.target_words || 0,
                    minutes: obedience.speaker_notes.target_duration_minutes || 0,
                  })
                : null,
              (obedience.warnings || []).includes('notes_budget_mismatch') &&
              obedience.speaker_notes?.budget_ok !== false
                ? t('groundingSettingsNotesBudget', {
                    actual: obedience.speaker_notes?.actual_words || 0,
                    target: obedience.speaker_notes?.target_words || 0,
                    minutes: obedience.speaker_notes?.target_duration_minutes || 0,
                  })
                : null,
              // The chosen deck language is a production setting too. Without
              // this line the panel fell back to its generic sentence and named
              // figures, tables and notes — all of which were correct.
              (obedience.language?.off_language_slides?.length || 0) > 0
                ? t('groundingSettingsOffLanguage', {
                    n: obedience.language!.off_language_slides!.length,
                    slides: obedience
                      .language!.off_language_slides!.map((item) =>
                        String(item.slide || '').replace(/^slide_0?/, '')
                      )
                      .filter(Boolean)
                      .join(', '),
                    expected: String(obedience.language?.language || '').toUpperCase(),
                  })
                : null,
            ]
              .filter(Boolean)
              .join(' · ') || t('groundingSettingsObedienceDescription')}
          </span>
        </div>
      )}
    </>
  )

  // Driven by the parsed sections, not the plan, so the reader can expand which
  // sections were found. Always starts collapsed. The fraction uses required
  // major content sections; the list still shows every parsed heading.
  const coverageProgress = requiredSections
    ? Math.round((coveredSections / coverageDenominator) * 100)
    : 0
  const coverage = sections.length > 0 && (
        <div className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h3>{t('groundingCoverageTitle')}</h3>
              <p>{plan ? t('groundingCoverageDescription') : t('groundingCoveragePending')}</p>
            </div>
            <span className={styles.coverageCount}>{coveredSections}/{requiredSections || sections.length}</span>
          </div>
          <div className={styles.sectionList}>
            {sections.map(section => {
              const assigned = section.slide_numbers || []
              const pages = formatSectionPages(section)
              return (
                <div
                  className={styles.sectionRow}
                  key={section.section_id}
                  data-assigned={assigned.length > 0}
                  data-nested={(section.level || 1) > 1}
                  data-backmatter={Boolean(section.is_backmatter)}
                >
                  <span className={styles.sectionBadge}>{pages || '—'}</span>
                  <div className={styles.citationBody}>
                    <strong>{section.title || t('groundingUntitledSection')}</strong>
                    <span>
                      {t('groundingEvidenceCitation', { n: section.evidence_count || 0 })}
                      {assigned.length ? ` · ${t('groundingSlideGroup', { slides: assigned.join(', ') })}` : ''}
                    </span>
                  </div>
                  <span className={styles.coveragePill}>
                    {assigned.length ? modeLabel(section.coverage_mode || undefined, t) : t('groundingSectionPending')}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
  )

  // Per-slide provenance: an audit trail, not progress. It used to sit open on
  // the running page, adding a row per slide to a screen that already had one
  // per source section.
  const citations = plan?.slides && plan.slides.length > 0 && (
        <div className={styles.section}>
          <div className={styles.sectionHeader}>
            <div>
              <h3>{t('groundingCitationsTitle')}</h3>
              <p>{t('groundingCitationsDescription')}</p>
            </div>
            <span className={styles.coverageCount}>
              {plan?.actual_slide_count || 0}/{plan?.requested_slide_count || 0}
            </span>
          </div>
          <div className={styles.citationList}>
            {plan.slides.map(slide => {
              const pages = formatPages(slide)
              return (
                <div className={styles.citationRow} key={slide.slide_id}>
                  <span className={styles.slideBadge}>{slide.slide_number}</span>
                  <div className={styles.citationBody}>
                    <strong>{slide.title}</strong>
                    <span>{slide.section_titles?.join(' · ') || t('groundingNoSection')}</span>
                    <span className={styles.citationSource}>
                      {pages ? `${t('groundingPdfPage')} ${pages}` : t('groundingEvidenceCitation', { n: slide.evidence_count || 0 })}
                      {slide.table_count ? ` · ${slide.table_count} ${t('groundingTables').toLowerCase()}` : ''}
                      {slide.figure_count ? ` · ${slide.figure_count} ${t('groundingFigures').toLowerCase()}` : ''}
                      {slide.formula_count ? ` · ${slide.formula_count} ${t('groundingFormulas').toLowerCase()}` : ''}
                    </span>
                  </div>
                  <span className={styles.coveragePill}>{modeLabel(slide.coverage_mode, t)}</span>
                </div>
              )
            })}
          </div>
        </div>
  )

  if (variant === 'compact') {
    return (
      <section className={compactClass} aria-live={live ? 'polite' : undefined}>
        <div className={styles.compactRow}>
          <span className={styles.modePill}>{t('groundingPdfStrict')}</span>
          <p className={styles.compactSummary}>
            {t('groundingCompactSummary', {
              pages: source.page_count || 0,
              evidence: evidence.evidence_count || 0,
              covered: coveredSections,
              // Denominator is major L1 content sections (same as coverage %),
              // not every nested/back-matter heading in the TOC.
              sections: requiredSections || sections.length,
            })}
          </p>
        </div>
        {advisories}
        <details className={styles.disclosure}>
          <summary>{t('groundingDetailToggle')}</summary>
          <div className={styles.disclosureBody}>
            {inventory}
            {sections.length > 0 && (
              <div className={styles.coverageProgress} role="presentation">
                <span style={{ width: `${coverageProgress}%` }} />
              </div>
            )}
            {coverage}
          </div>
        </details>
      </section>
    )
  }

  return (
    <section className={panelClass} aria-live={live ? 'polite' : undefined}>
      <header className={styles.header}>
        <div className={styles.headerCopy}>
          <div className={styles.eyebrow}>
            <span className={styles.eyebrowMark} />
            {t('groundingPanelTitle')}
          </div>
          <p className={styles.description}>{t('groundingPanelDescription')}</p>
          {inventory}
        </div>
        <span className={styles.modePill}>{t('groundingPdfStrict')}</span>
      </header>
      {advisories}
      {coverage && (
        <CoverageDisclosure
          label={t('groundingCoverageToggle')}
          count={`${coveredSections}/${requiredSections || sections.length}`}
          progress={coverageProgress}
        >
          {coverage}
        </CoverageDisclosure>
      )}
      {citations && (
        <details className={styles.disclosure}>
          <summary>{t('groundingCitationsToggle')}</summary>
          <div className={styles.disclosureBody}>{citations}</div>
        </details>
      )}
    </section>
  )
}
