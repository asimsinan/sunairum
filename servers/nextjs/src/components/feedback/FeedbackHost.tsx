'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import Icon from '@/components/Icon'
import { useUI } from '@/lib/i18n'
import {
  useFeedbackStore,
  type DialogRequest,
  type FeedbackTone,
  type ToastItem,
} from '@/store/feedbackStore'
import styles from './feedback.module.css'

const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

function toneAccentClass(tone: FeedbackTone | undefined) {
  if (tone === 'error') return styles.accentError
  if (tone === 'success') return styles.accentSuccess
  return styles.accentInfo
}

function DialogView({ dialog, onClose }: { dialog: DialogRequest; onClose: () => void }) {
  const { t } = useUI()
  const panelRef = useRef<HTMLDivElement>(null)
  const cancelRef = useRef<HTMLButtonElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const previousFocusRef = useRef<HTMLElement | null>(null)
  const [promptValue, setPromptValue] = useState(dialog.type === 'prompt' ? dialog.defaultValue ?? '' : '')
  const [exiting, setExiting] = useState(false)

  const isDestructiveConfirm = dialog.type === 'confirm' && dialog.tone === 'danger'
  const dismissible = dialog.type === 'alert' || dialog.type === 'prompt' || !isDestructiveConfirm

  const finish = useCallback(
    (action: () => void) => {
      setExiting(true)
      window.setTimeout(() => {
        action()
        onClose()
      }, 180)
    },
    [onClose],
  )

  useEffect(() => {
    previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const focusTarget =
      dialog.type === 'prompt'
        ? inputRef.current
        : isDestructiveConfirm
          ? cancelRef.current
          : panelRef.current?.querySelector<HTMLElement>(FOCUSABLE)
    focusTarget?.focus()
    return () => {
      previousFocusRef.current?.focus()
    }
  }, [dialog, isDestructiveConfirm])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        if (dialog.type === 'alert') finish(() => dialog.resolve())
        else if (dialog.type === 'confirm') finish(() => dialog.resolve(false))
        else finish(() => dialog.resolve(null))
        return
      }
      if (event.key !== 'Tab') return
      const root = panelRef.current
      if (!root) return
      const nodes = Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((el) => !el.hidden)
      if (!nodes.length) return
      const first = nodes[0]
      const last = nodes[nodes.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [dialog, finish])

  const tone: FeedbackTone | undefined =
    dialog.type === 'alert' ? dialog.tone : dialog.type === 'confirm' && dialog.tone === 'danger' ? 'error' : 'info'

  const role = dialog.type === 'alert' || isDestructiveConfirm ? 'alertdialog' : 'dialog'

  return (
    <div
      className={`${styles.scrim} ${exiting ? styles.scrimExiting : ''}`}
      onMouseDown={(event) => {
        if (!dismissible) return
        if (event.target === event.currentTarget) {
          if (dialog.type === 'alert') finish(() => dialog.resolve())
          else if (dialog.type === 'confirm') finish(() => dialog.resolve(false))
          else finish(() => dialog.resolve(null))
        }
      }}
    >
      <div
        ref={panelRef}
        className={`${styles.panel} ${exiting ? styles.panelExiting : ''}`}
        role={role}
        aria-modal="true"
        aria-labelledby="feedback-dialog-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className={styles.body}>
          {isDestructiveConfirm ? (
            <div className={styles.dangerIcon} aria-hidden="true">
              <Icon name="trash" className="w-5 h-5" />
            </div>
          ) : dialog.type === 'alert' && tone === 'error' ? (
            <div className={styles.dangerIcon} aria-hidden="true">
              <Icon name="alert" className="w-5 h-5" />
            </div>
          ) : null}
          {(dialog.type !== 'alert' || dialog.title) && (
            <h2 id="feedback-dialog-title" className={styles.title}>
              {dialog.title}
            </h2>
          )}
          {dialog.type === 'alert' && !dialog.title ? (
            <p id="feedback-dialog-title" className={styles.message} role="heading" aria-level={2}>
              {dialog.message}
            </p>
          ) : (
            dialog.message ? <p className={styles.message}>{dialog.message}</p> : null
          )}
          {dialog.type === 'prompt' && (
            <input
              ref={inputRef}
              className={styles.input}
              value={promptValue}
              onChange={(event) => setPromptValue(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') finish(() => dialog.resolve(promptValue.trim() || null))
              }}
            />
          )}
        </div>
        <div className={styles.actions}>
          {dialog.type !== 'alert' && (
            <button
              ref={cancelRef}
              type="button"
              className={styles.btnSecondary}
              onClick={() =>
                finish(() => (dialog.type === 'confirm' ? dialog.resolve(false) : dialog.resolve(null)))
              }
            >
              {dialog.cancelLabel ?? t('cancel')}
            </button>
          )}
          <button
            type="button"
            className={
              dialog.type === 'confirm' && dialog.tone === 'danger' ? styles.btnDanger : styles.btnPrimary
            }
            onClick={() => {
              if (dialog.type === 'alert') finish(() => dialog.resolve())
              else if (dialog.type === 'confirm') finish(() => dialog.resolve(true))
              else finish(() => dialog.resolve(promptValue.trim() || null))
            }}
          >
            {dialog.type === 'alert'
              ? t('ok')
              : dialog.confirmLabel ??
                (dialog.type === 'confirm' && dialog.tone === 'danger' ? t('delete') : t('ok'))}
          </button>
        </div>
      </div>
    </div>
  )
}

