"use client"

import Icon from '@/components/Icon'
import { useUI } from '@/lib/i18n'
import styles from './source-parsing.module.css'

export default function SourceParsingPanel({
  progress,
  message,
  pages,
  tables,
  figures,
  formulas,
  error,
}: {
  progress: number
  message: string
  pages: number
  tables: number
  figures: number
  formulas: number
  error?: string | null
}) {
  const { t } = useUI()
  const value = Math.min(100, Math.max(0, Math.round(progress)))
  return (
    <section className={styles.panel} aria-live="polite">
      <div className={styles.iconWrap} data-error={Boolean(error)}>
        <Icon name={error ? 'alert' : 'file'} className="w-6 h-6" />
      </div>
      <div className={styles.content}>
        <div className={styles.eyebrow}>{t('sourceParsingEyebrow')}</div>
        <h1>{error ? t('sourceParsingFailed') : t('sourceParsingTitle')}</h1>
        <p>{error || message || t('sourceParsingDescription')}</p>
        {!error && (
          <>
            <div className={styles.progressMeta}>
              <span>{t('sourceParsingProgress')}</span>
              <strong>{value}%</strong>
            </div>
            <div className={styles.track}>
              <div className={styles.value} style={{ width: `${Math.max(value, 4)}%` }} />
            </div>
            <div className={styles.stats}>
              <span><strong>{pages || 0}</strong> {t('sourceParsingPages')}</span>
              <span><strong>{tables || 0}</strong> {t('sourceParsingTables')}</span>
              <span><strong>{figures || 0}</strong> {t('sourceParsingFigures')}</span>
              <span><strong>{formulas || 0}</strong> {t('sourceParsingFormulas')}</span>
            </div>
          </>
        )}
      </div>
    </section>
  )
}
