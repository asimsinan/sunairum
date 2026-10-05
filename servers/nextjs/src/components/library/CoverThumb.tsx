'use client'

import Icon from '@/components/Icon'
import styles from '@/app/history/history.module.css'
import { coverSrc, type LibraryProject } from './types'

export default function CoverThumb({
  project,
  apiUrl,
  className,
}: {
  project: LibraryProject
  apiUrl: string
  className?: string
}) {
  const src = coverSrc(project, apiUrl)
  return (
    <div className={`${styles.cover} ${className || ''}`} data-missing={!src || undefined}>
      {src ? (
        <img src={src} alt="" className={styles.coverImage} loading="lazy" />
      ) : (
        <div className={styles.coverPlaceholder}>
          <Icon name="layers" className="w-8 h-8" />
        </div>
      )}
    </div>
  )
}
