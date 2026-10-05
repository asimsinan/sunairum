import { create } from 'zustand'

export type FeedbackTone = 'info' | 'error' | 'success'
export type ConfirmTone = 'danger' | 'default'

export interface AlertRequest {
  id: string
  type: 'alert'
  title?: string
  message: string
  tone?: FeedbackTone
  resolve: () => void
}

export interface ConfirmRequest {
  id: string
  type: 'confirm'
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  tone?: ConfirmTone
  resolve: (value: boolean) => void
}

export interface PromptRequest {
  id: string
  type: 'prompt'
  title: string
  message?: string
  defaultValue?: string
  confirmLabel?: string
  cancelLabel?: string
  resolve: (value: string | null) => void
}

export type DialogRequest = AlertRequest | ConfirmRequest | PromptRequest

export interface ToastItem {
  id: string
  title?: string
  message: string
  tone?: FeedbackTone
  durationMs?: number
}

interface FeedbackState {
  dialog: DialogRequest | null
  toasts: ToastItem[]
  showDialog: (dialog: DialogRequest) => void
  dismissDialog: (id: string) => void
  addToast: (toast: Omit<ToastItem, 'id'>) => string
  removeToast: (id: string) => void
}

export const useFeedbackStore = create<FeedbackState>((set, get) => ({
  dialog: null,
  toasts: [],
  showDialog: (dialog) => set({ dialog }),
  dismissDialog: (id) => {
    const { dialog } = get()
    if (dialog?.id === id) set({ dialog: null })
  },
  addToast: (toast) => {
    const id = `toast_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    set((state) => ({ toasts: [...state.toasts, { ...toast, id }] }))
    return id
  },
  removeToast: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
}))
