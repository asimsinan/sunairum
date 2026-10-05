'use client'

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import Icon from '@/components/Icon'
import SlideStage, { HtmlSlideFrame } from './SlideStage'
import type { SlideInfo } from './types'
import styles from './deckEditor.module.css'

export type PresentSlideVisual = {
  html?: string | null
  pngUrl?: string | null
}

type Props = {
  slides: SlideInfo[]
  startIndex: number
  visualsByFile: Record<string, PresentSlideVisual>
  onClose: () => void
}

type Motion = 'forward' | 'back'

type SlideLayer = {
  key: number
  index: number
  visual: PresentSlideVisual
  role: 'active' | 'outgoing'
  motion: Motion
}

const TRANSITION_MS = 420

function requestElementFullscreen(el: HTMLElement) {
  const anyEl = el as HTMLElement & {
    webkitRequestFullscreen?: () => Promise<void> | void
    msRequestFullscreen?: () => Promise<void> | void
  }
  const req =
    el.requestFullscreen?.bind(el) ||
    anyEl.webkitRequestFullscreen?.bind(el) ||
    anyEl.msRequestFullscreen?.bind(el)
  return Promise.resolve(req?.()).catch(() => undefined)
}

function getFullscreenElement(): Element | null {
  const doc = document as Document & {
    webkitFullscreenElement?: Element | null
    msFullscreenElement?: Element | null
  }
  return document.fullscreenElement || doc.webkitFullscreenElement || doc.msFullscreenElement || null
}

function exitDocumentFullscreen() {
  if (!getFullscreenElement()) return Promise.resolve()
  const doc = document as Document & {
    webkitExitFullscreen?: () => Promise<void> | void
    msExitFullscreen?: () => Promise<void> | void
  }
  const exit =
    document.exitFullscreen?.bind(document) ||
    doc.webkitExitFullscreen?.bind(document) ||
    doc.msExitFullscreen?.bind(document)
  return Promise.resolve(exit?.()).catch(() => undefined)
}

function isPresentNavKey(event: KeyboardEvent) {
  const key = event.key
  const code = event.code
  return (
    key === 'ArrowRight' ||
    key === 'ArrowLeft' ||
    key === ' ' ||
    key === 'Spacebar' ||
    key === 'PageDown' ||
    key === 'PageUp' ||
    key === 'Home' ||
    key === 'End' ||
    key === 'Escape' ||
    code === 'ArrowRight' ||
    code === 'ArrowLeft' ||
    code === 'Space' ||
    code === 'PageDown' ||
    code === 'PageUp' ||
    code === 'Home' ||
    code === 'End' ||
    code === 'Escape'
  )
}

function PresentSlideView({
  visual,
  className,
  title,
  role,
  motion,
}: {
  visual: PresentSlideVisual
  className: string
  title: string
  role: string
  motion: string
}) {
  return (
    <div className={className} data-role={role} data-motion={motion} aria-label={title}>
      <SlideStage style={{ background: '#000' }}>
        {visual.html ? (
          <HtmlSlideFrame html={visual.html} title={title} />
        ) : visual.pngUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={visual.pngUrl}
            alt={title}
            style={{
              display: 'block',
              width: '100%',
              height: '100%',
              objectFit: 'contain',
              background: '#000',
            }}
          />
        ) : (
          <div
            style={{
              display: 'grid',
              placeItems: 'center',
              width: '100%',
              height: '100%',
              color: '#94a3b8',
              fontWeight: 650,
              background: '#111827',
            }}
          >
            Preview unavailable
          </div>
        )}
      </SlideStage>
    </div>
  )
}