function ToastView({ toast, onDismiss }: { toast: ToastItem; onDismiss: () => void }) {
  const { t } = useUI()
  const [exiting, setExiting] = useState(false)
  const dismissedRef = useRef(false)

  const dismiss = useCallback(() => {
    if (dismissedRef.current) return
    dismissedRef.current = true
    setExiting(true)
    window.setTimeout(onDismiss, 220)
  }, [onDismiss])

  useEffect(() => {
    const duration = toast.durationMs ?? 1600
    if (duration <= 0) return
    const timer = window.setTimeout(dismiss, duration)
    return () => window.clearTimeout(timer)
  }, [dismiss, toast.durationMs])

  const tone = toast.tone ?? 'info'
  const title =
    toast.title ||
    (tone === 'error' ? 'Something went wrong' : tone === 'success' ? 'Done' : 'Notice')

  return (
    <div
      className={`${styles.toast} ${exiting ? styles.toastExiting : ''}`}
      data-tone={tone}
      role="status"
      aria-live="polite"
    >
      <div className={`${styles.toastIcon} ${toneAccentClass(tone)}`} aria-hidden="true">
        <Icon name={tone === 'error' ? 'alert' : tone === 'success' ? 'check' : 'sparkles'} className="w-4 h-4" />
      </div>
      <div className={styles.toastBody}>
        <p className={styles.toastTitle}>{title}</p>
        {toast.message ? <p className={styles.toastMessage}>{toast.message}</p> : null}
      </div>
      <button type="button" className={styles.toastClose} onClick={dismiss} aria-label={t('close')}>
        <Icon name="x" className="w-3.5 h-3.5" />
      </button>
    </div>
  )
}

export default function FeedbackHost() {
  const dialog = useFeedbackStore((s) => s.dialog)
  const toasts = useFeedbackStore((s) => s.toasts)
  const removeToast = useFeedbackStore((s) => s.removeToast)
  const [visibleDialog, setVisibleDialog] = useState<DialogRequest | null>(null)

  useEffect(() => {
    if (dialog) setVisibleDialog(dialog)
  }, [dialog])

  return (
    <>
      {visibleDialog && (
        <DialogView
          key={visibleDialog.id}
          dialog={visibleDialog}
          onClose={() => setVisibleDialog(null)}
        />
      )}
      {toasts.length > 0 && (
        <div className={styles.toastStack} aria-label="Notifications">
          {toasts.map((toast) => (
            <ToastView key={toast.id} toast={toast} onDismiss={() => removeToast(toast.id)} />
          ))}
        </div>
      )}
    </>
  )
}
