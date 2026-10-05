"use client"
import { useCallback, useEffect, useRef, type TextareaHTMLAttributes } from 'react'

type AutoTextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & {
  value: string
}

/**
 * A textarea that grows to fit its own content.
 *
 * These fields hold model-written sentences of unpredictable length. A
 * single-line input hid everything past its right edge, so the value has to
 * wrap and the box has to open up far enough to show all of it. Height is set
 * from scrollHeight rather than counting characters, so wrapping stays correct
 * at any width or font size.
 */
export default function AutoTextarea({ value, className, style, onInput, ...rest }: AutoTextareaProps) {
  const ref = useRef<HTMLTextAreaElement>(null)

  const fitToContent = useCallback(() => {
    const node = ref.current
    if (!node) return
    const previous = node.style.height
    // Collapse first, or scrollHeight can only ever report growth.
    node.style.height = 'auto'
    const wanted = `${node.scrollHeight}px`
    // Writing an unchanged value would bounce the ResizeObserver below.
    node.style.height = previous === wanted ? previous : wanted
  }, [])

  // The form is filled asynchronously, long after the first render.
  useEffect(fitToContent, [value, fitToContent])

  // How much text fits depends on the width, which changes with the viewport
  // and the sidebar, neither of which touches `value`.
  useEffect(() => {
    const node = ref.current
    if (!node || typeof ResizeObserver === 'undefined') return
    const container = node.parentElement ?? node
    const observer = new ResizeObserver(fitToContent)
    observer.observe(container)
    return () => observer.disconnect()
  }, [fitToContent])

  return (
    <textarea
      {...rest}
      ref={ref}
      value={value}
      className={className}
      // Hiding the scrollbar is what makes the growth read as a plain field;
      // the height always matches the content, so nothing is cut off.
      style={{ overflowY: 'hidden', resize: 'none', ...style }}
      onInput={event => {
        fitToContent()
        onInput?.(event)
      }}
    />
  )
}
