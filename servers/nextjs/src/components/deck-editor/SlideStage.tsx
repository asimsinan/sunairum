'use client'

import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'

export const SLIDE_STAGE_W = 1280
export const SLIDE_STAGE_H = 720

type Props = {
  /** Host fills parent; content is letterboxed with uniform scale. */
  className?: string
  style?: React.CSSProperties
  width?: number
  height?: number
  /** Controlled scale; when omitted, fit-to-host via ResizeObserver. */
  scale?: number
  onFitScaleChange?: (fitScale: number) => void
  children: ReactNode
  'aria-label'?: string
}

/**
 * Fixed design-space stage (default 1280×720) scaled uniformly into the host.
 * Use for HTML iframes / PNG so they match the old IR canvas framing.
 */
export default function SlideStage({
  className,
  style,
  width = SLIDE_STAGE_W,
  height = SLIDE_STAGE_H,
  scale: controlledScale,
  onFitScaleChange,
  children,
  'aria-label': ariaLabel,
}: Props) {
  const hostRef = useRef<HTMLDivElement>(null)
  const [fitScale, setFitScale] = useState(1)
  const [hostSize, setHostSize] = useState({ w: 0, h: 0 })
  const scale = controlledScale ?? fitScale

  useLayoutEffect(() => {
    const host = hostRef.current
    if (!host) return
    const measure = () => {
      const hw = host.clientWidth
      const hh = host.clientHeight
      setHostSize((prev) => (prev.w === hw && prev.h === hh ? prev : { w: hw, h: hh }))
      const next = Math.min(hw / width, hh / height)
      if (!Number.isFinite(next) || next <= 0) return
      setFitScale((prev) => {
        if (Math.abs(prev - next) < 0.002) return prev
        onFitScaleChange?.(next)
        return next
      })
    }
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(host)
    return () => ro.disconnect()
  }, [width, height, onFitScaleChange])

  const offsetX = Math.max(0, (hostSize.w - width * scale) / 2)
  const offsetY = Math.max(0, (hostSize.h - height * scale) / 2)

  return (
    <div
      ref={hostRef}
      className={className}
      aria-label={ariaLabel}
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        minWidth: 0,
        minHeight: 0,
        overflow: 'hidden',
        ...style,
      }}
    >
      <div
        style={{
          position: 'absolute',
          left: offsetX,
          top: offsetY,
          width,
          height,
          transform: `scale(${scale})`,
          transformOrigin: 'top left',
          background: '#fff',
        }}
      >
        {children}
      </div>
    </div>
  )
}

export function HtmlSlideFrame({
  html,
  title,
  width = SLIDE_STAGE_W,
  height = SLIDE_STAGE_H,
}: {
  html: string
  title?: string
  width?: number
  height?: number
}) {
  return (
    <iframe
      title={title || 'Slide'}
      sandbox="allow-same-origin"
      srcDoc={html}
      style={{
        display: 'block',
        width,
        height,
        border: 0,
        background: '#fff',
      }}
    />
  )
}
