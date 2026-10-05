'use client'

import type { CSSProperties } from 'react'
import styles from './DesignDirectionPreview.module.css'

export type DesignPreviewPalette = {
  background?: string
  secondary_bg?: string
  primary?: string
  accent?: string
  secondary_accent?: string
  body_text?: string
}

export type DesignPreviewCandidate = {
  visual_style?: string
  color?: {
    palette?: DesignPreviewPalette
  }
  typography?: {
    heading?: { primary?: string; english?: string; css?: string }
    body?: { primary?: string; english?: string; css?: string }
  }
}

type Props = {
  candidate: DesignPreviewCandidate
  topic?: string
  titleSlideLabel: string
  contentSlideLabel: string
}

type StyleKind = 'swiss' | 'creative' | 'brutalist' | 'default'

function styleKind(visualStyle?: string): StyleKind {
  const value = (visualStyle || '').toLowerCase()
  if (value.includes('brutal')) return 'brutalist'
  if (value.includes('swiss') || value.includes('minimal')) return 'swiss'
  if (value.includes('creative') || value.includes('glass') || value.includes('modern')) return 'creative'
  return 'default'
}

function resolvePalette(palette?: DesignPreviewPalette) {
  return {
    background: palette?.background || '#FFFFFF',
    secondaryBg: palette?.secondary_bg || palette?.background || '#F8FAFC',
    primary: palette?.primary || '#1E3A8A',
    accent: palette?.accent || '#F59E0B',
    secondaryAccent: palette?.secondary_accent || palette?.primary || '#3B82F6',
    bodyText: palette?.body_text || '#0F172A',
  }
}

function fontStack(
  face?: { primary?: string; english?: string; css?: string },
  fallback = 'system-ui, sans-serif',
) {
  const parts = [face?.primary, face?.english, face?.css, fallback].filter(Boolean)
  return parts.map((part) => (String(part).includes(' ') ? `"${part}"` : part)).join(', ')
}

function topicHeadline(topic?: string) {
  const trimmed = (topic || '').trim()
  if (!trimmed) return 'Presentation title'
  return trimmed.length > 72 ? `${trimmed.slice(0, 69)}…` : trimmed
}

export default function DesignDirectionPreview({
  candidate,
  topic,
  titleSlideLabel,
  contentSlideLabel,
}: Props) {
  const kind = styleKind(candidate.visual_style)
  const colors = resolvePalette(candidate.color?.palette)
  const headingFont = fontStack(candidate.typography?.heading)
  const bodyFont = fontStack(candidate.typography?.body)
  const headline = topicHeadline(topic)

  const slideVars = {
    '--preview-bg': colors.background,
    '--preview-secondary': colors.secondaryBg,
    '--preview-primary': colors.primary,
    '--preview-accent': colors.accent,
    '--preview-secondary-accent': colors.secondaryAccent,
    '--preview-text': colors.bodyText,
    '--preview-heading-font': headingFont,
    '--preview-body-font': bodyFont,
  } as CSSProperties

  return (
    <div className={styles.root} data-style={kind} style={slideVars} aria-hidden="true">
      <div className={styles.frame}>
        <span className={styles.frameLabel}>{contentSlideLabel}</span>
        <div className={`${styles.slide} ${styles.contentSlide}`}>
          <div className={styles.contentAccent} />
          <div className={styles.contentMain}>
            <h4 className={styles.contentTitle}>{headline}</h4>
            <div className={styles.contentRule} />
            <p className={styles.contentBody}>
              Key point one with supporting detail for this design direction.
            </p>
            <p className={styles.contentBody}>
              Second line shows body type, spacing, and accent contrast.
            </p>
            <div className={styles.contentChips}>
              <span>Insight</span>
              <span>Evidence</span>
            </div>
          </div>
          <div className={styles.figureSlot}>
            <span className={styles.figureInner} />
          </div>
        </div>
      </div>

      <div className={`${styles.frame} ${styles.frameCompact}`}>
        <span className={styles.frameLabel}>{titleSlideLabel}</span>
        <div className={`${styles.slide} ${styles.titleSlide}`}>
          <div className={styles.titleBand} />
          <div className={styles.titleCopy}>
            <span className={styles.titleEyebrow}>Sunairum</span>
            <h4 className={styles.titleHeadline}>{headline}</h4>
            <p className={styles.titleSub}>Design preview · {candidate.visual_style || 'custom'}</p>
          </div>
        </div>
      </div>
    </div>
  )
}
