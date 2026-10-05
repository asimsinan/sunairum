import { create } from 'zustand'

interface ProjectState {
  progress: number
  /**
   * A translation key, not a sentence.
   *
   * This used to hold text that had already been through `t()`, which froze it
   * in whatever language was active when the status arrived: switching language
   * mid-run left the old language on screen, because a stored string cannot
   * re-translate itself. Keeping the key means every render resolves it in the
   * current language. A value that is not a known key (a message forwarded from
   * the backend) falls through `t()` unchanged.
   */
  statusKey: string
  statusVars: Record<string, string | number>
  isGenerating: boolean
  setProgress: (progress: number, statusKey: string, statusVars?: Record<string, string | number>) => void
  setGenerating: (status: boolean) => void
}

export const useProjectStore = create<ProjectState>((set) => ({
  progress: 0,
  statusKey: '',
  statusVars: {},
  isGenerating: false,
  setProgress: (progress, statusKey, statusVars = {}) => set({ progress, statusKey, statusVars }),
  setGenerating: (status) => set({ isGenerating: status }),
}))
