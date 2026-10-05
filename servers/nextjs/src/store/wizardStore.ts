import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

export interface WizardConfig {
  projectId: string
  /** One-shot navigation intent; lets the editor distinguish create from reopen. */
  entry?: 'create' | 'open'
  topic: string
  mode: 'scratch' | 'template'
  templateId?: string
  color?: string
  lang: string
  slides: string
  hasSource?: boolean
  /** Directives about tone, style and constraints, kept apart from the subject. */
  instructions?: string
  /** Optional presentation-method pack for scratch free_design only. */
  styleId?: string
}

interface WizardState {
  config: WizardConfig | null
  setConfig: (config: WizardConfig | null) => void
}

export const useWizardStore = create<WizardState>()(
  persist(
    (set) => ({
      config: null,
      setConfig: (config) => set({ config }),
    }),
    {
      name: 'ppt-wizard-config',
      storage: createJSONStorage(() => sessionStorage),
    }
  )
)