export default function PresentMode({
  slides,
  startIndex,
  visualsByFile,
  onClose,
}: Props) {
  const initial = Math.min(Math.max(startIndex, 0), Math.max(slides.length - 1, 0))
  const [index, setIndex] = useState(initial)
  const [layers, setLayers] = useState<SlideLayer[]>(() => {
    const slide = slides[initial]
    if (!slide) return []
    return [
      {
        key: 0,
        index: initial,
        visual: visualsByFile[slide.filename] || {},
        role: 'active',
        motion: 'forward',
      },
    ]
  })
  const [chromeVisible, setChromeVisible] = useState(true)
  const [needsFsGesture, setNeedsFsGesture] = useState(false)

  const rootRef = useRef<HTMLDivElement>(null)
  const onCloseRef = useRef(onClose)
  const closingRef = useRef(false)
  const enteredFsRef = useRef(false)
  const animatingRef = useRef(false)
  const indexRef = useRef(initial)
  const slidesRef = useRef(slides)
  const visualsRef = useRef(visualsByFile)
  const layerKeyRef = useRef(1)
  const clearTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  onCloseRef.current = onClose
  slidesRef.current = slides
  visualsRef.current = visualsByFile
  indexRef.current = index

  const bumpChrome = useCallback(() => {
    setChromeVisible(true)
  }, [])

  const finishTransition = useCallback(() => {
    animatingRef.current = false
    setLayers((prev) => prev.filter((layer) => layer.role === 'active'))
    clearTimerRef.current = null
  }, [])

  const goTo = useCallback(
    (nextIndex: number, motion: Motion) => {
      const list = slidesRef.current
      const currentIndex = indexRef.current
      if (nextIndex < 0 || nextIndex >= list.length || nextIndex === currentIndex) return
      const nextSlide = list[nextIndex]
      if (!nextSlide) return

      if (animatingRef.current) {
        if (clearTimerRef.current) {
          clearTimeout(clearTimerRef.current)
          clearTimerRef.current = null
        }
        animatingRef.current = false
        setLayers((prev) => prev.filter((layer) => layer.role === 'active'))
      }

      animatingRef.current = true
      const incomingKey = layerKeyRef.current++
      const incomingVisual = visualsRef.current[nextSlide.filename] || {}

      setLayers((prev) => {
        const current = prev.find((layer) => layer.role === 'active')
        const nextLayers: SlideLayer[] = []
        if (current) {
          nextLayers.push({ ...current, role: 'outgoing', motion })
        }
        nextLayers.push({
          key: incomingKey,
          index: nextIndex,
          visual: incomingVisual,
          role: 'active',
          motion,
        })
        return nextLayers
      })
      indexRef.current = nextIndex
      setIndex(nextIndex)
      bumpChrome()

      if (clearTimerRef.current) clearTimeout(clearTimerRef.current)
      clearTimerRef.current = setTimeout(finishTransition, TRANSITION_MS)
    },
    [bumpChrome, finishTransition],
  )

  const goNext = useCallback(() => {
    goTo(indexRef.current + 1, 'forward')
  }, [goTo])

  const goPrev = useCallback(() => {
    goTo(indexRef.current - 1, 'back')
  }, [goTo])

  const closePresentation = useCallback(() => {
    if (closingRef.current) return
    closingRef.current = true
    void exitDocumentFullscreen().finally(() => {
      onCloseRef.current()
    })
  }, [])

  const focusRoot = useCallback(() => {
    const root = rootRef.current
    if (!root) return
    try {
      root.focus({ preventScroll: true })
    } catch {
      root.focus()
    }
  }, [])

  const enterFullscreen = useCallback(() => {
    const el = rootRef.current
    if (!el) return
    void requestElementFullscreen(el).then(() => {
      focusRoot()
      window.setTimeout(() => {
        if (getFullscreenElement()) {
          enteredFsRef.current = true
          setNeedsFsGesture(false)
          focusRoot()
        } else {
          // Browser blocked FS — keep windowed present; do NOT close.
          setNeedsFsGesture(true)
        }
      }, 250)
    })
  }, [focusRoot])

  useLayoutEffect(() => {
    enterFullscreen()

    const onFsChange = () => {
      const fsEl = getFullscreenElement()
      if (fsEl) {
        enteredFsRef.current = true
        setNeedsFsGesture(false)
        if (rootRef.current && (fsEl === rootRef.current || fsEl.contains(rootRef.current))) {
          focusRoot()
        }
        return
      }
      // Only auto-close after we had successfully entered fullscreen.
      // Otherwise Present instantly dismisses when FS is denied/pending.
      if (enteredFsRef.current && !closingRef.current) {
        closingRef.current = true
        onCloseRef.current()
      }
    }
    document.addEventListener('fullscreenchange', onFsChange)
    document.addEventListener('webkitfullscreenchange', onFsChange as EventListener)
    return () => {
      document.removeEventListener('fullscreenchange', onFsChange)
      document.removeEventListener('webkitfullscreenchange', onFsChange as EventListener)
      if (getFullscreenElement()) void exitDocumentFullscreen()
    }
  }, [enterFullscreen, focusRoot])

  useEffect(() => {
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    let hideTimer: ReturnType<typeof setTimeout> | null = null
    const scheduleHide = () => {
      if (hideTimer) clearTimeout(hideTimer)
      hideTimer = setTimeout(() => setChromeVisible(false), 2200)
    }
    scheduleHide()

    const onKey = (event: KeyboardEvent) => {
      if (!isPresentNavKey(event)) return

      const key = event.key
      const code = event.code
      const goForward =
        key === 'ArrowRight' ||
        key === ' ' ||
        key === 'Spacebar' ||
        key === 'PageDown' ||
        code === 'ArrowRight' ||
        code === 'Space' ||
        code === 'PageDown'
      const goBack =
        key === 'ArrowLeft' || key === 'PageUp' || code === 'ArrowLeft' || code === 'PageUp'

      event.preventDefault()
      event.stopPropagation()
      bumpChrome()

      if (key === 'Escape' || code === 'Escape') {
        closePresentation()
        return
      }
      if (goForward) {
        goNext()
        scheduleHide()
        return
      }
      if (goBack) {
        goPrev()
        scheduleHide()
        return
      }
      if (key === 'Home' || code === 'Home') {
        goTo(0, 'back')
        scheduleHide()
        return
      }
      if (key === 'End' || code === 'End') {
        goTo(Math.max(0, slidesRef.current.length - 1), 'forward')
        scheduleHide()
      }
    }

    const onMouseMove = () => {
      bumpChrome()
      scheduleHide()
    }

    focusRoot()
    const focusTimers = [0, 50, 200, 500].map((ms) => window.setTimeout(focusRoot, ms))

    window.addEventListener('keydown', onKey, true)
    window.addEventListener('mousemove', onMouseMove)
    return () => {
      document.body.style.overflow = previous
      window.removeEventListener('keydown', onKey, true)
      window.removeEventListener('mousemove', onMouseMove)
      focusTimers.forEach((id) => window.clearTimeout(id))
      if (hideTimer) clearTimeout(hideTimer)
    }
  }, [bumpChrome, closePresentation, focusRoot, goNext, goPrev, goTo])

  useEffect(() => {
    return () => {
      if (clearTimerRef.current) clearTimeout(clearTimerRef.current)
    }
  }, [])

  useEffect(() => {
    const slide = slides[index]
    if (!slide) return
    setLayers((cur) => {
      const active = cur.find((l) => l.role === 'active')
      if (!active) return cur
      const visual = visualsByFile[slide.filename] || {}
      if (active.visual.html === visual.html && active.visual.pngUrl === visual.pngUrl) {
        return cur
      }
      return cur.map((l) => (l.role === 'active' ? { ...l, visual } : l))
    })
  }, [index, slides, visualsByFile])

  if (!slides[index]) return null
  const title = slides[index]?.filename || `Slide ${index + 1}`

  return (
    <div
      ref={rootRef}
      className={styles.presentRoot}
      role="dialog"
      aria-modal="true"
      tabIndex={-1}
      onClick={() => goNext()}
    >
      <div
        className={styles.presentChrome}
        data-visible={chromeVisible ? 'true' : undefined}
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.presentControls}>
          <span className={styles.presentMeta}>
            {index + 1} / {slides.length}
          </span>
          <button
            type="button"
            className={styles.presentBtn}
            disabled={index <= 0}
            tabIndex={-1}
            onClick={goPrev}
            aria-label="Previous slide"
          >
            <Icon name="arrowLeft" className="w-4 h-4" />
          </button>
          <button
            type="button"
            className={styles.presentBtn}
            disabled={index >= slides.length - 1}
            tabIndex={-1}
            onClick={goNext}
            aria-label="Next slide"
          >
            <Icon name="arrowRight" className="w-4 h-4" />
          </button>
          <button
            type="button"
            className={styles.presentBtn}
            tabIndex={-1}
            onClick={closePresentation}
            aria-label="Exit presentation"
          >
            <Icon name="x" className="w-4 h-4" />
            <span>Exit</span>
          </button>
        </div>
      </div>

      {needsFsGesture ? (
        <button
          type="button"
          className={styles.presentBtn}
          style={{ position: 'absolute', top: 16, left: 16, zIndex: 90 }}
          onClick={(e) => {
            e.stopPropagation()
            enterFullscreen()
          }}
        >
          Enter fullscreen
        </button>
      ) : null}

      <div className={styles.presentStage}>
        {layers.map((layer) => (
          <PresentSlideView
            key={layer.key}
            visual={layer.visual}
            className={styles.presentSlide}
            title={title}
            role={layer.role}
            motion={layer.motion}
          />
        ))}
      </div>
    </div>
  )
}
