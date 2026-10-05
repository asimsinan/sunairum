'use client'

import Icon from '@/components/Icon'
import styles from './deckEditor.module.css'

type Props = {
  slideLabel: string
  feedback: string
  busy: boolean
  error: string
  onFeedbackChange: (value: string) => void
  onSubmit: () => void
  onOpenAdvanced: () => void
}

export default function HtmlAiRail({
  slideLabel,
  feedback,
  busy,
  error,
  onFeedbackChange,
  onSubmit,
  onOpenAdvanced,
}: Props) {
  return (
    <div className={styles.aiRail} data-busy={busy ? 'true' : undefined}>
      <div className={styles.aiRailHead}>
        <div className={styles.aiRailTitle}>
          <Icon name="sparkles" className="w-3.5 h-3.5" />
          Refine with AI
          <span className={styles.aiRailMeta}>{slideLabel}</span>
        </div>
        <button type="button" className={styles.aiRailLink} onClick={onOpenAdvanced} disabled={busy}>
          Advanced
        </button>
      </div>
      <div className={styles.aiRailBody}>
        <textarea
          className={styles.aiRailInput}
          value={feedback}
          placeholder="e.g. Tighten copy, fix overlaps, keep the hero image…"
          disabled={busy}
          rows={4}
          onChange={(e) => onFeedbackChange(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
              e.preventDefault()
              onSubmit()
            }
          }}
        />
        <button
          type="button"
          className={styles.aiRailPrimary}
          disabled={busy || !feedback.trim()}
          onClick={onSubmit}
        >
          <Icon name="sparkles" className="w-4 h-4" />
          <span>{busy ? 'Working…' : 'Regenerate'}</span>
        </button>
      </div>
      {error ? <p className={styles.aiRailError}>{error}</p> : null}
    </div>
  )
}
