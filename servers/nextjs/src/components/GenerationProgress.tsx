"use client"

import { useUI } from '@/lib/i18n'
import Icon from '@/components/Icon'
import styles from './generation-progress.module.css'

// The five phases a run moves through, in order. A percentage alone never said
// which of them was underway, so a long slide-drawing phase was indistinguishable
// from a stalled one.
const PHASES = ['plan', 'slides', 'compile', 'quality', 'export'] as const
type Phase = typeof PHASES[number]

// Derived from the status key rather than a separate piece of state, so the
// stepper cannot disagree with the sentence printed above it.
const PHASE_BY_STATUS_KEY: Record<string, Phase> = {
  status_queued: 'plan',
  status_started: 'plan',
  status_planning: 'plan',
  status_planning_content: 'plan',
  status_planning_grounding: 'plan',
  status_planning_grounding_repair: 'plan',
  status_planning_design: 'plan',
  status_planning_gate: 'plan',
  status_preparing: 'slides',
  status_generating: 'slides',
  status_generating_slide: 'slides',
  status_slide: 'slides',
  status_slide_titled: 'slides',
  status_placing_assets: 'slides',
  status_enriching_images: 'slides',
  status_resuming: 'slides',
  status_speaker_notes: 'slides',
  status_speaker_notes_slide: 'slides',
  status_fixing_slides: 'slides',
  generatingStatus: 'slides',
  status_compiling: 'compile',
  status_recompiling: 'compile',
  status_rechecking: 'quality',
  status_rendering: 'quality',
  status_repairing_visual: 'quality',
  status_publishing: 'export',
  status_completed: 'export',
  status_done_with_issues: 'export',
}

function currentPhase(statusKey: string, progress: number): Phase {
  const known = PHASE_BY_STATUS_KEY[statusKey]
  if (known) return known
  // An unrecognised status must still place the marker somewhere sensible.
  if (progress >= 95) return 'export'
  if (progress >= 75) return 'quality'
  if (progress >= 65) return 'compile'
  if (progress >= 15) return 'slides'
  return 'plan'
}

export default function GenerationProgress({
  statusKey,
  statusVars,
  progress,
  onCancel,
  cancelling,
}: {
  statusKey: string
  statusVars?: Record<string, string | number>
  progress: number
  onCancel: () => void
  cancelling: boolean
}) {
  const { t } = useUI()
  const percent = Math.round(Math.min(Math.max(progress, 0), 100))
  const finished =
    percent >= 100 ||
    statusKey === 'status_completed' ||
    statusKey === 'status_done_with_issues'
  const phase = currentPhase(statusKey, progress)
  const activeIndex = finished ? PHASES.length : PHASES.indexOf(phase)
  const label = statusKey ? t(statusKey, statusVars) : t('generatingStatus')

  return (
    <section className={styles.panel} aria-live="polite">
      <div className={styles.headline}>
        {!finished ? <span className={styles.pulse} aria-hidden="true" /> : null}
        <p className={styles.status}>{label}</p>
        <span className={styles.percent}>{percent}%</span>
      </div>

      <div
        className={styles.track}
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
      >
        <div className={styles.fill} style={{ width: `${percent}%` }} />
      </div>

      <ol className={styles.steps}>
        {PHASES.map((name, index) => {
          const state = index < activeIndex ? 'done' : index === activeIndex ? 'active' : 'pending'
          return (
            <li className={styles.step} key={name} data-state={state}>
              <span className={styles.marker} aria-hidden="true">
                {state === 'done' ? <Icon name="check" className="w-3 h-3" /> : index + 1}
              </span>
              <span className={styles.stepLabel}>{t(`phase_${name}`)}</span>
            </li>
          )
        })}
      </ol>

      <div className={styles.footer}>
        <p className={styles.hint}>{finished ? t('readyTitle') : t('generatingDesc')}</p>
        {!finished ? (
          <button type="button" className={styles.cancel} onClick={onCancel} disabled={cancelling}>
            <Icon name="x" className="w-4 h-4" />
            {cancelling ? t('cancellingGeneration') : t('cancelGeneration')}
          </button>
        ) : null}
      </div>
    </section>
  )
}
