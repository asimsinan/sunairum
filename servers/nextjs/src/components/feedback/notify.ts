import {
  useFeedbackStore,
  type ConfirmTone,
  type FeedbackTone,
} from '@/store/feedbackStore'

let dialogCounter = 0

function nextDialogId() {
  dialogCounter += 1
  return `dialog_${dialogCounter}_${Date.now()}`
}

export const notify = {
  alert(opts: { title?: string; message: string; tone?: FeedbackTone }) {
    return new Promise<void>((resolve) => {
      const id = nextDialogId()
      useFeedbackStore.getState().showDialog({
        id,
        type: 'alert',
        title: opts.title,
        message: opts.message,
        tone: opts.tone ?? 'info',
        resolve: () => {
          resolve()
          useFeedbackStore.getState().dismissDialog(id)
        },
      })
    })
  },

  confirm(opts: {
    title: string
    message: string
    confirmLabel?: string
    cancelLabel?: string
    tone?: ConfirmTone
  }) {
    return new Promise<boolean>((resolve) => {
      const id = nextDialogId()
      useFeedbackStore.getState().showDialog({
        id,
        type: 'confirm',
        title: opts.title,
        message: opts.message,
        confirmLabel: opts.confirmLabel,
        cancelLabel: opts.cancelLabel,
        tone: opts.tone ?? 'default',
        resolve: (value) => {
          resolve(value)
          useFeedbackStore.getState().dismissDialog(id)
        },
      })
    })
  },

  prompt(opts: {
    title: string
    message?: string
    defaultValue?: string
    confirmLabel?: string
    cancelLabel?: string
  }) {
    return new Promise<string | null>((resolve) => {
      const id = nextDialogId()
      useFeedbackStore.getState().showDialog({
        id,
        type: 'prompt',
        title: opts.title,
        message: opts.message,
        defaultValue: opts.defaultValue ?? '',
        confirmLabel: opts.confirmLabel,
        cancelLabel: opts.cancelLabel,
        resolve: (value) => {
          resolve(value)
          useFeedbackStore.getState().dismissDialog(id)
        },
      })
    })
  },

  toast(opts: { title?: string; message: string; tone?: FeedbackTone; durationMs?: number }) {
    // Auto-dismiss + exit animation live in ToastView so the toast slides out cleanly.
    return useFeedbackStore.getState().addToast({
      title: opts.title,
      message: opts.message,
      tone: opts.tone ?? 'info',
      durationMs: opts.durationMs ?? 1600,
    })
  },
}
