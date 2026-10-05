'use client'

import { Figtree, Sora } from 'next/font/google'
import { Suspense, useEffect, useState } from 'react'
import HtmlEditorShell from '@/components/deck-editor/HtmlEditorShell'
import { fetchPreviewMeta } from '@/components/deck-editor/api'
import type { SlideInfo } from '@/components/deck-editor/types'
import { touchProject } from '@/lib/touchProject'
import { useWizardStore } from '@/store/wizardStore'

const sora = Sora({ subsets: ['latin'], weight: ['600', '700'], variable: '--font-sora' })
const figtree = Figtree({
  subsets: ['latin'],
  weight: ['400', '600', '700', '800'],
  variable: '--font-figtree',
})

function DeckEditorInner({ projectId }: { projectId: string }) {
  const topic = useWizardStore((s) => s.config?.topic)
  const [slides, setSlides] = useState<SlideInfo[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    touchProject(projectId)
  }, [projectId])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const meta = await fetchPreviewMeta(projectId)
        if (!cancelled) setSlides(meta.slides)
      } catch (e) {
        if (!cancelled) setError(String(e))
      }
    })()
    return () => {
      cancelled = true
    }
  }, [projectId])

  if (error) {
    return (
      <div
        style={{
          padding: '2rem',
          fontFamily: 'var(--font-figtree), Figtree, sans-serif',
          color: 'var(--text-muted)',
        }}
      >
        {error}
      </div>
    )
  }

  if (!slides) {
    return (
      <div
        style={{
          padding: '2rem',
          fontFamily: 'var(--font-figtree), Figtree, sans-serif',
          color: 'var(--text-muted)',
        }}
      >
        Loading editor…
      </div>
    )
  }

  return (
    <HtmlEditorShell
      projectId={projectId}
      title={topic || projectId}
      initialSlides={slides}
    />
  )
}

export default function DeckEditorPage({ params }: { params: { projectId: string } }) {
  return (
    <div className={`${sora.variable} ${figtree.variable}`} style={{ height: '100vh' }}>
      <Suspense
        fallback={
          <div
            style={{
              padding: '2rem',
              fontFamily: 'var(--font-figtree), Figtree, sans-serif',
              color: 'var(--text-muted)',
            }}
          >
            Loading editor…
          </div>
        }
      >
        <DeckEditorInner projectId={params.projectId} />
      </Suspense>
    </div>
  )
}
