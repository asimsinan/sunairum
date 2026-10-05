'use client'

import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
} from 'react'
import { createPortal } from 'react-dom'
import styles from '@/app/history/history.module.css'

export default function LibraryCardMenu({
  open,
  onOpenChange,
  label,
  children,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  label: string
  children: ReactNode
}) {
  const [menuPos, setMenuPos] = useState<{ top: number; left: number } | null>(null)
  const [mounted, setMounted] = useState(false)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setMounted(true)
  }, [])

  const placeMenu = () => {
    const rect = buttonRef.current?.getBoundingClientRect()
    if (!rect) return
    const menuWidth = Math.max(dropdownRef.current?.offsetWidth || 0, 200)
    const menuHeight = dropdownRef.current?.offsetHeight || 220
    const pad = 8
    let left = rect.right - menuWidth
    let top = rect.bottom + pad
    left = Math.max(pad, Math.min(left, window.innerWidth - menuWidth - pad))
    if (top + menuHeight > window.innerHeight - pad) {
      top = Math.max(pad, rect.top - menuHeight - pad)
    }
    setMenuPos({ top, left })
  }

  const close = () => {
    onOpenChange(false)
    setMenuPos(null)
  }

  const toggle = (event: ReactMouseEvent) => {
    event.stopPropagation()
    event.preventDefault()
    if (open) {
      close()
      return
    }
    placeMenu()
    onOpenChange(true)
  }

  useLayoutEffect(() => {
    if (!open) return
    placeMenu()
  }, [open, children])

  useEffect(() => {
    if (!open) return
    const onDown = (event: globalThis.MouseEvent) => {
      const target = event.target as Node
      if (buttonRef.current?.contains(target)) return
      if (dropdownRef.current?.contains(target)) return
      close()
    }
    const onReposition = () => placeMenu()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close()
    }
    const timer = window.setTimeout(() => {
      document.addEventListener('mousedown', onDown)
    }, 0)
    window.addEventListener('resize', onReposition)
    window.addEventListener('scroll', onReposition, true)
    document.addEventListener('keydown', onKey)
    return () => {
      window.clearTimeout(timer)
      document.removeEventListener('mousedown', onDown)
      window.removeEventListener('resize', onReposition)
      window.removeEventListener('scroll', onReposition, true)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const menu =
    mounted &&
    open &&
    menuPos &&
    createPortal(
      <div
        ref={dropdownRef}
        className={styles.cardMenuDropdown}
        role="menu"
        style={{ top: menuPos.top, left: menuPos.left }}
        onClick={(event) => event.stopPropagation()}
      >
        {children}
      </div>,
      document.body,
    )

  return (
    <div className={styles.cardMenu} data-open={open}>
      <button
        ref={buttonRef}
        type="button"
        className={styles.iconGhost}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={label}
        onClick={toggle}
      >
        ⋯
      </button>
      {menu}
    </div>
  )
}
