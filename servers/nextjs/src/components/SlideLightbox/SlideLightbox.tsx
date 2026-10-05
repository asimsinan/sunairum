'use client'

import { ReactNode } from 'react'
import { createPortal } from 'react-dom'
import Icon from '@/components/Icon'
import SvgThumb from './SvgThumb'
import styles from './slideLightbox.module.css'

export type SlideLightboxProps = {
  apiUrl: string
  eyebrow: string
  ariaLabel: string
  index: number
  total: number
  slideUrl?: string | null
  slideAlt?: string
  hint?: string
  placeholder?: string
  action?: ReactNode
  onClose: () => void
  onPrev: () => void
  onNext: () => void
  closeLabel: string
  previousLabel: string
  nextLabel: string
}

export default function SlideLightbox({
  apiUrl,
  eyebrow,
  ariaLabel,
  index,
  total,
  slideUrl,
  slideAlt = '',
  hint,
  placeholder,
  action,
  onClose,
  onPrev,
  onNext,
  closeLabel,
  previousLabel,
  nextLabel,
}: SlideLightboxProps) {
  if (typeof document === 'undefined') return null

  const progress = total > 0 ? ((index + 1) / total) * 100 : 0

  return createPortal(
    <div
      className={styles.slideLightbox}
      role="dialog"
      aria-modal="true"
      aria-label={ariaLabel}
      onClick={onClose}
    >
      <div className={styles.slideLightboxPanel} onClick={(event) => event.stopPropagation()}>
        <header className={styles.slideLightboxChrome}>
          <div className={styles.slideLightboxBrand}>
            <span className={styles.slideLightboxMark} aria-hidden="true" />
            <span className={styles.slideLightboxEyebrow}>{eyebrow}</span>
          </div>
          <div className={styles.slideLightboxPager} aria-hidden="true">
            <span className={styles.slideLightboxIndex}>{total ? index + 1 : 0}</span>
            <span className={styles.slideLightboxSlash}>/</span>
            <span>{total}</span>
          </div>
          <button
            type="button"
            className={styles.slideLightboxClose}
            onClick={onClose}
            aria-label={closeLabel}
          >
            <Icon name="x" className="w-4 h-4" />
          </button>
        </header>

        <div className={styles.slideLightboxStage}>
          <button
            type="button"
            className={styles.slideLightboxSideNav}
            data-side="prev"
            disabled={index <= 0}
            onClick={onPrev}
            aria-label={previousLabel}
          >
            <Icon name="arrowLeft" className="w-5 h-5" />
          </button>

          <div className={styles.slideLightboxFrame}>
            {slideUrl ? (
              <SvgThumb
                apiUrl={apiUrl}
                url={slideUrl}
                alt={slideAlt}
                svgClassName="slide-lightbox"
                contain
              />
            ) : (
              <div className={styles.slideLightboxPlaceholder}>{placeholder}</div>
            )}
          </div>

          <button
            type="button"
            className={styles.slideLightboxSideNav}
            data-side="next"
            disabled={index >= total - 1}
            onClick={onNext}
            aria-label={nextLabel}
          >
            <Icon name="arrowRight" className="w-5 h-5" />
          </button>
        </div>

        <div className={styles.slideLightboxProgress} aria-hidden="true">
          <span style={{ width: `${progress}%` }} />
        </div>

        <footer className={styles.slideLightboxDock}>
          {hint ? <p className={styles.slideLightboxHint}>{hint}</p> : <span className={styles.slideLightboxDockSpacer} />}
          {action ?? <span className={styles.slideLightboxDockSpacer} />}
        </footer>
      </div>
    </div>,
    document.body,
  )
}

export { default as SvgThumb, prepareSvgThumbMarkup } from './SvgThumb'
export { default as lightboxStyles } from './slideLightbox.module.css'
